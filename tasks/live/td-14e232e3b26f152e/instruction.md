# Probe `tabulate` version for `preserve_whitespace`

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## Description
Somehow, users are able to have installations of newer mycli/[redacted-repo] with older versions of `tabulate`, before a breaking change in the way `preserve_whitespace` is specified for `tabulate`.

Here we probe the tabulate version to determine how to specify the value.

## Checklist
<!--- We appreciate your help and want to give you credit. Please take a moment to put an `x` in the boxes below as you complete them. -->
- [x] I've added this contribution to the `CHANGELOG`.
- [x] I've added my name to the `AUTHORS` file (or it's already there).
- [x] I installed pre-commit hooks (`pip install pre-commit && pre-commit install`), and ran `black` on my code.
- [x] Please squash merge this pull request (uncheck if you'd like us to merge as multiple commits)

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
