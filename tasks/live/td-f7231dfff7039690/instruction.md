# Fix `admin_allow_tags` erasing assignments in wrong scopes

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

Any `X.allow_tags = True` assignment was erased, including
self.allow_tags in unrelated classes' methods and assignments inside
conditional blocks, which could leave empty blocks and invalid syntax.
Restrict to module- and class-level assignments that are not the sole
statement of their block.

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
