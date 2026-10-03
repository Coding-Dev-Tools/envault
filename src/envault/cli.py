"""Main CLI entrypoint for Envault."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.prompt import Confirm
from rich.table import Table

from envault import __version__
from envault.audit import AuditLogger
from envault.backup import (
    backup_env_file,
    format_backup_list,
    list_backups,
    restore_backup,
)
from envault.config import EnvaultConfig, init_config
from envault.diff import diff_env_files, format_diff
from envault.encrypt import decrypt_env, encrypt_env
from envault.history import format_history, get_env_history
from envault.rotate import rotate_env_file, rotate_env_var
from envault.security_audit import (
    SecurityAuditResult,
    audit_env_file,
    format_audit_report,
)
from envault.serve import run_server
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
    existing_env_files: list[str | Path] = []
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
    fail_on_missing: bool = typer.Option(
        False,
        "--fail-on-missing",
        help="Exit with code 1 if source has keys not in target",
    ),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
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

    if json_output:
        print(result.to_json(source_label=label_s, target_label=label_t))
    else:
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
    fail_on_missing: bool = typer.Option(
        False,
        "--fail-on-missing",
        help="Exit with code 1 if source has keys not in target",
    ),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
):
    """Diff two .env files directly (no config needed)."""
    if not Path(file1).exists():
        err_console.print(f"[red]Error:[/red] File not found: {file1}")
        raise typer.Exit(1)
    if not Path(file2).exists():
        err_console.print(f"[red]Error:[/red] File not found: {file2}")
        raise typer.Exit(1)
    result = diff_env_files(file1, file2)
    if json_output:
        print(result.to_json(source_label=Path(file1).name, target_label=Path(file2).name))
    else:
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
    strategy: str = typer.Option(
        "source_wins",
        "--strategy",
        "-s",
        help="Conflict resolution: source_wins, target_wins, error",
    ),
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

        result = sync_envs(
            source_vars,
            target_vars,
            strategy=strategy,
            allow_delete=allow_delete,
            skip_keys=skip_keys,
        )
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
        src_path,
        tgt_path,
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
            console.print(
                f"  + Added: {', '.join(result.added[:10])}"
                + (f" +{len(result.added) - 10}" if len(result.added) > 10 else "")
            )
        if result.updated:
            console.print(
                f"  ~ Updated: {', '.join(result.updated[:10])}"
                + (f" +{len(result.updated) - 10}" if len(result.updated) > 10 else "")
            )
        if result.deleted:
            console.print(f"  - Deleted: {', '.join(result.deleted)}")
        if result.skipped:
            console.print(
                f"  - Skipped: {', '.join(result.skipped[:10])}"
                + (f" +{len(result.skipped) - 10}" if len(result.skipped) > 10 else "")
            )


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
        key,
        env_file,
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

    new_values = rotate_env_file(
        env_file,
        dry_run=dry_run,
        audit=audit,
    )
    rotated = len(new_values)

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
    result = encrypt_env(
        input_file,
        output_path=output,
        password=password,
        delete_original=delete_original,
    )
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


# ── Security Scan ──────────────────────────────────────────────────────────


@app.command()
def scan(
    files: list[str] = typer.Argument(..., help="One or more .env files to scan"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show info-level findings and suggestions"),
    json_output: bool = typer.Option(False, "--json", help="Output results as JSON"),
    no_permissions: bool = typer.Option(False, "--no-permissions", help="Skip file permission checks"),
    no_gitignore: bool = typer.Option(False, "--no-gitignore", help="Skip .gitignore checks"),
    config_path: str = typer.Option("", "--config", "-c", help="Config file path"),
):
    """Scan .env files for security issues (weak secrets, hardcoded credentials, permissions, gitignore)."""
    results: list[SecurityAuditResult] = []
    for f in files:
        result = audit_env_file(
            f,
            check_permissions=not no_permissions,
            check_gitignore=not no_gitignore,
        )
        results.append(result)

    if json_output:
        import json as _json

        output = []
        for r in results:
            entry = {
                "file": r.file_path,
                "pass_fail": r.pass_fail,
                "total_issues": r.total_issues,
                "critical": r.critical_count,
                "high": r.high_count,
                "medium": r.medium_count,
                "low": r.low_count,
                "info": r.info_count,
                "issues": [
                    {
                        "severity": i.severity,
                        "category": i.category,
                        "key": i.key,
                        "message": i.message,
                        "suggestion": i.suggestion,
                    }
                    for i in r.sorted_issues()
                ],
            }
            output.append(entry)
        print(_json.dumps(output, indent=2))
    else:
        report = format_audit_report(results, verbose=verbose)
        console.print(report)

    # Exit with non-zero code if critical or high issues found
    if any(r.has_critical_or_high for r in results):
        raise typer.Exit(1)


# ── History ──────────────────────────────────────────────────────────────────


@app.command()
def history(
    env: str = typer.Argument("dev", help="Environment name from config"),
    file: str | None = typer.Option(None, "--file", "-f", help="Direct .env file path (overrides env name)"),
    key: str | None = typer.Option(None, "--key", "-k", help="Filter changes to a specific key"),
    max_commits: int = typer.Option(50, "--max-commits", "-n", help="Maximum number of commits to inspect"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show old/new values in output"),
    json_output: bool = typer.Option(False, "--json", help="Output result as JSON for programmatic use"),
    config_path: str = typer.Option("", "--config", "-c", help="Config file path"),
):
    """Show git change history for an .env file.

    Walks the git log for the given .env file and shows each key-level
    change (added, removed, changed) per commit.
    """
    config = load_config(config_path)

    env_file = Path(file) if file else config.get_env_path(env)

    if not env_file.exists():
        err_console.print(f"[red]Error:[/red] Environment file '{env_file}' not found")
        raise typer.Exit(1)

    result = get_env_history(
        env_file,
        max_commits=max_commits,
        key_filter=key,
    )

    if json_output:
        print(result.to_json(mask_values=not verbose))
    else:
        console.print(format_history(result, verbose=verbose))


# ── Backup ───────────────────────────────────────────────────────────────────

backup_app = typer.Typer(name="backup", help="Backup and restore .env files.")
app.add_typer(backup_app)


@backup_app.command("create")
def backup_create(
    env: str | None = typer.Argument(None, help="Environment name from config"),
    file: str | None = typer.Option(None, "--file", "-f", help="Direct .env file path (overrides env name)"),
    all_envs: bool = typer.Option(False, "--all", "-a", help="Backup all configured environments"),
    encrypt: bool = typer.Option(False, "--encrypt", "-e", help="Encrypt backup with Fernet"),
    password: str | None = typer.Option(None, "--password", "-p", help="Encryption password (prompted if omitted)"),
    json_output: bool = typer.Option(False, "--json", help="Output result as JSON"),
    config_path: str = typer.Option("", "--config", "-c", help="Config file path"),
):
    """Create an encrypted backup of .env file(s)."""
    config = load_config(config_path)

    files_to_backup: list[Path] = []

    if all_envs:
        for env_cfg in config.environments:
            p = Path(env_cfg.env_file)
            if p.exists():
                files_to_backup.append(p)
            else:
                err_console.print(f"[yellow]⚠[/yellow] Skipping {env_cfg.name}: file '{p}' not found")
    elif file:
        files_to_backup.append(Path(file))
    elif env:
        files_to_backup.append(config.get_env_path(env))
    else:
        err_console.print("[red]Error:[/red] Provide --env, --file, or --all")
        raise typer.Exit(1)

    from envault.backup import BackupResult

    result = BackupResult()

    for f in files_to_backup:
        try:
            entry = backup_env_file(f, encrypt=encrypt, password=password)
            result.backups.append(entry)
        except FileNotFoundError as e:
            result.errors.append(str(e))
        except Exception as e:
            result.errors.append(str(e))

    if json_output:
        print(result.to_json())
    else:
        for entry in result.backups:
            enc_tag = " (encrypted)" if entry.encrypted else ""
            console.print(f"[green]✓[/green] Backed up {entry.source_file}{enc_tag} → {entry.backup_path}")
        for err in result.errors:
            err_console.print(f"[red]Error:[/red] {err}")

    if result.errors:
        raise typer.Exit(1)


@backup_app.command("list")
def backup_list(
    json_output: bool = typer.Option(False, "--json", help="Output result as JSON"),
    config_path: str = typer.Option("", "--config", "-c", help="Config file path"),
):
    """List existing backups."""
    entries = list_backups()

    if json_output:
        import json

        print(json.dumps([e.to_dict() for e in entries], indent=2))
    else:
        if not entries:
            console.print("[yellow]No backups found[/yellow]")
            raise typer.Exit(0)

        console.print(format_backup_list(entries))
        console.print(f"\n{len(entries)} backup(s) in .envault-backups/")


@backup_app.command("restore")
def backup_restore(
    name: str = typer.Argument(..., help="Backup name to restore"),
    target: str | None = typer.Option(None, "--target", "-t", help="Target file path (defaults to original)"),
    password: str | None = typer.Option(None, "--password", "-p", help="Decryption password (prompted if omitted)"),
    json_output: bool = typer.Option(False, "--json", help="Output result as JSON"),
    config_path: str = typer.Option("", "--config", "-c", help="Config file path"),
):
    """Restore a backup by name."""
    try:
        restored_path = restore_backup(name, target_path=target, password=password)
        if json_output:
            import json

            print(json.dumps({"restored_to": str(restored_path)}))
        else:
            console.print(f"[green]✓[/green] Restored → {restored_path}")
    except ValueError as e:
        err_console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from e
    except FileNotFoundError as e:
        err_console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from e


# ── Serve (HTTP API) ──────────────────────────────────────────────────────────


@app.command()
def serve(
    port: int = typer.Option(8080, "--port", "-p", help="Port to listen on"),
    host: str = typer.Option("127.0.0.1", "--host", "-H", help="Bind address (default: localhost only)"),
    password: str | None = typer.Option(
        None,
        "--password",
        "-k",
        help="Encryption password (prompted if omitted, or use ENVAULT_ENCRYPT_KEY)",
    ),
    api_key: str | None = typer.Option(None, "--api-key", help="Bearer token for API auth (or set ENVAULT_API_KEY)"),
    store: str | None = typer.Option(None, "--store", "-s", help="Named store from config to use"),
    config_path: str = typer.Option("", "--config", "-c", help="Config file path"),
    api_token: str | None = typer.Option(
        None,
        "--api-token",
        "-t",
        help="Bearer token for API auth (or set ENVAULT_API_TOKEN)",
    ),
):
    """Start an HTTP server that exposes decrypted secrets as a JSON API.

       Endpoints:

    GET /secrets — list all secret keys

    GET /secrets?prefix=X — filter keys by prefix

    GET /secrets/{key} — get decrypted value for a key

    GET /health — store connectivity check

       Security:
    - Default bind is 127.0.0.1 (localhost only); use --host 0.0.0.0 to expose.
    - Set --api-key or ENVAULT_API_KEY to require Bearer token auth on /secrets.
    """
    config = load_config(config_path)
    run_server(
        config,
        port=port,
        host=host,
        encrypt_key=password,
        store_name=store,
        api_key=api_key,
    )


# ── Version ─────────────────────────────────────────────────────────────────


@app.command()
def version() -> None:
    """Show version."""
    print(f"envault v{__version__}")


if __name__ == "__main__":
    app()
