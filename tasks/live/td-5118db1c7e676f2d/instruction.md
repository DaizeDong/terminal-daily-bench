# feat: update HackerNews extraction to avoid API timeout and use HTML parsing

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

* Add a new HackerNews extraction scheme to parse user profiles via HTML.
* Extract profile metadata including username, account creation date, karma, and bio.
* Transition away from Firebase API usage to prevent payload size timeouts for highly active users.
* Add end-to-end tests for HackerNews extraction.
* Update METHODS.md to reflect the new scheme capabilities.

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
