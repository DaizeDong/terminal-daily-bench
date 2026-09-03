# Install bundled Agent Skill

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

<!-- This is an auto-generated comment: release notes by coderabbit.ai -->
## Summary by CodeRabbit

- **New Features**
  - Added experimental CLI support to install the bundled Agent Skill for Codex or Claude Code.
  - Supports project or user installation scopes.
  - Existing skills are preserved by default, with optional overwrite support and protections for symlinks and non-directory targets.

- **Documentation**
  - Added comprehensive reference, usage, and experimental-feature guidance.
  - Updated quick references and setup instructions.

- **Packaging**
  - Bundled the Agent Skill in wheel and source distributions.
<!-- end of auto-generated comment: release notes by coderabbit.ai -->

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
