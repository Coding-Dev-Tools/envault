"""Main CLI entrypoint for Envault."""

from __future__ import annotations

import typer
from pathlib import Path
from rich.console import Console
from rich.prompt import Confirm
from rich.table import Table

try:
    from revenueholdings_license import require_license
except ImportError:
    def require_license(tool):
        def decorator(func):
            return func
        return decorator

from envault import __version__
from envault.audit import AuditLogger
from envault.config import EnvaultConfig, init_config
from envault.diff import diff_env_files, format_diff
from envault.rotate import rotate_env_var
from envault.stores import get_store
from envault.sync import sync_env_files

app = typer.Typer(
    name="envault",
    help="Env variable syncing, diffing, and secret rotation CLI",
    no_args_is_help=True,
)
console = Console()
err_console = Console(stderr=True)


def load_config(config_path: str = "") -> EnvaultConfig:
    """Load config, optionally from a specific path."""
    path = config_path if config_path else ".envault.yml"
    return EnvaultConfig.load(path)


# â”€â”€ Init â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@app.command()
def init(
    project_name: str = typer.Argument(..., help="Project name"),
    config_path: str = typer.Option(".envault.yml", "--config", "-c", help="Config file path"),
):
    """Initialize a new .envault.yml config file."""
    init_config(project_name, config_path)
    console.print(f"[green]âœ“[/green] Created {config_path} for project '{project_name}'")
    console.print("\nEdit the file to configure environments and secret stores.")
    console.print("Then run: envault diff, envault sync, envault rotate")


# â”€â”€ Diff â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@app.command()
def diff(
    source_env: str = typer.Argument("dev", help="Source environment"),
    target_env: str = typer.Argument("prod", help="Target environment"),
    source_file: str | None = typer.Option(None, "--source", "-s", help="Source .env file path (overrides env name)"),
    target_file: str | None = typer.Option(None, "--target", "-t", help="Target .env file path (overrides env name)"),
    config_path: str = typer.Option("", "--config", "-c", help="Config file path"),
):
    """Diff environment variables between two environments or .env files."""
    config = load_config(config_path)

    if source_file and target_file:
        result = diff_env_files(source_file, target_file)
        label_s, label_t = Path(source_file).name, Path(target_file).name
    else:
        src_path = source_file or config.get_env_path(source_env)
        tgt_path = target_file or config.get_env_path(target_env)
        result = diff_env_files(src_path, tgt_path)
        label_s, label_t = source_env, target_env

    console.print(format_diff(result, label_s, label_t))

    if result.has_differences:
        console.print(f"\nTotal: {result.total_differences} difference(s)")
    raise typer.Exit(0)


@app.command()
def diff_files(
    file1: str = typer.Argument(..., help="First .env file"),
    file2: str = typer.Argument(..., help="Second .env file"),
):
    """Diff two .env files directly (no config needed)."""
    result = diff_env_files(file1, file2)
    console.print(format_diff(result, Path(file1).name, Path(file2).name))
    if result.has_differences:
        console.print(f"\nTotal: {result.total_differences} difference(s)")
    raise typer.Exit(0)


