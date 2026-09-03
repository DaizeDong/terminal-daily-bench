# feat: export images from private event activities

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

Hi @[redacted-repo],

First of all, thank you very much for this project! It has been incredibly helpful.

I wanted to move our family's long-running TimeTree calendar into Notion, and TimeTree Exporter made it possible to preserve years of our calendar history.

While doing that, I noticed that images attached to private events were not included in the export. In our case, many of those images only make sense together with the event they belong to, so I experimented with preserving them as well.

This PR adds an optional `--include-images` feature for private calendars.

### What it does

- Fetches images attached through private event activities
- Reuses activity responses when `--include-comments` and `--include-images` are used together
- Saves images under `timetree_images/{event_uuid}/...`
- Generates `timetree_images.json` to preserve the relationship between events and images
- Records the event UUID, title, start date, relative image path, and original object key
- Skips existing images so interrupted exports can be resumed
- Adds connect/read timeouts so a stalled attachment download does not block the entire export
- Continues the export if an individual image download fails
- Does not change public calendar behavior

I kept this opt-in because it requires additional requests and can take quite a while for large calendars. I also chose not to embed the images into the ICS itself; the JSON manifest is only a sidecar for preserving the event-to-image relationship.

### Testing

I tested this with my own private calendar:

- about 3,400 events
- 6,264 attached images exported
- interrupted and resumed the export successfully
- manually checked several images against their event titles and dates

Automated checks:

- 79 tests passed
- `ruff check` passed
- `ruff format --check` passed
- `git diff --check` passed

I'm not sure whether this kind of sidecar image export fits the intended scope of TimeTree Exporter, since it goes a little beyond ICS output itself. If you would prefer to keep the project focused strictly on ICS export, please feel completely free to close this PR. I would absolutely understand.

Either way, thank you again for making this project available. It helped me a lot with preserving our family's TimeTree history.

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
