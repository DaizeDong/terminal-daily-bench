# Keep the event scheduler off while restoring a backup

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

A restore that has binary logs to apply can get stuck on a duplicate key. [redacted-repo] restarts mysqld with the binary log disabled for the restore phases but leaves event_scheduler at its default ON, and a physical basebackup keeps events in ENABLED state. Every restored event whose schedule lapsed during the restore therefore fires within seconds of startup, and the rows it writes collide with the transactions still being replayed from the binary logs. The applier stops with HA_ERR_FOUND_DUPP_KEY and retrying does not help, because the row is already there. Rebuilding the node only runs the same lottery again.

Pass --event-scheduler=OFF on the restarts that already disable the binary log. Only the restore phases run that way, so recognising them needs no new parameter, and this has to be a startup option rather than a SET GLOBAL: by the time we could connect and issue one, the events have already fired.

The restart that finalizes a restore asks for the binary log back and so produces no options at all, which drops MYSQLD_OPTS from the systemd environment file entirely. The restored server comes back with whatever its configuration file says, rather than a hardcoded ON that would override an operator who turned the scheduler off deliberately.

The two option lists that had drifted apart are now one helper, so a change like this cannot land in the subprocess path alone while production, which goes through [redacted-repo]_mysql_env_update and systemd, keeps the old behaviour. That path had no tests at all; it has some now.

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
