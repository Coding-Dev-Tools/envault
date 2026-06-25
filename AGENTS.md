# envault — AGENTS.md

## Overview
CLI for environment variable syncing, diffing, and secret rotation with integrations for HashiCorp Vault, AWS SSM, Doppler, and 1Password.

## Quick Start
```bash
pip install -e ".[dev]"
rh-envault --help
```

## Commands
| Command | Description |
|---------|-------------|
| `rh-envault sync` | Sync env vars between local .env and remote stores |
| `rh-envault diff` | Diff two env sources |
| `rh-envault rotate` | Rotate secrets in configured stores |
| `rh-envault audit` | Audit local env files for secrets |
| `rh-envault serve` | Run local HTTP server for env access |
| `rh-envault encrypt` | Encrypt/decrypt values |

## Development
```bash
# Install dev deps
pip install -e ".[dev]"

# Run tests
python -m pytest tests/ -v --tb=short

# Lint
ruff check src/ --target-version py310

# Type check (if mypy configured)
mypy src/
```

## CI/CD
- GitHub Actions: `.github/workflows/ci.yml` (test matrix: 3.11, 3.12, 3.13)
- Publish: `.github/workflows/publish.yml` (PyPI on tag)
- Pages: `.github/workflows/pages.yml` (docs deploy)

## Structure
```
src/envault/
├── cli.py          # Typer CLI entry point
├── config.py       # Configuration loading
├── sync.py         # Sync logic
├── diff.py         # Diff logic
├── rotate.py       # Rotation logic
├── audit.py        # Secret scanning
├── encrypt.py      # Encryption utilities
├── serve.py        # HTTP server
└── stores/         # Backend integrations
    ├── __init__.py
    ├── vault.py
    ├── awsssm.py
    ├── doppler.py
    └── onepassword.py
```

## Dependencies
- Core: typer, rich, python-dotenv, pyyaml, cryptography, pydantic
- Optional: hvac (Vault), boto3 (AWS SSM), requests (Doppler), onepasswordconnectsdk (1Password)
- Dev: pytest, pytest-cov, responses, ruff

## Testing
```bash
pytest tests/ -v --tb=short
pytest tests/test_cli.py -v
pytest tests/test_encrypt_secret_formats.py -v
```

## Security
- Never commit `.env.*` files (gitignored)
- Audit log at `.envault-audit.log` (gitignored)
- Rotate secrets via `rh-envault rotate` command