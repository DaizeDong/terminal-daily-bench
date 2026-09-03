# fix: Messages API Validations -- May 2026

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

This PR updates some validations for the Messages API. Specifically it:

- Adds validations to the `ttl` param for `sms`
- Adds model validators for the conditional validations for `rcs` based on `card_orientation`

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
