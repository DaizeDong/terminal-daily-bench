# Improve StartupSummaryRow for notifications for email/webhook

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

I thought the previous display for this information was cluttered and too long, line wrapping on my terminal
I think this looks cleaner

Previous style:
`* Notifications:             On (email: active, inactive, monitored tracks, every song, songs on loop, errors | webhook: active, inactive, monitored tracks, every song, songs on loop, errors)
`

This-PR style:
```
* Notifications (email):     On (active, inactive, monitored tracks, every song, songs on loop, errors)
* Notifications (webhook):   On (active, inactive, monitored tracks, every song, songs on loop, errors)

```

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
