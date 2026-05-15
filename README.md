# Envault CLI

**Env variable syncing, diffing, and secret rotation — with secret-store integrations.**

![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)

Compare `.env` files across environments, sync variables with conflict resolution, and rotate secrets with auto-generation. Integrates with AWS SSM, HashiCorp Vault, Doppler, and 1Password.

## Quick Start

```bash
pip install envault

# Initialize a project
envault init my-project

# Diff environments
envault diff dev prod

# Sync staging → prod
envault sync staging prod

# Rotate a secret
envault rotate DB_PASSWORD
```

## Commands

### `envault init <project>`
Initialize a `.envault.yml` config file.

### `envault diff <source> <target>`
Diff environment variables between two environments. Shows keys that are:
- Only in source
- Only in target
- Present in both but with different values

```bash
envault diff dev staging
envault diff prod staging
envault diff-files .env.dev .env.prod
```

### `envault sync <source> <target>`
Sync environment variables from one environment to another.

```bash
# Sync staging → prod (source values win conflicts)
envault sync staging prod

# Dry run first
envault sync staging prod --dry-run

# Keep target values on conflict
envault sync staging prod --strategy target_wins

# Delete keys in target that don't exist in source
envault sync staging prod --allow-delete

# Skip certain keys
envault sync staging prod --skip DB_HOST --skip DB_PORT
```

### `envault rotate <key>`
Rotate a single environment variable with an auto-generated cryptographically secure value.

```bash
envault rotate DB_PASSWORD
envault rotate API_KEY --env prod
envault rotate JWT_SECRET --length 64 --dry-run --show
envault rotate-all --env prod
```

Smart rotation infers the type of secret:
- `DB_PASSWORD`, `DATABASE_URL` → database-safe password (no ambiguous chars)
- `API_KEY`, `STRIPE_SECRET` → prefixed API key
- `JWT_SECRET` → 256-bit base64 secret
- `WEBHOOK_SECRET` → long hex key
- Everything else → 32-char random string

### `envault store`

Manage secret store integrations.

```bash
envault store list
envault store list --prefix /production/
envault store get DB_PASSWORD --store my-vault
envault store set DB_PASSWORD new_value --store my-vault
```

## Configuration

Create a `.envault.yml` file in your project root:

```yaml
project: my-app
version: '1'

environments:
  - name: dev
    env_file: .env.dev
  - name: staging
    env_file: .env.staging
  - name: prod
    env_file: .env.prod

stores:
  production-secrets:
    type: aws-ssm
    path_prefix: /my-app/prod
  vault:
    type: vault
    url: https://vault.example.com:8200
    token_env_var: VAULT_TOKEN
    path_prefix: my-app/prod

audit_log_path: .envault-audit.log
```

## Secret Store Integrations

| Store | Package | Install |
|-------|---------|---------|
| AWS SSM | `boto3` | `pip install envault[awsssm]` |
| HashiCorp Vault | `hvac` | `pip install envault[vault]` |
| Doppler | `requests` | `pip install envault[doppler]` |
| 1Password | `onepasswordconnectsdk` | `pip install envault[onepassword]` |

## Audit Trail

All operations are logged to `.envault-audit.log` by default:

```bash
envault audit
envault audit --key DB_PASSWORD
envault audit --action rotate --limit 100
```

## Development

```bash
# Install in editable mode
pip install -e ".[dev]"

# Run tests
pytest

# Run tests with coverage
pytest --cov=envault
```

## License

MIT — Revenue Holdings
