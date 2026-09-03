# fix: declare hdbscan extra + sanitize untrusted log content ([redacted-ref])

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

[redacted-ref] (A2-1 + S1-3).

- **A2-1** — `clustering.py` imports `hdbscan` lazily but it was declared **nowhere** in `pyproject.toml`, so the clustering feature silently no-op'd for every install and the docstring told users to `pip install hdbscan` off-resolver (a typosquat surface). Declared a `clustering = ["hdbscan>=0.8,<0.9"]` optional extra and added it to `[all]`.
- **S1-3** — memory/transcript text (`fact.content`, `dedup.fact`) was logged raw, so embedded newlines/CR/ANSI could forge log lines or inject terminal escapes (`pipeline.py:484/536/557/562`, …). Added `_safe_log()` (strips all control chars incl. newline/CR/tab → space) and routed the 9 user-content log args through it.

**Tests** (`tests/test_issue_696_hdbscan_logsanitize.py`): the `clustering` extra declares hdbscan; `_safe_log` strips control chars and handles non-str; the user-content log args use `_safe_log`. 12 pipeline/clustering tests still pass. ruff clean.

BLAST OFF v3.

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
