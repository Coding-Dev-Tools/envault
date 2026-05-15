"""Configuration model for Envault — .envault.yml file parsing."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import yaml
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
    store: Optional[str] = Field(default=None, description="Secret store name to use")
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

    def save(self, path: str | Path = ".envault.yml"):
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

    def get_store(self, name: str) -> Optional[SecretStoreConfig]:
        return self.stores.get(name)


def init_config(project_name: str, path: str | Path = ".envault.yml") -> EnvaultConfig:
    """Initialize a new .envault.yml config file."""
    config = EnvaultConfig(project=project_name)
    config.save(path)
    return config
