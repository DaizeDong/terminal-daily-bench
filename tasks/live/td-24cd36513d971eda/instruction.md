# fix(gda): close the res://../ containment bypass in path_outside_project

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## Summary

- `path_outside_project` (the ADR-0006 containment authority, `src/gda/project.py`) short-circuited **every** `res://` string as inside the project. Its docstring's own reasoning — "an engine-virtual path is inside by construction... gda can make no filesystem statement about one" — is true for a well-formed `res://a/b.gd` but false for one that lexically escapes the namespace: `res://../outside.gd` still names a file above the project root after Godot's own `.`/`..` collapsing, and nothing checked for that.
- `script validate` trusts this authority directly (`_script_validate_recipe`), so the same file got opposite verdicts by spelling: refused as `/abs/path/outside.gd`, accepted as `res://../outside.gd`. Per `CONTEXT.md`'s Project-code execution surface, `validate` compiles the target, so the bypass admitted code outside the `Trusted project` through a refusal that exists precisely to prevent that.
- Fix, part 1: a `res://` path is now canonicalized through the shared `gda.script_errors.canonical_res_path` and refused only when it still climbs above the namespace root after that collapsing (`res://..`, `res://../outside.gd`, `res://../../x`).
- Fix, part 2 (round-2 review): **the canonicalizer itself did not match the engine on separators.** Godot folds `\` to `/` across a `res://` address *before* it collapses anything (`String::simplify_path`, `core/string/ustring.cpp:4192`, `4.6-stable-3260-g070dc9897e`), so `res://..\outside.gd` **is** the escaping `res://../outside.gd` to the engine. The fold now lives in `canonical_res_path`, where the engine puts it, so all three consumers get the engine's own identity. Applied only to a `res://` string: `\` is a legal POSIX filename character, and the fold is the engine's rule, not the filesystem's.
- A path that lexically contains `..` but collapses back inside (`res://foo/../bar.gd` → `res://bar.gd`) stays accepted — it is net-inside the namespace, exactly as Godot itself would canonicalize the address. A filename that merely starts with two dots (`res://..foo.gd`) is unaffected (checked by path segment, not string prefix). `user://` and `uid://` are untouched: gda still cannot make a filesystem statement about either.

## Engine parity of `canonical_res_path`

The round-2 review asked that the claim "canonicalized the way the engine canonicalizes one" be true or the gap be stated. `canonical_res_path`'s docstring now audits `String::simplify_path` (`core/string/ustring.cpp:4149-4233`) step by step. Reproduced: the scheme/"drive" extraction (narrowly, for an exact `res://` prefix); the `\` → `/` fold (4192); the repeated-`//` collapse and `split("/", false)` (4193-4201); the `.`/`..` collapse **with the leading-`..` strip disabled for `res://`** (4204-4221, the engine's own `FIXME`-marked exception), which is what lets an escape survive to be detected at all.

**One stated gap**, in the join (4223-4232): when every segment collapses away the engine yields the bare `res://`, `posixpath.normpath` yields `.`, so `res://a/..` canonicalizes here to `res://.`. Both spellings name the project root and every consumer already treats the pair alike — `script run`'s gate tests the pair explicitly (`_ROOT_REMAINDERS = {"", "."}`) and a `.` is not an upward escape — so the divergence is unobservable. Closing it would churn a deliberate accommodation in another command's gate, which [redacted-ref] owns reconciling.

## Real-engine evidence (Godot 4.6.3, `4.6-stable-3260-g070dc9897e`)

All three spellings are one address to the engine, and it loads the file one directory above the project:

```
spelling=res://../outside.gd
  simplify_path -> res://../outside.gd
  load          -> (res://../outside.gd):<GDScript#-[redacted-sha]>
spelling=res://..\outside.gd
  simplify_path -> res://../outside.gd
  load          -> (res://../outside.gd):<GDScript#-[redacted-sha]>
spelling=res://a\..\..\outside.gd
  simplify_path -> res://../outside.gd
  load          -> (res://../outside.gd):<GDScript#-[redacted-sha]>
```

The separator bypass was **wider than `script validate`**. At the previous head (`[redacted-sha]`), against the real engine:

| command | previous head | this head |
|---|---|---|
| `gda script validate 'res://..\outside.gd'` | `valid=true`, exit 0 | `project_not_found`, exit 4 |
| `gda script run '..\outside.gd'` | exit 0, stdout `<<<OUTSIDE-SCRIPT-RAN>>>` — **it executed a script outside the project** | `invalid_path`, exit 4, no launch |

`script run`'s gate lifts a project-relative path onto a `res://` address before canonicalizing, so the un-folded backslash reached the engine as a real traversal. That is exactly the ADR-0009 `Trusted project` widening the gate exists to prevent, and it is closed by the same one-line fold because all three gates share the canonicalizer.

## Scope discipline (per [redacted-ref])

Three commands answer "is this target inside the resolved project", each its own way:

| command | `res://../outside.gd` | `res://..\outside.gd` | decided by |
|---|---|---|---|
| `script validate` | now refused (was accepted — the bug) | now refused (was accepted) | `gda.project.path_outside_project` (fixed here) |
| `script run` | refused | now refused (was **launched**) | its own `_project_scoped_res_path` (`src/gda/commands/script.py`) — its refusal *rules* are unchanged; it shares `canonical_res_path`, so the fold fixed its separator blind spot too |
| `resource import` | refused | refused on POSIX, by the later `is_file()` check rather than by its `..` gate | its own `..`-in-parts check in `_asset_res_path` (`src/gda/commands/resource.py`) — unchanged |

