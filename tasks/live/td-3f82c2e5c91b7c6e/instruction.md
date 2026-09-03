# Chiral hydrogens viewed by default

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

Hydrogens attached to R/S stereocenters are now shown by default, including when `--no-hy` is passed. This uses
xyzgraph's built-in `assign_rs()` detection to identify
stereocenters whose hydrogens would previously have been hidden.

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
