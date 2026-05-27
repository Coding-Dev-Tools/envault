"""Configuration model for Envault — .envault.yml file parsing."""

from __future__ import annotations

import yaml
from pathlib import Path
from pydantic import BaseModel, Field


class SecretStoreConfig(BaseModel):
    """Configuration for a secret store integration."""

    type: str = Field(description="Store type: aws-ssm, vault, doppler, onepassword")
    path_prefix: str = Field(default="", description="Path/prefix for secrets in the store")
    auth_method: str = Field(default="env", description="Auth method: env, token, file")
    token_env_var: str = Field(default="", description="Env var name containing auth token")
    url: str = Field(default="", description="Store URL (for vault)")


class EnvironmentConfig(BaseModel):
    """Configuration for an environment."""

    name: str
    env_file: str = Field(default=".env", description="Path to .env file")
    store: str | None = Field(default=None, description="Secret store name to use")
    store_path: str = Field(default="", description="Path/prefix within the store")


class EnvaultConfig(BaseModel):
    """Root configuration model for .envault.yml."""

    project: str = Field(default="", description="Project name")
    version: str = Field(default="1", description="Config version")

    environments: list[EnvironmentConfig] = Field(default_factory=lambda: [
        EnvironmentConfig(name="dev", env_file=".env.dev"),
        EnvironmentConfig(name="staging", env_file=".env.staging"),
        EnvironmentConfig(name="prod", env_file=".env.prod"),
    ])

    stores: dict[str, SecretStoreConfig] = Field(default_factory=dict)
    audit_log_path: str = Field(default=".envault-audit.log")
    gitignore_patterns: list[str] = Field(default_factory=lambda: [".envault-audit.log"])

    @classmethod
    def load(cls, path: str | Path = ".envault.yml") -> EnvaultConfig:
        """Load config from a .envault.yml file, returning defaults if not found."""
        path = Path(path)
        if not path.exists():
            return cls()

        with open(path) as f:
            raw = yaml.safe_load(f)

        if not raw:
            return cls()

        return cls.model_validate(raw)

    def save(self, path: str | Path = ".envault.yml") -> None:
        """Save config to a .envault.yml file."""
        path = Path(path)
        with open(path, "w") as f:
            yaml.dump(self.model_dump(exclude_none=True), f, default_flow_style=False, sort_keys=False)

    def get_env_path(self, env_name: str) -> Path:
        """Get the path to the .env file for a given environment name."""
        for env in self.environments:
            if env.name == env_name:
                return Path(env.env_file)
        return Path(f".env.{env_name}")

    def get_env_names(self) -> list[str]:
        """Get list of environment names."""
        return [env.name for env in self.environments]

    def get_store(self, name: str) -> SecretStoreConfig | None:
        return self.stores.get(name)


def init_config(
    project_name: str,
    path: str | Path = ".envault.yml",
    generate_example: bool = True,
    example_path: str | Path = ".env.example",
    env_files: list[str | Path] | None = None,
) -> EnvaultConfig:
    """Initialize a new .envault.yml config file.

    If generate_example is True, also creates a .env.example file
    containing all keys found in existing .env files with blank values.
    """
    config = EnvaultConfig(project=project_name)
    config.save(path)

    if generate_example:
        _generate_env_example(config, example_path, env_files)

    return config


def _generate_env_example(
    config: EnvaultConfig,
    example_path: str | Path = ".env.example",
    extra_env_files: list[str | Path] | None = None,
) -> Path:
    """Generate a .env.example file with keys and blank values.

    Scans all .env files referenced in the config (plus any extra paths),
    collects every key, and writes them with empty values to example_path.
    """
    from envault.diff import load_env_file

    all_keys: set[str] = set()

    # Collect keys from config-referenced env files
    for env_cfg in config.environments:
        env_path = Path(env_cfg.env_file)
        if env_path.exists():
            vars = load_env_file(env_path)
            all_keys.update(vars.keys())

    # Collect keys from any extra .env files (e.g. .env itself)
    if extra_env_files:
        for fp in extra_env_files:
            p = Path(fp)
            if p.exists():
                vars = load_env_file(p)
                all_keys.update(vars.keys())

    # Also scan .env in CWD if not already covered
    default_env = Path(".env")
    if default_env.exists():
        vars = load_env_file(default_env)
        all_keys.update(vars.keys())

    example_path = Path(example_path)

    if not all_keys:
        # No keys found — don't create an empty example file
        return example_path

    with open(example_path, "w") as f:
        f.write("# Environment variable template — copy to .env and fill in values\n")
        for key in sorted(all_keys):
            f.write(f"{key}=\n")

    return example_path
