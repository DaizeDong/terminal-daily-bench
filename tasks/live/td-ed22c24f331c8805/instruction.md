# Fix stale keep-alive connection reuse; unpin werkzeug ([redacted-ref])

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

- Fix reuse of stale keep-alive connections during recording: [redacted-repo] forced urllib3's `is_connection_dropped` to always return `False` (a 2014 Windows playback fix, [redacted-ref]), which let recording connections reuse a server-closed socket and raise `ProtocolError('Connection aborted', ...)`. Now scoped to playback stubs only.
- Add a regression test for the above (`tests/integration/test_stale_connection.py`).
- Drop the `werkzeug==2.0.3` pin and require `httpbin>=0.10.3` in both test extras, now that httpbin 0.10.3 fixes its `/bytes` endpoint to return `bytes` instead of `bytearray`. [redacted-ref].

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
