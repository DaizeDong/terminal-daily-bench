# Fix webhook URL validation and empty follower notifications

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## Problem
Two notification-related bugs were affecting the tool:

1. **[redacted-ref]:** Webhook URL validation was rejecting valid URLs with only a root path (e.g., `[redacted-url]), causing unnecessary webhook configuration errors.

2. **[redacted-ref]:** Email and webhook notifications were being sent when a follower/following count changed numerically, even when the actual follower/following list hadn't changed, resulting in empty notifications with no meaningful content.

## Solution
### Webhook URL Validation Fix
Modified `validate_webhook_url()` to accept both:
- Paths with content (e.g., `/webhook`, `/api/hooks`)
- Root path (`/`)

Previously, the function required `path.strip("/")` to be non-empty, which rejected root-only URLs.

### Follower Notification Fix
Changed the notification conditions to only send alerts when there are actual followers/followings added or removed, not just when the count changes:
- Email notifications now check `added_followers_list or removed_followers_list` instead of `followers_count != followers_old_count`
- Applied the same logic to following notifications for consistency
- Updated webhook notifications to match email conditions

## Testing
- All 91 notification and webhook tests pass
- All 7 follower comparison tests pass
- Verified webhook URL validation accepts `[redacted-url]

[redacted-ref]
[redacted-ref]

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
