# Restrict template source paths

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

<!-- This is an auto-generated comment: release notes by coderabbit.ai -->
## Summary by CodeRabbit

* **Bug Fixes**
  * Improved template loading security by rejecting missing, invalid, or out-of-scope template files.
  * Prevented templates and static includes from accessing files outside the approved template directory.
  * Added protection against symlink changes during template validation and reading.
  * Improved error reporting for invalid template sources and include paths.

* **Tests**
  * Added coverage for symlinks, directories, broken paths, file changes, and unsafe includes.
<!-- end of auto-generated comment: release notes by coderabbit.ai -->

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
