# add unquote_user option

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

Add the option to unquote the username also, to match the existing unquote_password option.
It is common for a username to contain an @ sign, especially in a major Cloud provider using IAM usernames.

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
