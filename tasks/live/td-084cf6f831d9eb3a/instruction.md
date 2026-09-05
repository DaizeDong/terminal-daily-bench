# Add UNSOURCED_PROJECTION_FIELD fitness function

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## Summary

- New `info`-level diagnostic `UNSOURCED_PROJECTION_FIELD` in the `handler_completeness` category. It flags a projection field that no projector write fills, so it renders as a dead column: the field is in the read model and carries a type, but nothing puts a value in it. `PROJECTION_WITHOUT_PROJECTOR` already catches a projection with no projector at all; this catches a projector that fills four of five fields.
- Evidence is what the projector's handler methods write, read from the behavioral view the producer rules already use. A field counts as sourced when some projector method constructs the projection with that field as a keyword (`ConstructionFact.field_names`) or writes it as an attribute (`AttributeFact` with `is_write`). Coverage is the union across every projector of the projection.
- Three guards keep the verdict reproducible: `externally_populated` projections opt out, a `**kwargs` construction disables the check for the whole projection, and a projection with no observed write at all is skipped rather than reported field by field. The `identity_field` is exempt because the framework fills it on write.
- Registered in `DiagnosticCode` with full `CodeMeta`, documented in `docs/reference/fitness-functions.md`, and added to the golden code-set and digest snapshots.

The level is `info` because the check works from observed writes. Once any projector write is seen, a sibling field filled only through a path the check cannot follow (a helper, `setattr`, a dict splat) can still be flagged. Advisory is the honest level for that.

## Compatibility

Additive: a new code, no change to any existing rule. At the default `[lint].level = "warn"`, info findings do not gate CI, so a project on the default config sees the new finding in the report and stays green. A project that has set `[lint].level = "info"` can see a new failure, the same as for any new info-level rule.

## Test plan

- [x] `tests/ir/` passes (1968 tests) — new `tests/ir/diagnostics/test_unsourced_projection_field.py` covers each acceptance criterion: four-of-five flags the fifth by name, full coverage flags nothing, attribute-write evidence, the empty-evidence guard, the `**kwargs` opt-out, the identity exemption, the two-projector union, and the `externally_populated` opt-out
- [x] The golden code-set snapshot in `tests/ir/diagnostics/test_code_registry.py` gains exactly one code
- [x] `ruff check`, `ruff format --check`, and `mypy` clean on `src/[redacted-repo]/ir` and `tests/ir`

The corpus lives in `tests/ir/support/unsourced_projection_domain/` as real importable source, because the rule reads projector method bodies through the behavioral substrate.

[redacted-ref]

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
