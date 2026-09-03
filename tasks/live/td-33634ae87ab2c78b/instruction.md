# Improving InterventionalTree[redacted-repo] and k-SII aggregation

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## Motivation and Context

  This PR substantially improves the `InterventionalTree[redacted-repo]` algorithm by moving the
  hot-path computations for non-boolean trees to C++.
This is achieved by a improved pre-processing via DFS that shares one tree walk across all reference samples, 
Additionally the baseline value prediction was moved to C++.
Those changes yield a ~263× end-to-end speedup.

Additionally, it vectorizes the k-SII aggregation in two stages. First, all subsets of the
  base interactions are built as a dense padded matrix and multiplied by their Bernoulli
  numbers. This leaves the matrix with 
as many repeatitions as there were supersets in the base interactions. 
Those are then again summed per subset, again vectorized (integer-encoded
  `bincount`), to obtain the final k-SII index (~12–27× faster.

  ## Public API Changes

  -   [x] No Public API changes
  -   [ ] Yes, Public API changes (Details below)

  ## How Has This Been Tested?

  All existing tests pass locally. 

  ## Checklist

  -   [x] The changes have been tested locally.
  -   [ ] Documentation has been updated (if the public API or usage changes).
  -   [x] An entry has been added to `CHANGELOG.md` (if relevant for users).
  -   [x] The code follows the project's style guidelines.
  -   [x] I have considered the impact of these changes on the public API.

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
