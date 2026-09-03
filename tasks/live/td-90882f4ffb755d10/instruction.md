# Follow KLayout's order for Path transformations

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## Summary

Magnification, then mirroring at the x-axis, then rotation, then displacement.

Also ends up fixing a few more bugs (e.g. missing mag, R+M =/= M+R) and improvements (e.g. analytical angles)

## Test Plan

🤖 🤖 🤖

## Summary by Sourcery

Align Path transformation behavior with KLayout and preserve accurate tangent angles.

Bug Fixes:
- Apply Path transformations in KLayout’s order so magnification, mirroring, rotation, and displacement compose correctly.
- Preserve analytic start and end tangent angles through Path transformations.

Tests:
- Add coverage comparing Path transformations with KLayout and validating analytic tangent-angle preservation.

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
