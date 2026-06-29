"""Audit trail logging for Envault."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


class AuditLogger:
    """Simple append-only audit log for Envault operations."""

    def __init__(self, log_path: str | Path = ".envault-audit.log"):
        self.log_path = Path(log_path)

    def log(
        self,
        action: str,
        key: str,
        *,
        source_path: str = "",
        target_path: str = "",
        env_file: str = "",
        details: dict | None = None,
    ):
        """Log an audit entry."""
        entry: dict[str, object] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "action": action,
            "key": key,
        }

        if source_path:
            entry["source"] = source_path
        if target_path:
            entry["target"] = target_path
        if env_file:
            entry["env_file"] = env_file
        if details:
            entry["details"] = details

        with open(self.log_path, "a") as f:
            f.write(json.dumps(entry) + "\n")

    def get_history(
        self, key: str | None = None, action: str | None = None, limit: int = 50
    ) -> list[dict]:
        """Get audit history, optionally filtered by key and/or action."""
        path = Path(self.log_path)
        if not path.exists():
            return []

        entries: list[dict] = []
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue

                if key and entry.get("key") != key:
                    continue
                if action and entry.get("action") != action:
                    continue

                entries.append(entry)

        return entries[-limit:]

    def clear(self) -> None:
        """Clear the audit log."""
        path = Path(self.log_path)
        if path.exists():
            path.unlink()
