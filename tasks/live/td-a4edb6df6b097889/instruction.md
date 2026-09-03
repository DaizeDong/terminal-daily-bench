# Fix get_real_name for names with more than two dotted parts ([redacted-ref])

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

[redacted-ref].

### The bug

`get_real_name()` returns the wrong component for a fully-qualified name with more than two dotted parts:

```python
import [redacted-repo]
ident = [redacted-repo].parse("db.schema.tbl.col")[0].tokens[0]
ident.get_real_name()   # 'schema'  — should be 'col'
ident.get_name()        # 'schema'  — should be 'col' (get_name falls back to real name)
```

More cases on current `master`: `a.b.c` → `'b'` (should be `'c'`), `x.y.z AS w` → real name `'y'` (should be `'z'`), `mydb.sch.func(1)` → `'sch'` (should be `'func'`). Two-part names like `a.b` → `'b'` are correct and stay correct.

This is [redacted-ref] (open since 2017): the "object name" of `db.schema.tbl.col` is the last component, but the current result is an intermediate one that is neither the object nor its parent.

### Root cause

`NameAliasMixin.get_real_name` (`[redacted-repo]/sql.py`) anchors on the **first** dot:

```python
dot_idx, _ = self.token_next_by(m=(T.Punctuation, '.'))   # first dot
return self._get_first_name(dot_idx, real_name=True)      # first name from there
```

`token_next_by` returns the first dot, so `_get_first_name` returns the component right after it — the second part. For a 2-part name the first dot is also the last, so it happened to be correct; for 3+ parts it stops too early.

`get_parent_name` documents the opposite intent — *"A parent object is identified by the first occurring dot"* — so the first-dot logic belongs there, not in `get_real_name`. The docstring of `get_real_name` says "the real name (object name)", which is unambiguously the component after the **last** dot.

### The fix

Anchor `get_real_name` on the last dot instead of the first. `get_parent_name` is untouched, so parent name and real name now come from opposite ends of the dotted path, as intended.

### Verification

- The repro above now returns `col`; `a.b.c` → `c`, `x.y.z AS w` → real `z` / alias `w`, `mydb.sch.func(1)` → `func`, `db.sch."My Table"` → `My Table`, `a.b.*` → `*`. Two-part names and `get_parent_name` are unchanged.
- Added `test_get_real_name_multi_part_dotted`; it fails on `master` (`assert 'col' == 'schema'`) and passes with the fix.
- Full suite: `488 passed, 2 xfailed, 1 xpassed` (was 487 + the new test) — no existing test relied on the old behavior. `ruff check [redacted-repo]/sql.py` clean.

---

This PR was authored by an AI coding agent (Claude Code) running on this account: the AI found the bug, ran the repro, wrote the test, and wrote this description. The human account holder reviews every change and is accountable for it. The verification above is real and re-runnable from the diff. If this isn't the kind of contribution you want, say so and I'll close it.

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
