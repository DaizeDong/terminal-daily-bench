# Expose restored backup and chain position in /status/restore

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

During an incremental restore /status/restore reported only the phase and
byte/binlog counters, so neither operators nor customers could tell which
backup in the chain was being applied or how many remained. In INC-1429 a
broken chain was retried repeatedly with no easy way to see where the restore
was, forcing correlation of ~30s status logs against a pre-restore backup
listing.

RestoreCoordinator already tracks everything needed (required_backups, the
prerequisite full + earlier incrementals; required_backups_restored; and the
target stream_id applied last), it was just never surfaced. Add a
restore_chain_progress property that reports the current backup name, whether
it is incremental, and a 1-based index/total (chain length is
len(required_backups) + 1), and include those four fields in the
/status/restore response. A plain non-incremental restore collapses to 1 of 1.

This is the [redacted-repo] half of surfacing chain position; the management plane,
Ops CLI and Console consume these fields separately.

[MYC-174]

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