# â”€â”€ Sync â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@app.command()
def sync(
    source_env: str = typer.Argument("staging", help="Source environment"),
    target_env: str = typer.Argument("prod", help="Target environment"),
    strategy: str = typer.Option("source_wins", "--strategy", "-s",
                                  help="Conflict resolution: source_wins, target_wins, error"),
    allow_delete: bool = typer.Option(False, "--allow-delete", "-d", help="Delete keys not in source"),
    skip: list[str] | None = typer.Option(None, "--skip", help="Keys to skip"),  # noqa: B008
    dry_run: bool = typer.Option(False, "--dry-run", "-n", help="Show changes without applying"),
    config_path: str = typer.Option("", "--config", "-c", help="Config file path"),
):
    """Sync environment variables from source env to target env."""
    config = load_config(config_path)

    src_path = config.get_env_path(source_env)
    tgt_path = config.get_env_path(target_env)

    if not src_path.exists():
        err_console.print(f"[red]Error:[/red] Source file '{src_path}' not found")
        raise typer.Exit(1)
    if not tgt_path.exists():
        err_console.print(f"[red]Error:[/red] Target file '{tgt_path}' not found")
        raise typer.Exit(1)

    skip_keys = set(skip) if skip else None
    audit = AuditLogger(config.audit_log_path)

    if dry_run:
        from envault.diff import load_env_file
        source_vars = load_env_file(src_path)
        target_vars = load_env_file(tgt_path).copy()

        from envault.sync import sync_envs
        result = sync_envs(source_vars, target_vars, strategy=strategy,
                           allow_delete=allow_delete, skip_keys=skip_keys)
        console.print(f"[yellow]Dry run[/yellow] â€” would sync {source_env} â†’ {target_env}:")
        console.print(f"  + {len(result.added)} keys to add")
        console.print(f"  ~ {len(result.updated)} keys to update")
        console.print(f"  - {len(result.deleted)} keys to delete")
        if result.conflicts:
            console.print(f"  ! {len(result.conflicts)} conflicts")
        if result.skipped:
            console.print(f"  - {len(result.skipped)} keys skipped")
        raise typer.Exit(0)

    result = sync_env_files(
        src_path, tgt_path,
        strategy=strategy,
        allow_delete=allow_delete,
        skip_keys=skip_keys,
        audit=audit,
    )

    if result.conflicts:
        for c in result.conflicts:
            err_console.print(f"[red]![/red] Conflict on '{c.key}'")
        raise typer.Exit(1)

    if result.success_count == 0 and not result.deleted:
        console.print(f"[green]âœ“[/green] {source_env} and {target_env} are already in sync")
    else:
        console.print(f"[green]âœ“[/green] Synced {source_env} â†’ {target_env}:")
        if result.added:
            console.print(f"  + Added: {', '.join(result.added[:10])}" +
                         (f" +{len(result.added) - 10}" if len(result.added) > 10 else ""))
        if result.updated:
            console.print(f"  ~ Updated: {', '.join(result.updated[:10])}" +
                         (f" +{len(result.updated) - 10}" if len(result.updated) > 10 else ""))
        if result.deleted:
            console.print(f"  - Deleted: {', '.join(result.deleted)}")
        if result.skipped:
            console.print(f"  - Skipped: {', '.join(result.skipped[:10])}" +
                         (f" +{len(result.skipped) - 10}" if len(result.skipped) > 10 else ""))


# â”€â”€ Rotate â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@app.command()
def rotate(
    key: str = typer.Argument(..., help="Environment variable name to rotate"),
    env: str = typer.Option("dev", "--env", "-e", help="Environment name"),
    length: int = typer.Option(32, "--length", "-l", help="Length of new secret"),
    dry_run: bool = typer.Option(False, "--dry-run", "-n", help="Show new value without changing file"),
    output: bool = typer.Option(False, "--show", help="Display the new secret value"),
    config_path: str = typer.Option("", "--config", "-c", help="Config file path"),
):
    """Rotate a single environment variable's value."""
    config = load_config(config_path)
    env_file = config.get_env_path(env)

    if not env_file.exists():
        err_console.print(f"[red]Error:[/red] Environment file '{env_file}' not found")
        raise typer.Exit(1)

    audit = AuditLogger(config.audit_log_path)

    success, new_value = rotate_env_var(
        key, env_file,
        length=length,
        dry_run=dry_run,
        audit=audit,
    )

    if not success:
        err_console.print(f"[red]Error:[/red] Key '{key}' not found in {env_file}")
        raise typer.Exit(1)

    if dry_run:
        if output:
            console.print(f"[yellow]Would rotate[/yellow] {key} â†’ {new_value}")
        else:
            console.print(f"[yellow]Would rotate[/yellow] {key} (use --show to display)")
    else:
        console.print(f"[green]âœ“[/green] Rotated {key} in {env}")
        if output:
            console.print(f"  New value: {new_value}")


