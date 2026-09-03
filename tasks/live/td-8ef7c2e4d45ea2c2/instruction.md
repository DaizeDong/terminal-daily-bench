# Rewrite the release checklist and make [redacted-repo]_LOG_LEVEL work

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## What and why

- **`[redacted-repo]_LOG_LEVEL` never worked.** It was only read when `[redacted-repo]_DISABLE_LOGGING` was `False`, but that constant was hardcoded `True` and could only be flipped by editing `__init__.py`, so no released version ever honoured the variable. The constant is gone; setting the environment variable now enables logging at that level at import, and leaving it unset keeps the library silent. Silence-by-default ([redacted-ref]) is unchanged, as is `set_log_level()` at runtime.
- **The release checklist described a pre-`pyproject`, pre-CI-gates world.** It named three of the six places the version lives, had no tagging step at all despite `CHANGELOG.md`'s compare links depending on a `vX.Y.Z` tag, and asked for manual test and docs runs that CI now gates. Rewritten around what is actually true, with conda-forge and Read the Docs steps added.
- **Added `.github/RELEASE_NOTES_TEMPLATE.md`** so contributors, issue reporters and reviewers get named in the release notes rather than forgotten. It includes the commands to collect them and a reminder that `git shortlog` will never show someone who reported a bug without opening a PR.

Two workflow fixes fall out of the checklist rewrite: `deploy_to_test_pypi.yml` no longer triggers on `release: created`, where it re-uploaded an already-published version and failed with a 400 every single release, and the `[redacted-repo]_RELEASE_BUILD` variable is removed from both deploy workflows since nothing reads it. `docs/source/ci_cd.rst` is corrected to six workflows, documents `release_testing.yml`, and no longer refers to micromamba.

Related to [redacted-ref].

## Test plan

- [x] Three new subprocess tests in `tests/logging_test.py`, since import-time behaviour can only be observed in a fresh interpreter: a bare import writes nothing to stderr; `[redacted-repo]_LOG_LEVEL=DEBUG` emits the initialization record; [redacted-repo]'s own sink honours the level it was given.
- [x] Full suite green (128 passed).
- [x] `ruff check`, `ruff format --check`, `pydoclint`, `vulture` clean.
- [x] `sphinx-build -W` succeeds, so the `ci_cd.rst` and `tutorial.rst` edits do not regress the docs gate.

### Known limitation, documented rather than fixed

Once records are enabled they also reach any *other* sink loguru has registered, including loguru's own default stderr handler, which sits at DEBUG and is unfiltered. [redacted-repo]'s records therefore print twice, and the built-in sink ignores the configured level. A library cannot lower the level of a handler it does not own without touching the host's configuration, which is the thing [redacted-ref] was about. The test asserts only [redacted-repo]'s own sink, and the reasoning is written down next to it.

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
