# Level/core

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

This is the first part of [redacted-ref], the umbrella Draft PR for the level module.

This PR introduces the shared helper functions that I intend to use for all the standard level functions, and implements the most simple out of all the level functions using these helpers, which is L_Eq.

Since thorough documentation will be very similar/redundant between these level functions, it should be done in a separate PR later, when more/all of the standard level functions are merged into the `level_module` branch. (see [redacted-ref] for elaboration)

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
