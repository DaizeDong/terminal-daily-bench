# Avoid cutting molecules across periodic boundaries

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

Add option to move atoms in the unit cell so that molecules are not cut across periodic boundaries.

Default behaviour:

<img width="479" height="800" alt="roy" src="[redacted-url] />


With '--whole' flag on:

<img width="419" height="800" alt="roy" src="[redacted-url] />

The feature includes:

- make_whole() function

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
