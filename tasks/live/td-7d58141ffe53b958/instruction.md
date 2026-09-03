# feat(funnel): add [redacted-repo] stream publisher

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## Intent

Add a [redacted-repo] stream publisher to the observation funnel in [redacted-repo]. Streaming is meant to be the primary source of truth for the funnel's three fields (Locked, ChargePortDoorOpen, DoorState.TrunkFront), with Bluetooth as the opportunistic secondary — but until now only the Bluetooth publisher (BleBroadcastPublisher) existed, which inverted that. Added [redacted-repo]StreamPublisher alongside it, feeding the same FieldPath set.

Deliberate dependency-direction decision: the stream client lives in the separate [redacted-repo]-stream PyPI package. Rather than hard-depending on it, [redacted-repo]StreamPublisher follows the existing VehicleDataResultPublisher precedent — it takes a caller-supplied payload as an argument (publish_update(data)) and holds no client, session, or callable able to obtain one. I fetched the real [redacted-repo]-stream source from GitHub to confirm the actual wire shape a stream push takes: a data mapping keyed by signal name (Locked, ChargePortDoorOpen, DoorState with a nested TrunkFront), and that some vehicles stream booleans as literal 'true'/'false' strings rather than JSON booleans even when the stream prefers typed values (confirmed from that package's own make_bool coercion) — the new publisher's translation handles that quirk.

Explicitly out of scope, per direction: no source ranking, precedence, or conflict-resolution logic between Bluetooth and streaming was added — the funnel has none by design today, and that is intentional; a real-world race between the two sources is what will decide ranking, not a guess baked in now. Also out of scope: no changes to vehicle_data or VehicleDataResultPublisher beyond using it as a structural precedent, and no changes to the Home Assistant integration (attaching this publisher there is separate downstream work).

Backwards compatible: purely additive (one new class, two new __init__.py exports). Existing Bluetooth funnel behavior is verified unchanged — all pre-existing funnel tests pass unmodified, and a new regression test proves both publishers reach the same funnel listeners with neither ranked over the other. New tests are colocated in tests/test_funnel_stream.py, matching this repo's existing test_funnel_vehicle_data.py/test_funnel_bluetooth.py style and coverage shape (signal translation edge cases, funnelling/dedup behavior, and proof the publisher cannot originate a request). Full suite (725 tests), ruff, and pyright strict all pass.

## What Changed

- Added `[redacted-repo]StreamPublisher` to `tesla_fleet_api/funnel.py`, a passive publisher that translates a caller-supplied [redacted-repo] stream update (`publish_update(data)`) into `Locked`/`ChargePortDoorOpen`/`DoorState.TrunkFront` observations, matching the `VehicleDataResultPublisher` precedent of holding no client/session/callable of its own.
- Handles the stream's `"true"`/`"false"` string-encoded booleans alongside real JSON booleans, and accepts signal keys matching the `[redacted-repo]-stream` package's own `Signal` enum values without depending on that package.
- Exported `[redacted-repo]StreamPublisher` from `tesla_fleet_api/__init__.py` and documented it in `AGENTS.md` alongside the existing `ObservationFunnel`/`BleBroadcastPublisher` description, clarifying streaming is the intended primary source with Bluetooth as opportunistic secondary (no ranking/precedence logic added between them).
- Added `tests/test_funnel_stream.py` covering signal translation edge cases, funnel dedup behavior, and that the publisher cannot originate a request.

## Risk Assessment

✅ Low: Purely additive, well-isolated change (one new class + two exports) that closely mirrors the existing VehicleDataResultPublisher pattern; traced the absent/null/string-boolean translation logic and found it correct in every case, and the new tests exercise real behavior through the public API without touching existing funnel code paths.

## Testing

Ran the targeted funnel test modules (new tests/test_funnel_stream.py plus the three pre-existing funnel test files) end-to-end via pytest — all 79 tests passed, including the new signal-translation edge cases (string 'true'/'false' coercion, absent-vs-null leaf handling, malformed DoorState), the funnel-dedup/no-re-dispatch behavior, the cannot-originate-a-request proof, and a regression test proving both BleBroadcastPublisher and [redacted-repo]StreamPublisher reach the same funnel listeners with neither ranked over the other. The pre-existing AST-based synchronous-module lock test also still passes with the new class added. Working tree is clean with no stray artifacts from the test run.

## Pipeline

Updates from [git push no-mistakes]([redacted-url])

<!-- no-mistakes-pipeline-attestation:v1 {"head_sha":"[redacted-sha]","steps":[{"step":"intent","status":"completed"},{"step":"rebase","status":"completed"},{"step":"review","status":"completed"},{"step":"test","status":"completed"},{"step":"document","status":"completed"},{"step":"lint","status":"completed"},{"step":"push","status":"completed"},{"step":"pr","status":"running"},{"step":"ci","status":"pending"}]} -->

<details>
<summary>✅ **intent** - passed</summary>

✅ No issues found.
</details>

<details>
<summary>✅ **Rebase** - passed</summary>

✅ No issues found.
</details>

<details>
<summary>✅ **Review** - passed</summary>

✅ No issues found.
</details>

<details>
<summary>✅ **Test** - passed</summary>

✅ No issues found.
- <code>`uv run pytest tests/test_funnel_stream.py tests/test_funnel.py tests/test_funnel_bluetooth.py tests/test_funnel_vehicle_data.py -q` — 79 passed</code>
- <code>`uv run pytest tests/test_funnel.py -k Cannot -q` — the AST-based synchronous-module lock (TestFunnelCannotOriginateWork) still passes with the new publisher added</code>
- <code>Manual code read of the diff (funnel.py `_translate`/`publish_update`, `__init__.py` exports) confirming `_leaf`&[redacted-ref];s absent-vs-None sentinel semantics are preserved for the new publisher and that `TestRegressionWalkthrough.test_streaming_and_bluetooth_both_reach_the_same_listeners` in tests/test_funnel_stream.py exercises both BleBroadcastPublisher and [redacted-repo]StreamPublisher against one funnel with neither ranked over the other</code>
</details>

<details>
<summary>✅ **Document** - passed</summary>

✅ No issues found.
</details>

<details>
<summary>✅ **Lint** - passed</summary>

✅ No issues found.
</details>

<details>
<summary>✅ **Push** - passed</summary>

✅ No issues found.
</details>

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
