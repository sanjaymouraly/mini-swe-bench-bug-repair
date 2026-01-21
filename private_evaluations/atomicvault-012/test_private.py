"""Private security and backup rotation tests for atomicvault-012."""

import pytest
from atomicvault import AtomicVault, VaultSecurityError


def test_reserved_filenames_and_backup_preservation(tmp_path):
    vault = AtomicVault(tmp_path / "vault")
    with pytest.raises(VaultSecurityError):
        vault.put("manifest.json", b"{}")
    with pytest.raises(VaultSecurityError):
        vault.put("secret.tmp", b"123")

    vault.put("doc.txt", b"first")
    vault.put("doc.txt", b"second", keep_backup=True)
    assert vault.get("doc.txt") == b"second"
    assert (tmp_path / "vault" / "doc.txt.bak").read_bytes() == b"first"
