# add classify --local mode

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

- Add `local_classify()` in api.py: embeds texts + labels locally, cosine similarity picks best label
- Add `--local` flag to `jina classify` command
- Add unit tests with mock embeddings
- Update README local mode section

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
