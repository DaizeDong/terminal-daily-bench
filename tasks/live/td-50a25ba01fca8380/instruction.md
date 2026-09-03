# Fix import from Castep lattice_abc format

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

[redacted-ref] 

Cell files with lattice_abc vectors were broken, and this was not causing test failures because it wasn't tested. Here we:

- Create test files with and without explicit dimension units
- fix the treatment of lattice_abc data in "two-rows" format (no unit)
- support recent versions of Pymatgen by migrating to
- Lattice.from_parameters from the deprecated Lattice.from_lengths_and_angles
- Note that Lattice.from_parameters does not produce the same cell matrices as CASTEP, and raise a warning if the user has `abs_positions`. The positions will very likely be wrong in this case; but not many features of [redacted-repo] are impacted, so perhaps it would be overkill to error out entirely.

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
