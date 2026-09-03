# RLE update with Azure Pipelines changes

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

Duplicate of [redacted-ref] from @eugenpt  
[redacted-ref] 

The main change here is that I pinned the pytest-cov version to 2.6.1, the previously working version. The plugin and pytest itself had upgrades for the past few weeks, causing them to _probably_ be out-of-sync. Pinning the versions should work

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
