# Dos in merge key

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

[redacted-ref]
Supercedes [redacted-ref]

### Summary
The merge key (`<<`) constructor implementation in
`SafeConstructor.flatten_mapping()` was vulnerable to an
exponential time and memory complexity Denial of Service (DoS)
vulnerability. When mapping/sequence nodes are merged using
anchors/aliases, duplicate references to the same alias point
to the same MappingNode instance in Python. During merge key
processing, the node values are copied and extended in-place.
If the same node appears multiple times at different levels,
this causes exponential amplification of the elements list:
`2^(n+1) - 1`.

A small document under 1 KB can trigger millions of element
list extensions, exhausting CPU and memory during safe loading.

### Hardened Fix
This commit resolves the vulnerability and hardens it against
secondary vectors:
1. Tracks node identity using object ID (`id(node)`) in a single
`seen` set scoped to the parent mapping's `flatten_mapping()`
execution.
2. Checks and skips duplicate node references inside SequenceNode
merge keys (resolving [redacted-ref]).
3. Checks and skips duplicate node references across separate,
independent MappingNode merge keys in the same mapping (e.g.,
repeating `<<: *anchor` multiple times).
4. Ensures C-based loaders (e.g., `CSafeLoader`, `CLoader`) are
also protected since they inherit constructor logic from
`SafeConstructor`.

### Performance Impact
- Sequence-nested merge duplicates: Loading a 22-level nested
document drops from 3.76s to 0.0028s (O(N) linear complexity).
- Mapping-level merge duplicates: Loading a 20-level nested
document drops from 0.93s to 0.0026s.

### Tests
- Added regression tests to
`tests/legacy_tests/data/construct-merge.data` and
`tests/legacy_tests/data/construct-merge.code` covering both
duplicate sequence merges and duplicate direct merges.

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
