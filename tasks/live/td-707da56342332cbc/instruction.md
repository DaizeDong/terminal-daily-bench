# strip script and noscript content in get_base_url

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

>>> get_base_url("<script>var t = \"<base href='[redacted-url]>\";</script>", "[redacted-url])
    '[redacted-url]

get_base_url only runs remove_comments before scanning for `<base href>`, so a `<base>` written as text inside `<script>` or `<noscript>` is picked up and used to resolve relative URLs. A browser never parses tags inside those elements, so it ignores such a base and resolves against the real one; a consumer that reflects untrusted markup into a script/noscript block ends up resolving links against an attacker-chosen base.

get_meta_refresh already drops script/noscript for the same reason. This does the same in get_base_url before the search. A `<base>` that follows the ignored content is still returned.

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