@app.command()
def rotate_all(
    env: str = typer.Option("prod", "--env", "-e", help="Environment name to rotate all in"),
    dry_run: bool = typer.Option(False, "--dry-run", "-n", help="Show what would rotate"),
    config_path: str = typer.Option("", "--config", "-c", help="Config file path"),
):
    """Rotate all variables in an environment (re-generates every value)."""
    config = load_config(config_path)
    env_file = config.get_env_path(env)

    if not env_file.exists():
        err_console.print(f"[red]Error:[/red] Environment file '{env_file}' not found")
        raise typer.Exit(1)

    audit = AuditLogger(config.audit_log_path)

    from envault.diff import load_env_file
    vars = load_env_file(env_file)

    if not vars:
        console.print("[yellow]No variables found[/yellow]")
        raise typer.Exit(0)

    if not dry_run:
        confirm = Confirm.ask(f"Rotate all {len(vars)} variables in {env}? This cannot be undone.")
        if not confirm:
            console.print("Cancelled")
            raise typer.Exit(0)

    rotated = 0
    for key in sorted(vars.keys()):
        success, new_val = rotate_env_var(
            key, env_file,
            dry_run=dry_run,
            audit=audit,
        )
        if success:
            rotated += 1

    if dry_run:
        console.print(f"[yellow]Dry run:[/yellow] Would rotate {rotated} variables in {env}")
    else:
        console.print(f"[green]âœ“[/green] Rotated {rotated} variables in {env}")


# â”€â”€ Store Commands â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

store_app = typer.Typer(name="store", help="Manage secret store integrations.")
app.add_typer(store_app)


@store_app.command("list")
def store_list(
    store_name: str | None = typer.Argument(None, help="Store name from config"),
    prefix: str = typer.Option("", "--prefix", "-p", help="Filter keys by prefix"),
    config_path: str = typer.Option("", "--config", "-c", help="Config file path"),
):
    """List keys in a secret store."""
    config = load_config(config_path)

    if store_name and store_name in config.stores:
        store_config = config.stores[store_name]
        store_instance = get_store(store_config)
    else:
        store_instance = get_store(config_path)

    keys = store_instance.list_keys(prefix=prefix)

    if not keys:
        console.print("[yellow]No keys found[/yellow]")
        return

    table = Table(title=f"Keys ({len(keys)})")
    table.add_column("Key", style="cyan")
    for k in keys:
        table.add_row(k)
    console.print(table)


@store_app.command("get")
def store_get(
    key: str = typer.Argument(..., help="Key to retrieve"),
    store_name: str | None = typer.Option(None, "--store", "-s", help="Store name from config"),
    config_path: str = typer.Option("", "--config", "-c", help="Config file path"),
):
    """Get a value from a secret store."""
    config = load_config(config_path)

    if store_name and store_name in config.stores:
        store_instance = get_store(config.stores[store_name])
    else:
        store_instance = get_store(config_path)

    value = store_instance.get(key)
    if value is None:
        err_console.print(f"[red]Key '{key}' not found[/red]")
        raise typer.Exit(1)

    console.print(value)


@store_app.command("set")
def store_set(
    key: str = typer.Argument(..., help="Key to set"),
    value: str = typer.Argument(..., help="Value to store"),
    store_name: str | None = typer.Option(None, "--store", "-s", help="Store name from config"),
    config_path: str = typer.Option("", "--config", "-c", help="Config file path"),
):
    """Set a value in a secret store."""
    config = load_config(config_path)

    if store_name and store_name in config.stores:
        store_instance = get_store(config.stores[store_name])
    else:
        store_instance = get_store(config_path)

    store_instance.set(key, value)
    console.print(f"[green]âœ“[/green] Set {key}")


# â”€â”€ Audit â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@app.command()
def audit(
    key: str | None = typer.Option(None, "--key", "-k", help="Filter by key"),
    action: str | None = typer.Option(None, "--action", "-a", help="Filter by action (add/update/delete/rotate)"),
    limit: int = typer.Option(50, "--limit", "-n", help="Number of entries to show"),
    config_path: str = typer.Option("", "--config", "-c", help="Config file path"),
):
    """View audit trail of Envault operations."""
    config = load_config(config_path)
    logger = AuditLogger(config.audit_log_path)
    entries = logger.get_history(key=key, action=action, limit=limit)

    if not entries:
        console.print("[yellow]No audit entries found[/yellow]")
        raise typer.Exit(0)

    table = Table(title=f"Audit Trail ({len(entries)} entries)")
    table.add_column("Timestamp", style="dim")
    table.add_column("Action", style="bold")
    table.add_column("Key")
    table.add_column("Details")

    for entry in entries:
        details = entry.get("source") or entry.get("target") or entry.get("env_file") or ""
        table.add_row(
            entry.get("timestamp", "")[-23:-7],
            entry.get("action", ""),
            entry.get("key", ""),
            details[:40],
        )

    console.print(table)


# â”€â”€ Version â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@app.command()
def version():
    """Show version."""
    console.print(f"envault v{__version__}")


if __name__ == "__main__":
    app()

