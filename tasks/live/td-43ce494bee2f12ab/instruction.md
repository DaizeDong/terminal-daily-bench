# Feat(models): add public params_array and param_indices API

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

Adds a stable public API for accessing fitted model parameters, addressing [redacted-ref].

## New API
  - `params_array` property: Returns a copy of the internal parameter vector as a numpy array
  - `param_indices()` method: Returns a dict with named indices for parameter groups (attack, defense, home_advantage, etc.)
  - `_get_tail_param_indices()` abstract method: Each model documents its trailing parameter positions

### Example Usage

  ```python
  model = DixonColesGoalModel(...)
  model.fit()

  # Access parameter array (safe copy)
  params = model.params_array

  # Get documented indices
  idx = model.param_indices()
  # {'attack': slice(0, n), 'defense': slice(n, 2n), 'home_advantage': -2, 'rho': -1}

  # Use indices
  hfa = params[idx['home_advantage']]
  attacks = params[idx['attack']]
  ```

## Why This Matters
Downstream tools that apply adjustments to model parameters previously had to access `model._params` directly and maintain hardcoded index mappings. This was fragile - if the internal layout changed, downstream code would silently break.

### With this API:
  - Parameter positions are documented by the model itself
  - Consistency tests ensure indices stay synchronized with the actual layout
  - Breaking changes become visible through test failures

## Tests
  - 22 new tests covering the API
  - Includes consistency tests that verify param_indices() matches _get_param_names()

Closes [redacted-url]

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
