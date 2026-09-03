# Recover transient post-action failures without rerunning completed work

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## Summary

Cloud Tasks may redeliver a worker task. Before this change, a transient
Firestore output write or successor-task creation failure after an action
completed could cause the action to run again, including another paid model
call. This change records task-specific completion so redelivery replays the
output and downstream work without rerunning the action; delivery count alone
never proves completion.

## Behavior

Two durable records use the workflow bucket and Firestore collection already
in the engine:

1. **Task completion output.** After an action completes, the worker creates
   `_task-completions/<task-token>.json` before writing the node output or
   creating successor tasks. The token hashes the Cloud Tasks queue and task
   names with the execution, node, and group, so it remains stable across
   redeliveries of that task. The object is create-only
   (`if_generation_match=0`) and read with one download. A redelivery that finds
   it replays the Firestore output write and successor-task creation without
   calling the action again. Completion objects carry no synthetic expiry
   metadata; retention follows the workflow bucket's lifecycle policy.

   The existing action cache cannot prove task completion: it is shared by
   action and inputs, and `forceExecution` deliberately bypasses it. The new
   object records the output of one specific task instead.

2. **Owner-fenced task state.** The existing Firestore lock document now records
   `running`, `retryable`, `succeeded`, or `failed`, together with the stable
   task token, a unique delivery-owner token, and a 1,860-second lease. A
   same-task redelivery while the owner is active receives a retryable response;
   an expired owner may be replaced in recovery-only mode; and a delayed owner
   cannot change its replacement's state. If the final success-state write
   fails, the handler makes a best-effort recovery-only transition before
   returning a retryable response; a success write that already committed
   cannot be reopened.

A missing completion object permits action execution only when durable state
explicitly records `recoveryOnly: false`. This covers a new task, a quota 429,
and a transient completion download that occurred before any object bytes were
observed. Post-action and ambiguous completion failures remain recovery-only:
later deliveries may replay saved output but may not call the action, and a
missing object or transient download failure returns a retryable response.

Once completion bytes are downloaded, malformed JSON, invalid encoding,
excessive nesting, or a non-object root fails terminally on the first observed
delivery. Unexpected local parser failures remain retryable but recovery-only,
so a later missing object cannot permit the action to run.

If the action cache or completion-object write fails after output was produced,
the task stops rather than risking another paid call. The handler uses the
deployed queues' 30-attempt limit. Quota 429 errors, including
client-library-wrapped forms, remain retryable; model 5xx errors and timeouts are
not retried automatically.

`ROLE=worker` requires the Cloud Tasks queue name, task name, and retry-count
headers before lock access. These headers identify the delivery; Cloud Run
IAM/OIDC remains the authentication boundary. `ROLE=all` keeps the headerless
local-development path.

## Tests

Covers complete, missing, empty, partial, malformed, and local delivery headers;
nonzero retry counts on a task's first observed delivery; forced-action quota
recovery; transient initial completion reads with absent and present output;
create-only write conflicts and single-request reads; terminal invalid encoding,
JSON, nesting, and root shape; recovery-only unexpected parser failures and
create-conflict read failures; missing recovery output; absence of synthetic
expiry metadata; malformed recovery state; active and expired leases; owner
fencing; definite and ambiguous state-write failures; action-cache and
completion-write failures; wrapped quota errors; the 30-attempt boundary; and
ambiguous successor-task creation.

## Risks / Notes

- A model call and its completion-object write cannot be atomic. If output was
  produced but durable completion cannot be proven, the task stops rather than
  risk another billable action.
- If both the success-state write and its best-effort retryable transition fail,
  the document remains `running` until its lease expires. The configured queue
  retry schedule outlives that lease.
- If a fatal action error occurs and Firestore also cannot record `failed`, the
  handler still acknowledges the task to avoid a potentially billable retry;
  the task document may remain `running` until Firestore TTL cleanup.
- For this protocol, a claimed delivery performs one completion-object read. A
  delivery that executes an action also attempts one create-only object write,
  and a claimed delivery normally performs one fenced state-transition
  transaction after the existing claim transaction.
- Create-only writes prevent this worker protocol from replacing an existing
  completion object. A principal with bucket write permission can still modify
  or delete it.
- Completion objects remain until the workflow bucket's lifecycle policy
  removes them; this repository does not install that policy.
- An ambiguous successor-task response may create a duplicate delivery; the
  existing join seal prevents that duplicate from releasing the downstream node
  twice.
- This change does not add a general workflow watchdog or UI repair path.

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
