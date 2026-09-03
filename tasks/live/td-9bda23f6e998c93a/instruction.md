# Repair v5 judge contract after DeepSeek alias drift

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## Summary

- preserve the first paid development attempt as partial / not_evaluated after strict model-identity rejection
- amend the disconnected v5 transport contract to request exact deepseek-v4-flash with thinking disabled
- persist safe usage for rejected responses without persisting semantic output, and aggregate failed-call accounting at the execution seam
- add conservative dated V4 Flash peak pricing while preventing deployment price overrides from changing the frozen study
- document the provider stop, pre-registration amendment, implementation evidence, and updated project state

## Verification

- 1751 passed, 639 subtests passed
- adapter/runner: 16 passed
- adapter/runner/accounting: 46 passed, 8 subtests passed
- latest Ruff: passed
- narrow CI Pylint: passed
- real default v5 dry-run: 8/8 cases, 64/64 candidates, 16 prompt identities, zero network/model calls
- defect reinjection: missing thinking control and environment-price leakage each made the outbound seam test fail

## Boundaries

No paid retry occurred. OpenAlex, production reports, and planner triggers remain disconnected. Any later W01-W08 execution requires fresh authorization on a merged revision.

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
