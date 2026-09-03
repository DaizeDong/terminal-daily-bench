# feat: detect Supabase sensitive tokens

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## What & why

Detect sensitive Supabase personal access tokens (`sbp_...`) and project secret keys (`sb_secret_...`) so Agent Sweep can find and redact them from agent histories. Public `sb_publishable_...` keys remain unreported, while legacy Supabase JWT keys continue through the existing generic JWT rule.

[redacted-ref].

## Type of change

- [ ] Bug fix
- [ ] New agent source
- [x] New detection rule
- [x] Feature / enhancement
- [ ] Refactor / docs / chore

## Testing

```text
uv run --frozen pytest -q
694 passed in 2.99s

uv run --frozen pytest -q tests/test_supabase_tokens.py tests/test_ported_rules.py tests/test_scan_performance.py
220 passed in 0.50s

uv run --frozen mypy src/
Success: no issues found in 29 source files
```

A CLI smoke scan reported the synthetic personal access token and secret key while ignoring the publishable key.

## Checklist

- [x] `pytest` passes locally, and CI is green on **all** platforms (Linux **and** Windows, Python 3.11–3.13)
- [x] `mypy src/` is clean — it runs on every matrix leg and is the most common reason a PR goes red
- [x] No new runtime dependency, or the PR explains why one is needed (the core install is deliberately three packages)
- [x] No real secrets, tokens, or raw history-file contents are committed — tests use synthetic, non-live examples
- [x] Redaction / write-path changes preserve the corruption-prevention invariants (not touched by this PR)
- [x] **New detection rule?** Added to `RULES` **and** `ROTATION_GUIDANCE` **and** synthetic fixtures/tests, with bounded quantifiers and lossless keyword prefilters
- [x] **New source?** N/A — no source registration changes
- [x] `--json` and non-tty output stay machine-clean; the JSON CLI smoke path was exercised
- [x] Did not re-introduce `force-include` in `pyproject.toml`

<!-- This is an auto-generated comment: release notes by coderabbit.ai -->

## Summary by CodeRabbit

* **New Features**
  * Added detection for Supabase personal access tokens and secret keys.
  * Added guidance to rotate detected Supabase credentials.
  * Publishable Supabase keys are excluded from sensitive-token findings.

* **Documentation**
  * Updated detection totals and performance documentation to reflect expanded coverage.

* **Bug Fixes**
  * Improved recognition of valid Supabase credentials while rejecting malformed or embedded variants.

<!-- end of auto-generated comment: release notes by coderabbit.ai -->

<!-- greptile_comment -->

<details><summary><h3>Greptile Summary</h3></summary>

The PR adds detection and rotation guidance for sensitive Supabase personal access tokens and project secret keys while excluding publishable keys.
- Registers bounded, keyword-prefiltered patterns for `sbp_...` and `sb_secret_...` credentials.
- Adds behavioral, regex-engine parity, fixture-coverage, and performance tests.
- Updates user-facing detection and performance documentation.
</details>

<h3>Confidence Score: 5/5</h3>

The PR appears safe to merge because no blocking failure remains within the eligible follow-up scope.

No blocking failure remains.

<h3>Important Files Changed</h3>

| Filename | Overview |
|----------|----------|
| src/agentsweep/scanner.py | Adds the two Supabase token rules, lossless prefilter anchors, and provider-specific rotation guidance. |
| tests/test_supabase_tokens.py | Covers accepted sensitive-token formats, malformed and embedded-token rejection, publishable-key exclusion, and scanner integration. |
| tests/test_regex_engine_parity.py | Adds Supabase fixtures to the cross-engine parity and prefilter-losslessness coverage. |
| tests/test_scan_performance.py | Updates performance expectations and fixtures for the expanded rule registry. |
| README.md | Documents Supabase coverage and updates the advertised detector inventory. |
| docs/PERF.md | Updates scanner inventory and prefilter coverage documentation. |

<sub>Reviews (5): Last reviewed commit: ["Merge origin/main into feat/supabase-tok..."]([redacted-url]) | [Re-trigger Greptile]([redacted-url])</sub>

<!-- /greptile_comment -->

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
