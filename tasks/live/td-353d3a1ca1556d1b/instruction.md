# Pluralize words ending in "x" with "-es" (box -> boxes)

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

pluralize() adds "-es" for words ending in "s", "ch", or "sh", but it was missing "x", so it returned "boxs", "foxs", and "taxs" instead of "boxes", "foxes", and "taxes". This adds "x" to that rule.

Irregular "-x" words such as "ox" are unaffected because they are resolved from the irregular map before the rule runs. I left singularize() untouched, since the reverse direction is genuinely ambiguous (axes could singularize to axe or axis).

Added test_pluralize_x; it fails on the current code.

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
