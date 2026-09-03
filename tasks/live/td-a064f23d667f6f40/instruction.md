# MARCOS and MAIRCA aggregation methods

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

Implements MARCOS and MAIRCA methods
This pull request adds two new multi-criteria decision-making (MCDM) aggregation methods—MAIRCA and MARCOS—to the `skcriteria` library, along with comprehensive reference documentation and extensive test coverage. These additions enhance the library's ability to handle a wider range of decision analysis scenarios and provide robust, validated implementations for both methods.

New aggregation methods:

* Added the `MAIRCA` (Multi Attributive Ideal Real Comparative Analysis) method in `skcriteria/agg/mairca.py`, including its algorithm, parameter validation, and integration with the decision maker interface.
* Added the `MARCOS` (Measurement Alternatives and Ranking according to COmpromise Solution) method in `skcriteria/agg/marcos.py`, with its algorithm and integration into the aggregation framework.

Testing and validation:

* Introduced comprehensive tests for the `MAIRCA` method in `tests/agg/test_mairca.py`, including validation against literature examples, parameter checks, and edge cases.
* Introduced comprehensive tests for the `MARCOS` method in `tests/agg/test_marcos.py`, including validation against published reference data.

Documentation and references:

* Added relevant literature references for MAIRCA and MARCOS methods in `docs/source/refs.bib` to support academic and practical usage.

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
