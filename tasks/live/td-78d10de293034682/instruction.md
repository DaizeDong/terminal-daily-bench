# Make page classification less expensive during crawls

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## What changed

This cleans up the NLP classifier so crawling more than one page does not retrain the model over and over. The classifier now trains lazily from the packaged CSV, stays cached for the process, and returns a confidence score for the selected category instead of the old misleading accuracy value.

I also removed the runtime `training_data/` generation from classification and stopped the NLP helpers from changing the process working directory. The optional data export helper is still there for experiments, but normal crawls no longer write generated files into the package directory.

Version is bumped to `4.3.0` and the changelog has the release notes.

## Checks

- `.venv/bin/python -m pytest tests/test_nlp.py`
- `.venv/bin/python -m pytest`
- `.venv/bin/python -m flake8 src/[redacted-repo]/modules/nlp/main.py src/[redacted-repo]/modules/nlp/gather_data.py tests/test_nlp.py`
- Real classifier smoke test against the packaged CSV

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
