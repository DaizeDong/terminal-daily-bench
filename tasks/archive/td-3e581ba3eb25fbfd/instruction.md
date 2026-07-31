# Add Mir card validation support

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

This PR introduces validation for Mir cards (Russian payment system) to the [redacted-repo] library.

Key Changes:
* Added mir() validator function with BIN checks (2200-2204)
* Ensures compliance with Luhn algorithm
* Includes length validation (16 digits standard)
* Added unit tests for valid/invalid cases

Why This Matters:
* Mir is a nationally critical payment system (used in Russia and neighboring countries)
* Required for apps processing payments in RUB
* Maintains parity with other card [redacted-repo] (Visa, Mastercard, Unionpay etc.)

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
