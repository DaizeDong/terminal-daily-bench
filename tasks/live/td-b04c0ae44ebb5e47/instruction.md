# Add neutral_venue option to exclude home advantage per match

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

Adds an optional per-match `neutral_venue` flag to the six frequentist goal models. When a match is flagged neutral, the home advantage term is excluded from its expected goals during fitting, so `home_advantage` is estimated only from genuine home games.

This matters for tournaments played at neutral venues (World Cups, continental cups): labelling one side "home" otherwise dilutes the home advantage estimate.

## Changes
  - Optional `neutral_venue` argument on all six frequentist models (Poisson, Dixon-Coles, Negative Binomial, ZIP, Bivariate Poisson, Weibull Copula).
  - Threaded through the Cython loss and gradient kernels: `home_advantage` enters `λ_home` only when `neutral_venue == 0`.
  - Length and 0/1 value validation in `BaseGoalsModel`.

## Backwards compatibility
`neutral_venue` defaults to `None`. Omitting it, passing `None`, or passing an all-zeros array is bit-identical to previous behaviour — existing callers are unaffected.

## Tests
New `test/test_neutral_venue.py` covering all six models: backwards compatibility, loss/gradient response to the flag, the home-advantage gradient being zero for neutral matches, all-neutral convergence, and input validation.

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
