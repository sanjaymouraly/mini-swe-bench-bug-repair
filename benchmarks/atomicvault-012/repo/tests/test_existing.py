"""Pre-existing preservation tests for atomicvault."""

import json
from atomicvault import AtomicVault, sha256_bytes


def test_put_and_get_updates_manifest(tmp_path):
    vault = AtomicVault(tmp_path / "vault")
    digest = vault.put("configs/app.bin", b"hello-world")
    assert digest == sha256_bytes(b"hello-world")
    assert vault.get("configs/app.bin") == b"hello-world"

    manifest = json.loads((tmp_path / "vault" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["configs/app.bin"] == digest
