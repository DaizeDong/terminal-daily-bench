# Redact tool results in the SDK adapters, not just screen the calls

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

[redacted-ref].

## What changed

Every in-process adapter that holds the tool's return value now passes it
through the shared `[redacted-repo].runtime.redaction` helper before the framework
hands it to the model:

| adapter | return site |
| --- | --- |
| LangChain / LangGraph | `func` + `coroutine` wrappers |
| CrewAI | `func` / `_run` / `run` wrapper |
| OpenAI Agents | plain-callable wrapper + `FunctionTool.on_invoke_tool` |
| Agno | `tool_hook`'s `function_call(...)` |
| browser-use | `Registry.execute_action` |
| Pydantic AI | `WrapperToolset.call_tool` |
| Semantic Kernel | `context.function_result`, after `next(context)` |
| AutoGen Core | new `on_response` — the send leg can only refuse |
| Google ADK | new `make_after_tool_callback()` — `before_tool_callback` never sees the output |

BeeAI (a listener on the tool's `start` event) and the Claude Agent SDK (a
`PreToolUse` hook) hook a pre-action event and carry no output to repair. Each
now says so in its module docstring, where the others document the capability.

`contract.SURFACES` records `sdk-adapter` as `can_redact=True`.

`redact_payload_values` learns to walk objects, redacting their string
attributes in place. Once a framework has wrapped a result it is rarely a bare
string, and rebuilding an arbitrary class from its fields is a guess this
cannot afford to get wrong. Bounded depth, so a self-referencing result object
cannot hang the call. Best-effort by contract throughout: masking never raises
and never fails a call closed.

### Two things found on the way

**No adapter test has been running in CI.** The four modules the issue names
error at *collection* from a bare checkout; with the framework extras actually
installed it is six, and a collection error aborts the whole run. Cause:
`[redacted-repo]/__init__.py` (deliberate — it stops an installed distribution from
shadowing the repo-local runtime, [redacted-ref]) makes `[redacted-repo]` a regular package, so
`adapters/*/[redacted-repo]/<fw>/` can never be found by adding a sys.path entry. A
`tests/conftest.py` extends `[redacted-repo].__path__` with each bundled shim, which is
what the installed wheel layout does anyway. That is +63 tests now running.

**Result redaction built a whole PolicyEngine per string.** The data-boundary
classifier instantiates one when it isn't handed a policy — 6.6 ms of rule
construction, per tool call, for an engine the caller had just built and parked
on `Decision.engine` for exactly this purpose. The adapters now hand it over.
Not a cache, so there is no staleness question: the engine reused is the one
that allowed the call. Measured on st3ve (2-core, 200 samples, median):
**8.11 ms → 0.27 ms** per result.

## Verified on st3ve

A fresh clone, real framework SDKs installed (langchain-core 1.6, crewai
1.15.17, openai-agents 0.22, agno 3.0.1, pydantic-ai-slim 2.35.1,
semantic-kernel 1.44.1, google-adk 2.8, autogen-core 0.7.5), tested against the
built **wheel** rather than the editable install, because the editable layout
is the one that cannot resolve the shims.

**Live leak test** — each adapter driven with its real framework objects and a
tool that reads a config file with two planted credentials (one registered in
the cloak store, one a `ghp_` token the classifier catches). Every case is run
twice, so "masked" only counts because the same tool leaked first:

```
langchain        leaked_unguarded=true  leaked_guarded=false
crewai           leaked_unguarded=true  leaked_guarded=false
openai-agents    leaked_unguarded=true  leaked_guarded=false
agno             leaked_unguarded=true  leaked_guarded=false
pydantic-ai      leaked_unguarded=true  leaked_guarded=false
semantic-kernel  leaked_unguarded=true  leaked_guarded=false
google-adk       leaked_unguarded=true  leaked_guarded=false
autogen-core     leaked_unguarded=true  leaked_guarded=false
browser-use      leaked_unguarded=true  leaked_guarded=false

  github_token: [REDACTED:secret]
  db_password:  @@SECRET:E2E_DB_PASSWORD@@
```

Both passes fire: the classifier masks the token shape, and the cloak store
re-cloaks the registered value back to its placeholder.

**Full suite**, same box, same venv:

| | failed | passed | collection errors |
| --- | --- | --- | --- |
| `origin/main` | 21 | 2290 | 6 |
| this branch | 21 | 2353 | 0 |

Identical failure set — zero regressions, and the 21 are the suite's
pre-existing red.

## Not in scope

Vercel AI SDK and Mastra reach the runtime over `eval-server` and need the
redacted text returned in the HTTP response, which the issue calls out as
separate work.

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
