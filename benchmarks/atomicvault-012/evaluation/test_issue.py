"""Issue-specific FAIL_TO_PASS tests for atomicvault-012."""

import pytest
from atomicvault import AtomicVault, VaultSecurityError, VaultWriteError, sha256_bytes


def test_failed_midstream_write_preserves_existing_file_and_cleans_temp(tmp_path):
    vault = AtomicVault(tmp_path / "vault")
    vault.put("data/state.json", b'{"version": 1}')

    def failing_writer(f):
        f.write(b'{"version": ')
        raise RuntimeError("disk I/O interruption")

    with pytest.raises(VaultWriteError):
        vault.put("data/state.json", failing_writer, keep_backup=True)

    # Original file must still exist intact!
    assert vault.get("data/state.json") == b'{"version": 1}'
    # No .tmp files may remain
    assert list((tmp_path / "vault").rglob("*.tmp")) == []


def test_recover_restores_orphaned_bak_and_removes_tmp_and_rebuilds_manifest(tmp_path):
    vault_dir = tmp_path / "vault"
    vault = AtomicVault(vault_dir)
    vault.put("models/weights.bin", b"v1_weights")

    # Simulate an external crash where primary was removed, .bak exists, and an orphan .tmp exists
    primary = vault_dir / "models" / "weights.bin"
    bak = vault_dir / "models" / "weights.bin.bak"
    orphan_tmp = vault_dir / "models" / "weights.bin.tmp"
    primary.replace(bak)
    orphan_tmp.write_bytes(b"corrupted_partial")

    rebuilt = vault.recover()
    assert not orphan_tmp.exists()
    assert primary.exists()
    assert vault.get("models/weights.bin") == b"v1_weights"
    assert rebuilt["models/weights.bin"] == sha256_bytes(b"v1_weights")


def test_nested_path_traversal_rejected(tmp_path):
    vault = AtomicVault(tmp_path / "vault")
    with pytest.raises(VaultSecurityError):
        vault.put("subdir/../../outside.txt", b"exploit")
