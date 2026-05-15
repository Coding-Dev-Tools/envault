"""Secret store integrations for Envault — base class and implementations."""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional


class SecretStoreError(Exception):
    """Base exception for secret store operations."""
    pass


class SecretStore(ABC):
    """Abstract base class for secret store integrations."""

    @abstractmethod
    def get(self, key: str) -> Optional[str]:
        """Get a secret by key."""
        ...

    @abstractmethod
    def set(self, key: str, value: str) -> bool:
        """Set a secret by key."""
        ...

    @abstractmethod
    def delete(self, key: str) -> bool:
        """Delete a secret by key."""
        ...

    @abstractmethod
    def list_keys(self, prefix: str = "") -> list[str]:
        """List all keys, optionally filtered by prefix."""
        ...

    def get_many(self, keys: list[str]) -> dict[str, str]:
        """Get multiple secrets at once."""
        result = {}
        for key in keys:
            value = self.get(key)
            if value is not None:
                result[key] = value
        return result

    def set_many(self, secrets: dict[str, str]) -> int:
        """Set multiple secrets at once. Returns count of successful sets."""
        count = 0
        for key, value in secrets.items():
            if self.set(key, value):
                count += 1
        return count


class LocalEnvStore(SecretStore):
    """Local .env file as a secret store."""

    def __init__(self, env_file: str | Path = ".env"):
        self.env_file = Path(env_file)
        self._cache: Optional[dict[str, str]] = None

    def _load(self) -> dict[str, str]:
        if self._cache is not None:
            return self._cache
        from envault.diff import load_env_file
        self._cache = load_env_file(self.env_file)
        return self._cache

    def _invalidate(self):
        self._cache = None

    def get(self, key: str) -> Optional[str]:
        return self._load().get(key)

    def set(self, key: str, value: str) -> bool:
        from envault.diff import load_env_file
        from envault.sync import write_env_file

        env_vars = load_env_file(self.env_file)
        env_vars[key] = value
        write_env_file(self.env_file, env_vars)
        self._invalidate()
        return True

    def delete(self, key: str) -> bool:
        from envault.diff import load_env_file
        from envault.sync import write_env_file

        env_vars = load_env_file(self.env_file)
        if key in env_vars:
            del env_vars[key]
            write_env_file(self.env_file, env_vars)
            self._invalidate()
            return True
        return False

    def list_keys(self, prefix: str = "") -> list[str]:
        vars = self._load()
        if prefix:
            return [k for k in vars if k.startswith(prefix)]
        return list(vars.keys())


class AwsSsmStore(SecretStore):
    """AWS Systems Manager Parameter Store integration.

    Requires: pip install boto3
    """

    def __init__(self, path_prefix: str = "/", region: Optional[str] = None):
        self.path_prefix = path_prefix.rstrip("/")
        self.region = region or os.environ.get("AWS_REGION", "us-east-1")

    def _get_client(self):
        try:
            import boto3
        except ImportError:
            raise SecretStoreError("boto3 not installed. Run: pip install envault[awsssm]")
        session = boto3.Session(region_name=self.region)
        return session.client("ssm")

    def get(self, key: str) -> Optional[str]:
        client = self._get_client()
        param_path = f"{self.path_prefix}/{key}"
        try:
            response = client.get_parameter(Name=param_path, WithDecryption=True)
            return response["Parameter"]["Value"]
        except client.exceptions.ParameterNotFound:
            return None

    def set(self, key: str, value: str) -> bool:
        client = self._get_client()
        param_path = f"{self.path_prefix}/{key}"
        client.put_parameter(
            Name=param_path,
            Value=value,
            Type="SecureString",
            Overwrite=True,
        )
        return True

    def delete(self, key: str) -> bool:
        client = self._get_client()
        param_path = f"{self.path_prefix}/{key}"
        try:
            client.delete_parameter(Name=param_path)
            return True
        except client.exceptions.ParameterNotFound:
            return False

    def list_keys(self, prefix: str = "") -> list[str]:
        client = self._get_client()
        full_prefix = f"{self.path_prefix}/{prefix}" if prefix else self.path_prefix
        keys: list[str] = []
        paginator = client.get_paginator("describe_parameters")
        for page in paginator.paginate(
            ParameterFilters=[{"Key": "Name", "Option": "BeginsWith", "Values": [full_prefix]}]
        ):
            for param in page["Parameters"]:
                name = param["Name"]
                # Strip the path prefix
                if name.startswith(self.path_prefix + "/"):
                    name = name[len(self.path_prefix) + 1:]
                keys.append(name)
        return keys


