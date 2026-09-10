# Added session forwarding via baggage headers to httpx and requests

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## Description of the change

This PR adds the ability to instrument outgoing request made via HTTPX and requests with the [redacted-repo] session IDs and execution scope IDs in the baggage header.

Propagation of the session and execution scope is controlled with two parameters `enabled_urls` and `enabled_headers`. By default `enabled_headers` is `["baggage"]`.

Only requests to URLs included in the `enabled_urls` will include the propagated session and execution scope IDs.

If there is an existing `baggage` header in the request is will be updated to include the new values. All other headers are left untouched. If for some reason the request `baggage` header already includes [redacted-repo] session and execution scope IDs they will be updated.

If both global and client/session instrumentation is enabled, the client/session instrumentation takes precedence over the global.

There are three ways to manage instrumentation:

#### 1. Global instrumentation with `[redacted-repo].init()`.

```python
import [redacted-repo]

[redacted-repo].init(
    '<access_token>',
    environment='staging',
    tracing={
        "propagation": {
            "enabled_urls": [
                "[redacted-url]  # Can be an exact URL
                r"^http:\/\/example.com\/.*",  # Can be a RegEx
            ]
        }
    }
)
```

#### 2. Global instrumentation with the propagation manager

In HTTPX...

```python
from [redacted-repo].contrib.httpx import HTTPXContextPropagationManager

HTTPXContextPropagationManager.instrument(
    enabled_urls=[r"^http:\/\/example.com\/.*"],
)

# To remove instrumentation
HTTPXContextPropagationManager.uninstrument()
```

In requests...

```python
from [redacted-repo].contrib.requests import RequestsContextPropagationManager

RequestsContextPropagationManager.instrument(
    enabled_urls=[r"^http:\/\/example.com\/.*"],
)

# To remove instrumentation
RequestsContextPropagationManager.uninstrument()
```

#### 3. Individual Client/Session instrumentation with the propagation manager

In HTTPX...

```python
import httpx
from [redacted-repo].contrib.httpx import HTTPXContextPropagationManager

client = httpx.AsyncClient(base_url="[redacted-url])

HTTPXContextPropagationManager.instrument_client(
    client,
    enabled_urls=[r"^http:\/\/example.com\/.*"],
)

# To remove instrumentation
HTTPXContextPropagationManager.uninstrument_client(client)
```

In requests...

```python
import requests
from [redacted-repo].contrib.requests import RequestsContextPropagationManager

session = requests.Session()

RequestsContextPropagationManager.instrument_session(
    session,
    enabled_urls=[r"^http:\/\/example.com\/.*"],
)

# To remove instrumentation
RequestsContextPropagationManager.uninstrument_session(session)
```

## Type of change

- [x] New feature (non-breaking change that adds functionality)

## Related issues

- SDK-578

## Checklists

### Development

- [x] Lint rules pass locally
- [x] The code changed/added as part of this pull request has been covered with tests
- [x] All tests related to the changed code pass in development

### Code review

- [ ] This pull request has a descriptive title and information useful to a reviewer. There may be a screenshot or screencast attached
- [ ] "Ready for review" label attached to the PR and reviewers assigned
- [ ] Issue from task tracker has a link to this pull request
- [ ] Changes have been reviewed by at least one other engineer

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
