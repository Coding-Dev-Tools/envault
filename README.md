# Envault CLI

[![GitHub stars](https://img.shields.io/github/stars/Coding-Dev-Tools/envault?style=social)](https://github.com/Coding-Dev-Tools/envault/stargazers)

**Environment variable syncing, diffing, and secret rotation — with secret-store integrations.**

[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](https://github.com/Coding-Dev-Tools/envault)
[![License](https://img.shields.io/github/license/Coding-Dev-Tools/envault)](https://github.com/Coding-Dev-Tools/envault/blob/main/LICENSE)
[![CI](https://github.com/Coding-Dev-Tools/envault/actions/workflows/ci.yml/badge.svg)](https://github.com/Coding-Dev-Tools/envault/actions/workflows/ci.yml)
[![Open Source Alternative](https://img.shields.io/badge/Open_Source_Alternative-%E2%87%92-blue?logo=opensourceinitiative)](https://www.opensourcealternative.to/project/envault)

> ⭐ **Star this repo** if you manage environment variables — it helps other developers find Envault!

**Why Envault?** Managing .env files across dev, staging, and prod is error-prone — copy-pasting secrets between environments, accidentally committing .env to git, rotating keys by hand across 5 files. Envault encrypts your .env files with a single master key, syncs them across environments, and rotates secrets without touching a text editor. One `envault push` encrypts and deploys. One `envault pull` decrypts and loads. No more plaintext secrets in .git history.

## Quick Start

> **Note:** rh-envault is not yet published to PyPI. Install directly from GitHub.

```bash
pip install git+https://github.com/Coding-Dev-Tools/envault.git

# Initialize a project
rh-envault init my-project

# Diff environments
rh-envault diff dev prod

# Sync staging → prod
rh-envault sync staging prod

# Rotate a secret
rh-envault rotate DB_PASSWORD
```

## Commands

### `rh-envault init <project>`

Initialize a `.envault.yml` config file with sensible defaults.

```bash
rh-envault init my-project
```

### `rh-envault diff <source> <target>`

Diff environment variables between two environments or `.env` files. Shows keys that are:
- Only in source
- Only in target
- Present in both but with different values

```bash
rh-envault diff dev staging
rh-envault diff prod staging
rh-envault diff-files .env.dev .env.prod
```

### `rh-envault sync <source> <target>`

Sync environment variables from one environment to another with conflict resolution strategies.

```bash
# Sync staging → prod (source values win conflicts)
rh-envault sync staging prod

# Dry run first
rh-envault sync staging prod --dry-run

# Keep target values on conflict
rh-envault sync staging prod --strategy target_wins

# Delete keys in target that don't exist in source
rh-envault sync staging prod --allow-delete

# Skip certain keys
rh-envault sync staging prod --skip DB_HOST --skip DB_PORT
```

### `rh-envault rotate <key>`

Rotate a single environment variable with an auto-generated cryptographically secure value.

```bash
rh-envault rotate DB_PASSWORD
rh-envault rotate API_KEY --env prod
rh-envault rotate JWT_SECRET --length 64 --dry-run --show
rh-envault rotate-all --env prod
```

Smart rotation infers the type of secret:
- `DB_PASSWORD`, `DATABASE_URL` → database-safe password (no ambiguous chars)
- `API_KEY`, `STRIPE_SECRET` → prefixed API key
- `JWT_SECRET` → 256-bit base64 secret
- `WEBHOOK_SECRET` → long hex key
- Everything else → 32-char random string

### `rh-envault store`

Manage secret store integrations — read, write, and list secrets from external stores.

```bash
rh-envault store list
rh-envault store list --prefix /production/
rh-envault store get DB_PASSWORD --store my-vault
rh-envault store set DB_PASSWORD new_value --store my-vault
rh-envault store delete DB_PASSWORD --store my-vault
```

### `rh-envault audit`

View the audit log of all diff, sync, and rotate operations.

```bash
rh-envault audit
rh-envault audit --key DB_PASSWORD
rh-envault audit --action rotate --limit 100
```

### `rh-envault serve`

Start an HTTP server that exposes decrypted secrets as a JSON API — ideal for MCP server sidecars, CI/CD pipelines, and AI agent runtimes.

```bash
# Start the secrets API on port 8080 (default)
rh-envault serve

# Custom port, host, and API key
rh-envault serve --port 3000 --host 0.0.0.0 --api-key my-bearer-token

# Use a named store from config
rh-envault serve --store production-secrets
```

**Endpoints:**

| Endpoint | Auth | Description |
|----------|------|-------------|
| `GET /health` | No | Store connectivity check |
| `GET /secrets` | Yes | List all secret keys (filter with `?prefix=X`) |
| `GET /secrets/{key}` | Yes | Get decrypted value for a key |

**Security:**
- Defaults to `127.0.0.1` (localhost only) — use `--host 0.0.0.0` only behind a firewall or reverse proxy
- Set `--api-key` or `ENVAULT_API_KEY` env var to require Bearer token auth on `/secrets` endpoints
- No built-in TLS — run behind a reverse proxy (nginx, Caddy) for HTTPS in production

```bash
# Fetch secrets with curl
curl -H "Authorization: Bearer my-token" http://localhost:8080/secrets

# Filter by prefix
curl -H "Authorization: Bearer my-token" "http://localhost:8080/secrets?prefix=STRIPE"

# Get a specific secret
curl -H "Authorization: Bearer my-token" http://localhost:8080/secrets/DB_PASSWORD
```

## Features

- **Environment diffing** — compare variables between any two environments with colorized output
- **Conflict resolution** — choose source-wins, target-wins, or interactive merge strategies
- **Smart secret rotation** — auto-detects secret type (DB password, API key, JWT, webhook) and generates appropriate values
- **Bulk rotation** — `rotate-all` with per-key dry-run preview
- **Secret store integration** — AWS SSM, HashiCorp Vault, Doppler, 1Password
- **Secrets HTTP API** — `serve` exposes decrypted secrets over HTTP with Bearer token auth for MCP sidecars, CI/CD, and agent runtimes
- **Audit trail** — every operation logged to `.envault-audit.log` with queryable CLI
- **Configuration as code** — `.envault.yml` is team-shareable and Git-friendly

## Pricing

Envault is one of 11 tools in the Revenue Holdings suite. One license covers all CLI tools.

| Plan | Price | Best For |
|------|-------|----------|
| **Free** | $0 | Individual devs, OSS — CLI only, rate-limited |
| **Envault Individual** | **$12/mo** ($10 billed annually) | Professional devs — unlimited syncs, secret stores, audit |
| **Suite (all 11 tools)** | **$49/mo** ($39 billed annually) | Full Revenue Holdings toolkit — 40% savings |
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

| Store | Package | Install (from GitHub) |
|-------|---------|----------------------|
| AWS SSM | `boto3` | `pip install "rh-envault[awsssm] @ git+https://..."` |
| HashiCorp Vault | `hvac` | `pip install "rh-envault[vault] @ git+https://..."` |
| Doppler | `requests` | `pip install "rh-envault[doppler] @ git+https://..."` |
| 1Password | `onepasswordconnectsdk` | `pip install "rh-envault[onepassword] @ git+https://..."` |

## CI/CD Integration

```bash
# Block deployment if production has secrets that staging doesn't
rh-envault diff staging prod --fail-on-missing

# Rotate a secret and sync to all environments
rh-envault rotate DB_PASSWORD --env staging
rh-envault sync staging prod

# Audit before deployment
rh-envault audit --action rotate --limit 20
```

## Storage

Configuration and audit logs are stored in the project root and `~/.envault/`:
- `.envault.yml` — project configuration (Git-friendly)
- `.envault-audit.log` — audit trail (append-only)

## Roadmap

- [ ] Interactive merge for conflict resolution
- [ ] Vault OIDC auth
- [ ] GitOps mode — sync from Git-based config repos
- [x] ~~MCP server for AI-assisted env management~~ → `envault serve` (HTTP API, see above)
- [ ] Docker-based CLI image
- [ ] Terraform provider for secret provisioning

## License

MIT — see [LICENSE](LICENSE)

---

<sub>Part of [Revenue Holdings](https://coding-dev-tools.github.io/revenueholdings.dev/) — a suite of 11 developer CLI tools built by autonomous AI agents. Also check out [API Contract Guardian](https://github.com/Coding-Dev-Tools/api-contract-guardian) (breaking change detection), [DeployDiff](https://github.com/Coding-Dev-Tools/deploydiff) (infrastructure diffs), [json2sql](https://github.com/Coding-Dev-Tools/json2sql) (JSON → SQL), [ConfigDrift](https://github.com/Coding-Dev-Tools/configdrift) (config drift detection), [DeadCode](https://github.com/Coding-Dev-Tools/deadcode) (dead code cleanup), [APIAuth](https://github.com/Coding-Dev-Tools/apiauth) (API key management), [APIGhost](https://github.com/Coding-Dev-Tools/apighost) (mock API server), [SchemaForge](https://github.com/Coding-Dev-Tools/schemaforge) (ORM converter), [click-to-mcp](https://github.com/Coding-Dev-Tools/click-to-mcp) (CLI → MCP server), and [DataMorph](https://github.com/Coding-Dev-Tools/datamorph) (data format conversion).</sub>