class VaultStore(SecretStore):
    """HashiCorp Vault integration (KV v2 engine).

    Requires: pip install hvac
    """

    def __init__(self, url: str = "http://127.0.0.1:8200", token: Optional[str] = None,
                 mount_point: str = "secret", path_prefix: str = ""):
        self.url = url
        self.token = token or os.environ.get("VAULT_TOKEN", "")
        self.mount_point = mount_point
        self.path_prefix = path_prefix

    def _get_client(self):
        try:
            import hvac
        except ImportError:
            raise SecretStoreError("hvac not installed. Run: pip install envault[vault]")
        client = hvac.Client(url=self.url, token=self.token)
        if not client.is_authenticated():
            raise SecretStoreError("Vault authentication failed")
        return client

    def _full_path(self, key: str) -> str:
        parts = [p for p in [self.path_prefix, key] if p]
        return "/".join(parts)

    def get(self, key: str) -> Optional[str]:
        client = self._get_client()
        try:
            response = client.secrets.kv.v2.read_secret(
                path=self._full_path(key),
                mount_point=self.mount_point,
            )
            data = response.get("data", {}).get("data", {})
            return data.get("value")
        except Exception:
            return None

    def set(self, key: str, value: str) -> bool:
        client = self._get_client()
        client.secrets.kv.v2.create_or_update_secret(
            path=self._full_path(key),
            secret={"value": value},
            mount_point=self.mount_point,
        )
        return True

    def delete(self, key: str) -> bool:
        client = self._get_client()
        try:
            client.secrets.kv.v2.delete_metadata_and_all_versions(
                path=self._full_path(key),
                mount_point=self.mount_point,
            )
            return True
        except Exception:
            return False

    def list_keys(self, prefix: str = "") -> list[str]:
        client = self._get_client()
        list_path = self._full_path(prefix)
        try:
            response = client.secrets.kv.v2.list_secrets(
                path=list_path,
                mount_point=self.mount_point,
            )
            return response.get("data", {}).get("keys", [])
        except Exception:
            return []


def get_store(config) -> SecretStore:
    """Factory: create a SecretStore from config."""
    from envault.config import SecretStoreConfig

    if isinstance(config, SecretStoreConfig):
        store_type = config.type
        kwargs = {}

        if store_type == "aws-ssm":
            kwargs["path_prefix"] = config.path_prefix
        elif store_type == "vault":
            kwargs["url"] = config.url or "http://127.0.0.1:8200"
            kwargs["path_prefix"] = config.path_prefix
            if config.token_env_var:
                kwargs["token"] = os.environ.get(config.token_env_var, "")
            kwargs["mount_point"] = config.path_prefix.split("/")[0] if config.path_prefix else "secret"
        elif store_type == "local":
            kwargs["env_file"] = config.path_prefix or ".env"
        else:
            raise SecretStoreError(f"Unknown store type: {store_type}")

        return _create_store(store_type, **kwargs)

    return LocalEnvStore()


def _create_store(store_type: str, **kwargs) -> SecretStore:
    stores = {
        "local": LocalEnvStore,
        "aws-ssm": AwsSsmStore,
        "vault": VaultStore,
    }
    cls = stores.get(store_type)
    if not cls:
        raise SecretStoreError(f"Unknown store type: {store_type}")
    return cls(**kwargs)
