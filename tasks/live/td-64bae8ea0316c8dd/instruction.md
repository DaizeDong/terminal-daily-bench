# [redacted-repo]: enable systemd-journal logging for correct priority mapping

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

<!-- All contributors please complete these sections, including maintainers -->
# About this change - What it does

Currently, `[redacted-repo]` logs to stderr/stdout which systemd captures with a default
priority (usually INFO), losing the distinction between error and info logs.
This change attempts to use `systemd.journal.JournalHandler` when running
as a service (non-interactive). This handler correctly maps Python log
levels to Syslog priorities, allowing journalpump and other tools to
properly filter error logs.

Falls back to standard stream logging if systemd module is missing or
running interactively.

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
