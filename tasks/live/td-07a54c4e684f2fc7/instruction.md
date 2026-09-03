# Codex/update arxiv preprint citation

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## Summary by Sourcery

Add a new LaTeX platform recommendation table for zero-skip DataLoader choices, ensure generated plots use embeddable fonts, and update the README to reference the new arXiv preprint and citation.

New Features:
- Generate a per-platform zero-skip DataLoader recommendation LaTeX table, including integration into the table generation workflow.

Enhancements:
- Configure matplotlib PDF/PS font types for better compatibility with LaTeX and vector outputs.

Documentation:
- Update README with the current preprint link and BibTeX citation, and clarify citation guidance.

Tests:
- Add coverage to verify the platform recommendation table contents, formatting, and decoder inclusion/exclusion rules.

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
