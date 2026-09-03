# Harden checkpoint writes and restore Python 3.9 typing compatibility in legacy trainer

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

This PR addresses all unresolved comments in the linked [redacted-ref] review thread, with changes limited to the reviewed scope. It specifically resolves checkpoint corruption risk during interrupted saves and removes Python 3.10-only type syntax from `scripts/train_transformer.py`.

- **Checkpoint persistence hardening (review comment: partial/corrupt save risk)**
  - Updated `save_training_checkpoint(...)` to use atomic write semantics:
    1. write payload to a temp file in the target directory,
    2. promote with `os.replace(...)`.
  - Added cleanup on write failure so temporary artifacts are not left behind.

- **Python version compatibility (review comment: PEP 604 unions vs `requires-python >=3.9`)**
  - Replaced PEP 604 unions (`str | None`, `float | None`, etc.) with `Optional[...]`.
  - Normalized affected type annotations to `Dict/List/Tuple` forms compatible with Python 3.9.

- **Focused regression coverage for new failure mode**
  - Extended `tests/test_checkpoint_resume.py` with a test that simulates `torch.save` failure and asserts:
    - no final checkpoint file is created,
    - no `.tmp` checkpoint artifact remains.

```python
with tempfile.NamedTemporaryFile(dir=target_dir, prefix=f".{os.path.basename(path)}.", suffix=".tmp", delete=False) as tmp_file:
    tmp_path = tmp_file.name
try:
    torch.save(payload, tmp_path)
    os.replace(tmp_path, path)  # atomic promotion
except Exception:
    if os.path.exists(tmp_path):
        os.remove(tmp_path)
    raise
```

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
