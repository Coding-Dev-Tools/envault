"""Main CLI entrypoint for Envault."""

from __future__ import annotations

import typer
from envault import __version__
from envault.audit import AuditLogger
from envault.config import EnvaultConfig, init_config
from envault.diff import diff_env_files, format_diff
from envault.encrypt import decrypt_env, encrypt_env
from envault.rotate import rotate_env_var
from envault.serve import run_server
from envault.stores import get_store
from envault.sync import sync_env_files
from pathlib import Path
from rich.console import Console
from rich.prompt import Confirm
from rich.table import Table

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


# ── Init ────────────────────────────────────────────────────────────────────

@app.command()
def init(
    project_name: str = typer.Argument(..., help="Project name"),
    config_path: str = typer.Option(".envault.yml", "--config", "-c", help="Config file path"),
    no_example: bool = typer.Option(False, "--no-example", help="Skip .env.example generation"),
    example_file: str = typer.Option(".env.example", "--example-file", "-e", help="Output path for .env.example"),
):
    """Initialize a new .envault.yml config file and generate .env.example.

    Scans existing .env files for keys and creates a .env.example with
    all keys but blank values — safe to commit to version control.
    """
    # Before overwriting config, collect env file paths from any existing config
    # so _generate_env_example can scan them for keys.
    existing_env_files: list[str] = []
    if Path(config_path).exists():
        existing_config = EnvaultConfig.load(config_path)
        existing_env_files = [e.env_file for e in existing_config.environments]

    init_config(
        project_name,
        config_path,
        generate_example=not no_example,
        example_path=example_file,
        env_files=existing_env_files if existing_env_files else None,
    )
    console.print(f"[green]✓[/green] Created {config_path} for project '{project_name}'")
    if not no_example:
        example_path = Path(example_file)
        if example_path.exists():
            key_count = sum(1 for line in example_path.read_text().splitlines() if line and not line.startswith("#"))
            console.print(f"[green]✓[/green] Generated {example_file} ({key_count} keys)")
        else:
            console.print(f"[yellow]⚠[/yellow] No .env files found — {example_file} not created")
    console.print("\nEdit the config to set up environments and secret stores.")
    console.print("Then run: envault diff, envault sync, envault rotate")


# ── Diff ────────────────────────────────────────────────────────────────────

@app.command()
def diff(
    source_env: str = typer.Argument("dev", help="Source environment"),
    target_env: str = typer.Argument("prod", help="Target environment"),
    source_file: str | None = typer.Option(None, "--source", "-s", help="Source .env file path (overrides env name)"),
    target_file: str | None = typer.Option(None, "--target", "-t", help="Target .env file path (overrides env name)"),
    config_path: str = typer.Option("", "--config", "-c", help="Config file path"),
    fail_on_missing: bool = typer.Option(False, "--fail-on-missing", help="Exit with code 1 if source has keys not in target"),
):
    """Diff environment variables between two environments or .env files."""
    config = load_config(config_path)

    try:
        if source_file and target_file:
            result = diff_env_files(source_file, target_file)
            label_s, label_t = Path(source_file).name, Path(target_file).name
        else:
            src_path = source_file or config.get_env_path(source_env)
            tgt_path = target_file or config.get_env_path(target_env)
            result = diff_env_files(src_path, tgt_path)
            label_s, label_t = source_env, target_env
    except FileNotFoundError as e:
        err_console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(code=1) from None

    console.print(format_diff(result, label_s, label_t))

    if result.has_differences:
        console.print(f"\nTotal: {result.total_differences} difference(s)")

    if fail_on_missing and result.only_in_source:
        raise typer.Exit(1)

    raise typer.Exit(0)


@app.command()
def diff_files(
    file1: str = typer.Argument(..., help="First .env file"),
    file2: str = typer.Argument(..., help="Second .env file"),
    fail_on_missing: bool = typer.Option(False, "--fail-on-missing", help="Exit with code 1 if source has keys not in target"),
):
    """Diff two .env files directly (no config needed)."""
    try:
        result = diff_env_files(file1, file2)
    except FileNotFoundError as e:
        err_console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(code=1) from None
    console.print(format_diff(result, Path(file1).name, Path(file2).name))
    if result.has_differences:
        console.print(f"\nTotal: {result.total_differences} difference(s)")

    if fail_on_missing and result.only_in_source:
        raise typer.Exit(1)

    raise typer.Exit(0)


# ── Sync ────────────────────────────────────────────────────────────────────

