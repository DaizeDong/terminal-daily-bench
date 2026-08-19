# fix(controller): Recover from invalid dates

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

Tiny hardening change that prevents a malformed Date header from crashing the controller.

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
