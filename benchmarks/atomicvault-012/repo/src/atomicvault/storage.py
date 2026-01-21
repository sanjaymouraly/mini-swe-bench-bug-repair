"""Atomic file storage with SHA-256 manifest and crash recovery."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from pathlib import Path
from typing import BinaryIO


class VaultSecurityError(ValueError):
    """Raised when a relative path attempts to escape the vault root."""


class VaultWriteError(RuntimeError):
    """Raised when an artifact write fails."""


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class AtomicVault:
    """Manages atomic file writes, backups, and a SHA-256 manifest."""

    def __init__(self, root_dir: str | Path) -> None:
        self.root = Path(root_dir).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.manifest_path = self.root / "manifest.json"
        if not self.manifest_path.exists():
            self._write_manifest({})

    def _resolve_path(self, rel_path: str) -> Path:
        # BUG 1: Only checks startswith(".."), allowing "a/../../escape.txt"!
        clean = rel_path.replace("\\", "/").strip()
        if not clean or clean.startswith("/") or clean.startswith(".."):
            raise VaultSecurityError(f"Unsafe path: {rel_path}")
        return self.root / clean

    def _read_manifest(self) -> dict[str, str]:
        if not self.manifest_path.exists():
            return {}
        return json.loads(self.manifest_path.read_text(encoding="utf-8"))

    def _write_manifest(self, data: dict[str, str]) -> None:
        self.manifest_path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")

    def put(
        self,
        rel_path: str,
        content_or_writer: bytes | Callable[[BinaryIO], None],
        keep_backup: bool = True,
    ) -> str:
        target = self._resolve_path(rel_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = target.with_name(target.name + ".tmp")
        bak_path = target.with_name(target.name + ".bak")

        # BUG 2: Moves live target to .bak BEFORE writing tmp_path, and doesn't clean up tmp_path on failure!
        if keep_backup and target.exists():
            target.replace(bak_path)

        try:
            with open(tmp_path, "wb") as f:
                if callable(content_or_writer):
                    content_or_writer(f)
                else:
                    f.write(content_or_writer)
        except Exception as exc:
            raise VaultWriteError(f"Failed writing {rel_path}: {exc}") from exc

        tmp_path.replace(target)
        digest = sha256_bytes(target.read_bytes())
        manifest = self._read_manifest()
        manifest[rel_path.replace("\\", "/")] = digest
        self._write_manifest(manifest)
        return digest

    def get(self, rel_path: str) -> bytes:
        target = self._resolve_path(rel_path)
        if not target.exists():
            raise FileNotFoundError(rel_path)
        return target.read_bytes()

    def recover(self) -> dict[str, str]:
        # BUG 3: Does not remove orphaned .tmp files or restore .bak files when target is missing!
        return self._read_manifest()
