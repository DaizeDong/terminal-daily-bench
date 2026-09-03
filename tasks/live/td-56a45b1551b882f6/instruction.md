# Permit composite URL protocol schemes in `infer_storage_options`

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

Hi there. In [omniload]([redacted-url]), we are [using]([redacted-url]) composite URL protocol schemes like `https+webdav://`, `mongodb+srv://`, or `mysql+pymysql://`. While the code used custom auxiliary/helper functions before, we are now aiming to modernize and refactor a bit, for example towards using `[redacted-repo].utils.infer_storage_options` across the board. On this occasion, we found that a specific regex pattern needed a minor adjustment to permit such URL protocol schemes that include a `+` character.

- Reference: [redacted-url]

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
