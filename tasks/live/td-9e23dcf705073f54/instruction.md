# feat: alternate ddl and sub phases

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

- support optional alternate DDL for clustering and partitioned layouts
- support selective ANALYZE for only running on a defined subset of columns in the benchmark registry
- support analyze and optimize being triggered as a subphase for isolating the cost of maintenance operations

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
