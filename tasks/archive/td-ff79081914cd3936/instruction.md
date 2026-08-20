# Add medical observational research domain profile

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## Summary

This PR adds a lightweight `medical_observational` domain pack for retrospective clinical and epidemiology research topics, without changing the core 23-stage pipeline.

It is intended to help [redacted-repo] route topics such as retrospective cohort, case-control, cross-sectional, STROBE, EHR/HIS, clinical registry, and trauma registry studies into a safer methodology-aware prompt layer.

## What changed

- Adds `researchclaw/domains/profiles/medical_observational.yaml` with medical observational study metadata, STROBE-oriented outputs, and privacy/ethics safeguards.
- Adds `MedicalObservationalPromptAdapter` to require ethics/IRB status, de-identification confirmation, data access planning, variable definitions, missingness planning, and cautious interpretation of observational associations.
- Registers the adapter and detector keywords for medical observational topics.
- Adds a synthetic-only demo note for a trauma registry retrospective cohort topic.
- Adds tests for profile loading, keyword routing, adapter dispatch, and safety-oriented prompt blocks.

## Motivation

Medical observational research has some domain-specific requirements that are easy for a generic autonomous research pipeline to miss: IRB/ethics status, de-identification, STROBE reporting, participant-flow counts, Table 1, missing-data handling, and careful separation of association from causation.

This contribution was informed by my public `TUANZIDING/medical-paper-pipeline` project, but it intentionally contributes only a small [redacted-repo]-native domain pack rather than importing or replacing any pipeline logic.

## Boundaries

- Does not add a medical statistics executor.
- Does not move or replace the 23-stage runner.
- Does not include real patient data, hospital-specific workflows, or identifiable clinical examples.
- Does not claim to provide clinical advice; it is research-methodology assistance.

## Test plan

- [x] `.venv/bin/python -m pytest tests/test_domain_detector.py tests/test_prompt_adapter.py tests/test_universal_codegen_integration.py tests/test_robotics_adapter.py tests/test_neuroscience_domain.py -q`
- [x] `.venv/bin/python -m pytest -q`
- [x] `git diff --check`

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
