# Envault CLI

**Environment variable syncing, diffing, and secret rotation — with secret-store integrations.**

[![PyPI](https://img.shields.io/pypi/v/envault)](https://pypi.org/project/envault/)
[![Python](https://img.shields.io/pypi/pyversions/envault)](https://pypi.org/project/envault/)
[![License](https://img.shields.io/pypi/l/envault)](https://github.com/Coding-Dev-Tools/envault/blob/main/LICENSE)
[![CI](https://github.com/Coding-Dev-Tools/envault/actions/workflows/test.yml/badge.svg)](https://github.com/Coding-Dev-Tools/envault/actions/workflows/test.yml)

**Why Envault?** Every team with more than one environment has been burned by a stale `.env.prod`, a secret that was rotated last month and nobody remembers, or a deployment that broke because `STAGING_DB_URL` pointed to production. Envault gives you a single CLI to diff environments, sync with conflict resolution, rotate secrets with smart type inference, and integrate with AWS SSM, HashiCorp Vault, Doppler, and 1Password — all from your terminal.

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

Initialize a `.envault.yml` config file with sensible defaults.

```bash
envault init my-project
```

### `envault diff <source> <target>`

Diff environment variables between two environments or `.env` files. Shows keys that are:
- Only in source
- Only in target
- Present in both but with different values

```bash
envault diff dev staging
envault diff prod staging
envault diff-files .env.dev .env.prod
```

### `envault sync <source> <target>`

Sync environment variables from one environment to another with conflict resolution strategies.

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

Manage secret store integrations — read, write, and list secrets from external stores.

```bash
envault store list
envault store list --prefix /production/
envault store get DB_PASSWORD --store my-vault
envault store set DB_PASSWORD new_value --store my-vault
```

### `envault audit`

View the audit log of all diff, sync, and rotate operations.

```bash
envault audit
envault audit --key DB_PASSWORD
envault audit --action rotate --limit 100
```

## Features

- **Environment diffing** — compare variables between any two environments with colorized output
- **Conflict resolution** — choose source-wins, target-wins, or interactive merge strategies
- **Smart secret rotation** — auto-detects secret type (DB password, API key, JWT, webhook) and generates appropriate values
- **Bulk rotation** — `rotate-all` with per-key dry-run preview
- **Secret store integration** — AWS SSM, HashiCorp Vault, Doppler, 1Password
- **Audit trail** — every operation logged to `.envault-audit.log` with queryable CLI
- **Configuration as code** — `.envault.yml` is team-shareable and Git-friendly

## Pricing

Envault is one of eight tools in the Revenue Holdings suite. One license covers all CLI tools.

| Plan | Price | Best For |
|------|-------|----------|
| **Free** | $0 | Individual devs, OSS — CLI only, rate-limited |
| **Envault Individual** | **$12/mo** ($10 billed annually) | Professional devs — unlimited syncs, secret stores, audit |
| **Suite (all 8 tools)** | **$49/mo** ($39 billed annually) | Full Revenue Holdings toolkit — 40% savings |
| **Team** | **$79/mo** ($63 billed annually) | Up to 5 devs — shared configs, team dashboard, alerts |
| **Enterprise** | Custom | SSO, RBAC, compliance reports, dedicated support |

🔹 **No lock-in**: CLI works fully offline on the free tier — no telemetry, no phone-home.
🔹 **Annual billing**: Save 20%.

### Per-Tier Features

| Feature | Free | Individual | Suite | Team | Enterprise |
|---------|:----:|:----------:|:-----:|:----:|:----------:|
| CLI: diff, sync, rotate | ✓ | ✓ | ✓ | ✓ | ✓ |
| Conflict resolution strategies | — | ✓ | ✓ | ✓ | ✓ |
| Smart secret type inference | — | ✓ | ✓ | ✓ | ✓ |
| Secret store integrations | — | ✓ | ✓ | ✓ | ✓ |
| Secret store integrations | 1 store | Unlimited | Unlimited | Unlimited | Unlimited |
| Audit trail & query | 7 days | Unlimited | Unlimited | Unlimited | Unlimited |
| Bulk rotate-all | — | ✓ | ✓ | ✓ | ✓ |
| Team shared configs | — | — | — | ✓ | ✓ |
| Dashboard & analytics | — | — | — | ✓ | ✓ |
| Compliance reports | — | — | — | — | ✓ |
| RBAC / SSO / SAML / OIDC | — | — | — | — | ✓ |
| Priority support | Community | 24h | 24h | 8h | Dedicated |

---

<p align="center">
  <sub>Part of <a href="https://coding-dev-tools.github.io/revenueholdings.dev/">Revenue Holdings</a> — CLI tools built by autonomous AI.</sub>
</p>

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

## CI/CD Integration

```bash
# Block deployment if production has secrets that staging doesn't
envault diff staging prod --fail-on-missing

# Rotate a secret and sync to all environments
envault rotate DB_PASSWORD --env staging
envault sync staging prod

# Audit before deployment
envault audit --action rotate --limit 20
```

## Storage

Configuration and audit logs are stored in the project root and `~/.envault/`:
- `.envault.yml` — project configuration (Git-friendly)
- `.envault-audit.log` — audit trail (append-only)

## Roadmap

- [ ] Interactive merge for conflict resolution
- [ ] Vault OIDC auth
- [ ] GitOps mode — sync from Git-based config repos
- [ ] MCP server for AI-assisted env management
- [ ] Docker-based CLI image
- [ ] Terraform provider for secret provisioning

## License

MIT — see [LICENSE](LICENSE)

---

<sub>Part of [Revenue Holdings](https://coding-dev-tools.github.io/revenueholdings.dev/) — a suite of 10 developer CLI tools built by autonomous AI agents. Also check out [API Contract Guardian](https://github.com/Coding-Dev-Tools/api-contract-guardian) (breaking change detection), [DeployDiff](https://github.com/Coding-Dev-Tools/deploydiff) (infrastructure diffs), [json2sql](https://github.com/Coding-Dev-Tools/json2sql) (JSON → SQL), [ConfigDrift](https://github.com/Coding-Dev-Tools/configdrift) (config drift detection), [DeadCode](https://github.com/Coding-Dev-Tools/deadcode) (dead code cleanup), [APIAuth](https://github.com/Coding-Dev-Tools/apiauth) (API key management), [APIGhost](https://github.com/Coding-Dev-Tools/apighost) (mock API server), [SchemaForge](https://github.com/Coding-Dev-Tools/schemaforge) (ORM converter), and [click-to-mcp](https://github.com/Coding-Dev-Tools/click-to-mcp) (CLI → MCP server).</sub>
