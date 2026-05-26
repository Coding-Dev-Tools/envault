# Using Envault in GitHub Actions for Secure CI/CD

Managing environment variables and secrets in CI/CD pipelines is one of the most common security challenges in modern development. Hardcoding secrets in workflow files, committing .env files to repositories, or managing separate secret sets for each environment creates significant risks. Envault solves this by providing encrypted, version-controlled environment management that integrates seamlessly with GitHub Actions.

## Why Envault for GitHub Actions?

Traditional approaches to CI/CD secret management suffer from several problems:
- Secrets scattered across repository secrets, workflow files, and .env files
- No visibility into what changed between environments
- Difficult rotation without breaking pipelines
- No audit trail of who accessed or modified secrets

Envault addresses these by:
- Encrypting environment files with a single master key
- Providing clear diff, sync, and rotation capabilities
- Integrating with external secret stores (AWS SSM, HashiCorp Vault, etc.)
- Maintaining an audit trail of all operations
- Working completely offline on the free tier

## Setting Up Envault for GitHub Actions

### 1. Initialize Envault in Your Repository

First, install Envault and initialize it in your project:

```bash
# Install from GitHub (since not yet on PyPI)
pip install git+https://github.com/Coding-Dev-Tools/envault.git

# Initialize Envault (creates .envault.yml)
rh-envault init my-project

# This creates a .envault.yml file with:
# project: my-project
# version: '1'
# environments:
#   - name: dev
#     env_file: .env.dev
#   - name: staging
#     env_file: .env.staging
#   - name: prod
#     env_file: .env.prod
```

### 2. Configure Your Environments

Create environment-specific .env files:

```bash
# .env.dev
DATABASE_URL=postgresql://localhost/dev_db
API_KEY=dev_key_123
DEBUG=true

# .env.staging  
DATABASE_URL=postgresql://staging-db.company.com/staging_db
API_KEY=staging_key_456
DEBUG=false

# .env.prod
DATABASE_URL=postgresql://prod-db.company.com/prod_db
API_KEY=prod_key_789
DEBUG=false
```

### 3. Encrypt Your Environment Files

Encrypt your environment files with a master key:

```bash
# First time encryption - you'll be prompted for a master key
rh-envault encrypt

# This creates encrypted versions:
# .env.dev.enc
# .env.staging.enc  
# .env.prod.enc

# Add the encrypted files to git (they're safe to commit)
git add .env.*.enc
git commit -m "Add encrypted environment files"

# Add the master key to GitHub Secrets
# Go to Settings > Secrets and variables > Actions > New repository secret
# Name: ENVAULT_KEY
# Value: [your master key from the encryption prompt]
```

## Using Envault in GitHub Actions Workflows

Here's a complete GitHub Actions workflow that uses Envault for secure deployment:

```yaml
name: Deploy to Production

on:
  push:
    branches: [ main ]

jobs:
  deploy:
    runs-on: ubuntu-latest
    environment: production
    
    steps:
    - uses: actions/checkout@v4
    
    - name: Set up Python
      uses: actions/setup-python@v5
      with:
        python-version: '3.10'
        
    - name: Install Envault
      run: |
        pip install git+https://github.com/Coding-Dev-Tools/envault.git
        
    - name: Decrypt Environment
      env:
        ENVAULT_KEY: ${{ secrets.ENVAULT_KEY }}
      run: |
        # Decrypt only the production environment
        rh-envault decrypt prod --env-file .env.prod
        
    - name: Verify Environment (Optional)
      run: |
        # Check that we have the right variables without showing values
        rh-envault diff-files .env.prod.example .env.prod --fail-on-missing
        
    - name: Deploy Application
      env:
        # Load variables from decrypted .env file
        DATABASE_URL: ${{ env.DATABASE_URL }}
        API_KEY: ${{ env.API_KEY }}
        DEBUG: ${{ env.DEBUG }}
      run: |
        # Your deployment commands here
        echo "Deploying to production..."
        # Example: docker-compose up -d
        # Example: ./deploy.sh
        
    - name: Clean Up
      if: always()
      run: |
        # Remove decrypted file for security
        rm -f .env.prod
```

### Advanced: Using Envault with External Secret Stores

For even better security, integrate with external secret stores like AWS SSM or HashiCorp Vault:

```yaml
# .envault.yml with AWS SSM integration
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
    region: us-east-1

audit_log_path: .envault-audit.log
```

Then in your workflow:

```yaml
- name: Sync from AWS SSM
  env:
    AWS_ACCESS_KEY_ID: ${{ secrets.AWS_ACCESS_KEY_ID }}
    AWS_SECRET_ACCESS_KEY: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
    ENVAULT_KEY: ${{ secrets.ENVAULT_KEY }}
  run: |
    # Pull latest secrets from AWS SSM, decrypt local env, then sync
    rh-envault store get --store production-secrets --prefix /my-app/prod/
    rh-envault decrypt prod
    rh-envault sync production-secrets prod --strategy target_wins
```

## Best Practices for Envault in CI/CD

1. **Use Environment Protection Rules**: Configure GitHub Environments with required reviewers and wait timers for production deployments.

2. **Implement Drift Detection**: Add a step to check for configuration drift before deployment:
   ```yaml
   - name: Check for Drift
     run: |
       rh-envault diff staging prod --fail-on-missing
   ```

3. **Rotate Secrets Regularly**: Schedule regular secret rotation:
   ```yaml
   name: Monthly Secret Rotation
   
   on:
     schedule:
       - cron: '0 0 1 * *'  # First day of every month
   
   jobs:
     rotate:
       runs-on: ubuntu-latest
       steps:
         - uses: actions/checkout@v4
         - name: Install Envault
           run: pip install git+https://github.com/Coding-Dev-Tools/envault.git
         - name: Rotate Production Secrets
           env:
             ENVAULT_KEY: ${{ secrets.ENVAULT_KEY }}
           run: |
             rh-envault rotate DB_PASSWORD --env prod
             rh-encault rotate API_KEY --env prod
             # Commit updated encrypted files
             git config --local user.email "action@github.com"
             git config --local user.name "GitHub Action"
             git add .env.*.enc
             git commit -m "chore: rotate production secrets [skip ci]"
             git push
   ```

4. **Audit Access**: Regularly review the audit trail:
   ```yaml
   - name: Audit Check
     run: |
       rh-envault audit --limit 50
   ```

## Benefits of This Approach

- **Security**: Secrets never exist in plaintext in your repository or logs
- **Visibility**: Clear diffs show exactly what changed between environments
- **Auditability**: Every encryption, decryption, sync, and rotation is logged
- **Portability**: Works the same way locally and in CI/CD
- **Flexibility**: Can integrate with external secret stores or work completely offline
- **Team Friendly**: Configuration is stored in plaintext .envault.yml (safe to commit)

## Getting Started

1. Install Envault: `pip install git+https://github.com/Coding-Dev-Tools/envault.git`
2. Initialize: `rh-envault init my-project`
3. Create environment files (.env.dev, .env.staging, .env.prod)
4. Encrypt: `rh-envault encrypt` (save the master key to GitHub Secrets)
5. Add the workflow template above to `.github/workflows/deploy.yml`
6. Add your master key to repository secrets as `ENVAULT_KEY`

Envault transforms environment variable management from a security liability into a controlled, auditable process that gives you confidence in your deployments while maintaining the simplicity developers expect from CLI tools.

> Envault is part of the Revenue Holdings suite of 11 developer CLI tools built by autonomous AI agents. Each tool solves a specific development challenge with a focus on security, simplicity, and CI/CD integration.