Neither `script run`'s nor `resource import`'s private gate becomes redundant by this fix: neither ever delegated the `res://` case to `path_outside_project` — that's exactly the "three answers" problem [redacted-ref] (blocked on this PR) is scoped to unify. This PR makes the authority answer correctly, fixes the one caller (`script validate`) that trusted it, and corrects the shared canonicalizer that all three read.

`res://foo/../bar.gd` (net-inside, contains a literal `..`): the script-validate gate **accepts** it (canonicalizes first, matching Godot's own address identity), while `resource import`'s gate **rejects** it (its parts-based check refuses any literal `..` regardless of net effect). That divergence already existed before this PR and is left in place — reconciling it is explicitly [redacted-ref]'s job, not this one's.

**Disclosed residual risk (unchanged by this PR, for [redacted-ref]):** `_asset_res_path` splits with `PurePosixPath`, so `res://..\x.png` is one segment and its `..` gate does not fire. On POSIX the request is still refused, one step later, by `source.is_file()` on the literal-backslash name; a Windows-native `Path` join would treat `\` as a separator and could reach the parent directory. Not reproducible on this platform, so it is reported rather than changed — `resource import` is a different command with its own gate, and [redacted-ref] owns unifying them.

## Test plan

- [x] `tests/test_script_error_parser.py` — the canonicalization matrix gains `res://a\b.gd`, `res://..\outside.gd`, `res://a\..\..\outside.gd` (all folding to the engine's spelling), `res://\a.gd` (pins that the fold runs **before** the leading-slash strip, as the engine runs it before its own split), and `/abs/we\ird.gd` (a filesystem path keeps its backslashes).
- [x] `tests/test_project.py` pins the authority directly: `res://../outside.gd` and `res://..` are outside (with the resolved location reported); the new `test_a_backslash_spelled_res_escape_is_outside` covers `res://..\outside.gd` and the mixed `res://a\..\..\outside.gd`; `test_a_backslash_in_a_filesystem_path_is_not_a_separator_on_posix` pins that `..\outside.gd` as a *filesystem* path stays inside **on POSIX**, where `\` is a legal filename character — native Windows `pathlib` reads the same string as a parent escape and gda reports it outside, correctly by that platform's rule, so the test carries the repository's `os.name != "posix"` skip. The platform-independent half of that boundary — that the fold is the engine's `res://` rule and never rewrites another string — is pinned where it is already owned, in `tests/test_script_error_parser.py`'s `canonical_res_path` matrix, which now carries `a\b.gd` and `..\outside.gd` one row away from their `res://` twins; `res://foo/../bar.gd` and `res://..foo.gd` stay inside; `user://../outside.gd` / `uid://../abc123` stay inside (untouched).
- [x] `tests/test_script_commands.py` — `test_script_validate_refuses_a_res_dotdot_escape_the_same_as_the_absolute_spelling` is now parametrized over the slash, backslash and mixed spellings, each paired **in one test** with the absolute path of the same file: identical `project_not_found` verdict, identical reported location, neither reaching the engine.
- [x] `tests/test_script_run_operation.py` — the `_project_scoped_res_path` refusal matrix gains `res://..\outside.gd`, `..\outside.gd` and `res://a\..\..\outside.gd`, the spellings that previously launched.
- [x] Existing `test_script_validate_does_not_refuse_a_res_path` (well-formed `res://deck.gd`) still passes; its comment cross-references the new escape test.
- [x] `test_engine_virtual_paths_are_never_outside` renamed to `test_well_formed_engine_virtual_paths_are_not_outside`, its comment qualified — the old name asserted an absolute that the sibling escape test disproves (round-2 Standards finding).
- [x] Red-proofed: with the committed head's `src/` restored over the new tests, **10 cases failed** — 4 canonicalizer cases, `test_a_backslash_spelled_res_escape_is_outside`, 2 CLI-parity cases, 3 `script run` gate cases (the last reporting `ScriptRunResult(path='res://a\\..\\..\\outside.gd', exit_status=0)`, i.e. the pre-fix build launched the escape). With the fix restored, all 246 tests in those four files pass.
- [x] Real-engine severity check run both ways (table above), plus a legitimate in-project `gda script run inside.gd` still succeeding (exit 0).

Gates (verbatim, at `[redacted-sha]`):
```
$ uv run pytest -q -m "not e2e"
1958 passed, 543 deselected in 55.49s

$ uv run ruff check .
All checks passed!

$ uv run ruff format --check .
473 files already formatted

$ uv run pyright
0 errors, 0 warnings, 0 informations

$ uv run pytest -q -m e2e -rs tests/test_e2e_script.py tests/test_e2e_script_run.py tests/test_e2e_project.py
141 passed in 160.48s (0:02:40)

$ uv run pytest -q -m e2e -rs tests/test_e2e_scene_preflight.py tests/test_e2e_scene_validate.py tests/test_e2e_scene_security.py
30 passed in 22.88s
```

The second e2e batch is there because `canonical_res_path` is shared with the script-error parser, which the scene preflight also reads.

## Sweep (AC bullet 4)

Every remaining site that answers "is this target inside the resolved project", confirmed by grep across `src/gda`:

1. `gda.project.path_outside_project` — the declared ADR-0006 authority (fixed here).
2. `gda.commands.script._project_scoped_res_path` — `script run`'s own gate, independent rules, unchanged; shares `canonical_res_path`, so it inherits the separator fold.
3. `gda.commands.resource._asset_res_path` — `resource import`'s own gate: reuses the authority for filesystem paths, but has its own inline check for `res://` inputs, unchanged.

Still three answers, not one — [redacted-ref] is the tracked follow-up to unify them.

[redacted-ref]

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
