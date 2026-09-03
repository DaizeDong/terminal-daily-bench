# MNT improve UtilityParity lambda projection

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## Description

Improve `UtilityParity.project_lambda` for difference-based constraints by removing the redundant per-event group-membership component. The projection uses a probability-weighted median, preserves the classifier-dependent Lagrangian term, and reduces the multiplier L1 norm.

[redacted-ref].

## Tests

- [ ] no new tests required
- [x] new tests added
- [x] existing tests adjusted

Focused validation: `python -m pytest test/unit/reductions/moments/test_moments_demographic_parity.py test/unit/reductions/moments/test_moments_equalized_odds.py -q` (9 passed).

## Documentation

- [ ] no documentation changes needed
- [x] user guide added or updated
- [ ] API docs added or updated
- [ ] example notebook added or updated

## Screenshots

Not applicable.

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
