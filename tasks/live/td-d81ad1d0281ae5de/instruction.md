# [BUG] multidimensional time crop

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

I stumbled across this while working. `pf.dsp.time_crop` raised an error when applied to signals with a channel dimension greater than 1.

This PR should fix this issue. 

I have also added a test for this scenario.

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
