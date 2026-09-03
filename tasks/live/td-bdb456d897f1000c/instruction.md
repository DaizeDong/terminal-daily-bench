# Support for compact ntfy updates

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

The recently added native ntfy webhook code sends the same content to each ntfy notification as the notification emails. 

For this PR, If NTFY_SHORT is True, an alternative and more compact version of the alerts will be used. Some users may find this easier to view on mobile devices and smart watches.

Also added some currently unused support for setting the 'priority' and 'tags' for ntfy notifications

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
