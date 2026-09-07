# fix: serialize text nodes in [redacted-repo] str/html

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

[redacted-repo].__str__ hits TypeError when contents() includes text nodes. This PR fixes the regression with a focused test covering the case.

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
