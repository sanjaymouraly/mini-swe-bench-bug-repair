# Issue: `AtomicVault` loses live files on mid-write failure, fails crash recovery, and allows `a/../../` path traversal

## Description
`AtomicVault` manages crash-safe artifact files and a SHA-256 `manifest.json` inside a root directory. Three critical reliability/security bugs were discovered:

1. **Nested path traversal bypass (`subdir/../../escape.txt`)**:
   `_resolve_path(rel_path)` only checks `rel_path.startswith("..") or rel_path.startswith("/")`. Passing `"nested/../../outside.txt"` escapes the vault root! It must resolve the path and verify `candidate.is_relative_to(self.root)` (and reject reserved `"manifest.json"` or `*.tmp` / `*.bak` names), raising `VaultSecurityError`.
2. **Mid-write exception destroys existing live file and leaves `.tmp` behind**:
   In `put(rel_path, content_or_writer, keep_backup=True)`:
   Currently, if the target file already exists, `put()` renames `target -> target.bak` **before** writing the new content to `target.tmp`. When `content_or_writer` (a callable `writer(file_obj)`) raises an exception mid-write, `target` is gone and `target.tmp` is left behind!
   Instead:
   - Write to a temporary file in the same directory first (`<name>.tmp`).
   - If writing fails, unlink the `.tmp` file and re-raise `VaultWriteError` without touching the live `target` file or `manifest.json`!
   - Only after the `.tmp` file is completely written and flushed: if `keep_backup=True` and `target` exists, copy/link `target` to `<name>.bak` (or replace atomically) and `os.replace(tmp_path, target)`, then update `manifest.json` atomically.
3. **`recover()` after simulated crash does not clean `.tmp` files or restore missing targets from `.bak`**:
   When an external crash leaves orphaned `*.tmp` files or a `<name>.bak` file where `<name>` is missing, `recover()` must:
   - Delete all orphaned `*.tmp` files across the vault.
   - If a `<name>.bak` file exists and its corresponding `<name>` target does not exist, restore `<name>.bak` -> `<name>`.
   - Rebuild `manifest.json` with accurate SHA-256 digests of all live artifact files (excluding `manifest.json`, `*.tmp`, and `*.bak`).

## Expected Behavior
- Any path escaping `self.root` raises `VaultSecurityError`.
- Failed writes leave existing target files and `manifest.json` completely intact and leave zero `.tmp` files behind.
- `recover()` cleans up `.tmp` files, restores orphaned `.bak` files when the primary target is missing, and synchronizes `manifest.json`.
