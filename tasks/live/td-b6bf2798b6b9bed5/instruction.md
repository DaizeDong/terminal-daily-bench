# Fix erasing statements joined by semicolons

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

Erasing a statement that shared a physical line with another statement
via a semicolon left the stray semicolon behind, producing invalid
syntax. This affected every fixer erasing statements, e.g.
`default_app_config` and `use_l10n`. Handle a following semicolon by
consuming it, and a preceding one by blanking it in place, which avoids
invalidating token indices before the erased node.

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
