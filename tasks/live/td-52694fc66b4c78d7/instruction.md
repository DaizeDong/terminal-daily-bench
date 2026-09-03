# Fix bug when unwrapping paramax parameters

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## Checklist

- [x] I've formatted the new code by running `uv run poe format` before committing.
- [x] I've added tests for new code.
- [N/a] I've added docstrings for the new code.

## Description

Fixes [redacted-url] Additionally:

- Updates some of the `fit` tests to optimise the *negative* marginal log likelihood (since fit *minimises* and we want to *maximise* the marginal log lieklihood).
- Updated `migration.md` which was incorrectly showing `fit` being called with `conjugate_mll` as the objective - it should be negated.
- Updated a few sites to use `_val` which were not previously calling it, and instead copying the (buggy) logic.

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