@app.command()
def sync(
    source_env: str = typer.Argument("staging", help="Source environment"),
    target_env: str = typer.Argument("prod", help="Target environment"),
    strategy: str = typer.Option("source_wins", "--strategy", "-s",
                                  help="Conflict resolution: source_wins, target_wins, error"),
    allow_delete: bool = typer.Option(False, "--allow-delete", "-d", help="Delete keys not in source"),
    skip: list[str] | None = typer.Option(None, "--skip", help="Keys to skip"),
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
        console.print(f"[yellow]Dry run[/yellow] — would sync {source_env} → {target_env}:")
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
        console.print(f"[green]✓[/green] {source_env} and {target_env} are already in sync")
    else:
        console.print(f"[green]✓[/green] Synced {source_env} → {target_env}:")
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


# ── Rotate ──────────────────────────────────────────────────────────────────

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
            console.print(f"[yellow]Would rotate[/yellow] {key} → {new_value}")
        else:
            console.print(f"[yellow]Would rotate[/yellow] {key} (use --show to display)")
    else:
        console.print(f"[green]✓[/green] Rotated {key} in {env}")
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
        console.print(f"[green]✓[/green] Rotated {rotated} variables in {env}")


# ── Store Commands ──────────────────────────────────────────────────────────

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
    console.print(f"[green]✓[/green] Set {key}")


@store_app.command("delete")
def store_delete(
    key: str = typer.Argument(..., help="Key to delete"),
    store_name: str | None = typer.Option(None, "--store", "-s", help="Store name from config"),
    config_path: str = typer.Option("", "--config", "-c", help="Config file path"),
):
    """Delete a secret from a secret store."""
    config = load_config(config_path)

    if store_name and store_name in config.stores:
        store_instance = get_store(config.stores[store_name])
    else:
        store_instance = get_store(config_path)

    if store_instance.delete(key):
        console.print(f"[green]✓[/green] Deleted {key}")
    else:
        err_console.print(f"[red]Error:[/red] Key '{key}' not found in store")
        raise typer.Exit(1)


# ── Encrypt / Decrypt ──────────────────────────────────────────────────────────

@app.command()
def encrypt(
    input_file: Path = typer.Argument(..., help=".env file to encrypt", exists=True),
    output: Path | None = typer.Option(None, "--output", "-o", help="Output path (default: input.locked)"),
    password: str | None = typer.Option(None, "--password", "-p", help="Encryption password (prompted if omitted)"),
    delete_original: bool = typer.Option(False, "--delete", "-d", help="Delete original after encryption"),
):
    """Encrypt a .env file using Fernet symmetric encryption."""
    result = encrypt_env(input_file, output_path=output, password=password, delete_original=delete_original)
    console.print(f"[green]✓[/green] Encrypted → {result}")
    if delete_original:
        console.print(f"[yellow]🗑 Deleted original: {input_file}[/yellow]")


@app.command()
def decrypt(
    input_file: Path = typer.Argument(..., help=".env.locked file to decrypt", exists=True),
    output: Path | None = typer.Option(None, "--output", "-o", help="Output path (default: strips .locked)"),
    password: str | None = typer.Option(None, "--password", "-p", help="Decryption password (prompted if omitted)"),
    delete_encrypted: bool = typer.Option(False, "--delete", "-d", help="Delete encrypted file after decryption"),
):
    """Decrypt a .env.locked file."""
    result = decrypt_env(input_file, output, password, delete_encrypted)
    console.print(f"[green]✓[/green] Decrypted → {result}")
    if delete_encrypted:
        console.print(f"[yellow]🗑 Deleted encrypted: {input_file}[/yellow]")


# ── Audit ───────────────────────────────────────────────────────────────────

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


# ── Serve (HTTP API) ──────────────────────────────────────────────────────────

@app.command()
def serve(
    port: int = typer.Option(8080, "--port", "-p", help="Port to listen on"),
    host: str = typer.Option("127.0.0.1", "--host", "-H", help="Bind address (default: localhost only)"),
    password: str | None = typer.Option(None, "--password", "-k", help="Encryption password (prompted if omitted, or use ENVAULT_ENCRYPT_KEY)"),
    store: str | None = typer.Option(None, "--store", "-s", help="Named store from config to use"),
    config_path: str = typer.Option("", "--config", "-c", help="Config file path"),
    api_token: str | None = typer.Option(None, "--api-token", "-t", help="Bearer token for API auth (or set ENVAULT_API_TOKEN)"),
    api_key: str | None = typer.Option(None, "--api-key", help="API key for X-API-Key header auth (or set ENVAULT_API_KEY)"),
    auth_mode: str = typer.Option("bearer", "--auth-mode", help="Auth mode: bearer (default), api-key, oauth2, any"),
    oauth_introspect_url: str | None = typer.Option(None, "--oauth-introspect-url", help="OAuth2 token introspection endpoint URL (or set ENVAULT_OAUTH_INTROSPECT_URL)"),
    oauth_client_id: str | None = typer.Option(None, "--oauth-client-id", help="OAuth2 client ID for introspection (or set ENVAULT_OAUTH_CLIENT_ID)"),
    oauth_client_secret: str | None = typer.Option(None, "--oauth-client-secret", help="OAuth2 client secret for introspection (or set ENVAULT_OAUTH_CLIENT_SECRET)"),
):
    """Start an HTTP server that exposes decrypted secrets as a JSON API.

    Endpoints:

    GET /secrets — list all secret keys (auth required if any auth is configured)

    GET /secrets?prefix=X — filter keys by prefix

    GET /secrets/{key} — get decrypted value for a key

    GET /health — store connectivity check (no auth required)

    Authentication:

    --auth-mode bearer (default): Bearer token via --api-token / ENVAULT_API_TOKEN

    --auth-mode api-key: X-API-Key header via --api-key / ENVAULT_API_KEY

    --auth-mode oauth2: Bearer token validated via OAuth2 introspection (--oauth-introspect-url)

    --auth-mode any: Accept X-API-Key or Bearer token (tries X-API-Key first)
    """
    config = load_config(config_path)
    run_server(
        config, port=port, host=host, encrypt_key=password, store_name=store,
        api_token=api_token, api_key=api_key, auth_mode=auth_mode,
        oauth_introspect_url=oauth_introspect_url,
        oauth_client_id=oauth_client_id,
        oauth_client_secret=oauth_client_secret,
    )


# ── Version ─────────────────────────────────────────────────────────────────

@app.command()
def version():
    """Show version."""
    console.print(f"envault v{__version__}")


if __name__ == "__main__":
    app()
