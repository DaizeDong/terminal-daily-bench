# Contributing / submitting results

You do NOT need the private construction pipeline to contribute — you run the day's
tasks with your own model or scaffold and submit the results. Ingest records a
content-addressed patch as **pending**; it does not score it. A later project-controlled
offline replay may issue a digest-bound receipt. Only receipt-backed results enter the
verified ranking, and semantic verifier exploits remain a separately measured risk.

## Submission format

One JSON line per `(model, task)` cell, POSTed by the harness on completion:

```json
{ "date": "YYYY-MM-DD", "submitter": "your-handle",
  "model": "your-model", "model_build": "immutable-build-id",
  "scaffold": "your-scaffold", "harness_version": "immutable-version",
  "task": "td-...",
  "patch": "<unified diff your model produced>",   // stored for operator replay
  "reward_claimed": 1.0 }                           // advisory only, never ranked
```

Run `web/submit_result.py` to validate + record; the deployment auth layer supplies
`--authenticated-submitter` separately from the JSON body. Operators freeze a trusted
manifest and run `web/replay_worker.py`; only a v2 Ed25519 receipt signed by a pinned
worker authority can promote a row. The ingest/promoter holds public keys, never the
worker private key.

Replay operators install the optional authority dependency explicitly:

```bash
pip install -e '.[replay]'
```

Signing and verification use Python `cryptography`'s in-process Ed25519 primitives.
The authority code neither searches `PATH` nor starts an external OpenSSL process.

Deployment must make that separation physical: run the public ingest/promoter and
receipt signer under distinct UIDs (or equivalent service identities), keep the
private key readable only by the signer, and mount the frozen manifest/public-key
registry read-only into the promoter. `0600`/`0444` mode bits under one shared owner
are not an authority boundary because that owner can chmod/replace the files. The
worker rejects a private key placed under the submission store, work tree, trusted
task tree, or source checkout and signs UID/mode facts into the receipt, but an
operator must still audit the service identities and mount/ACL policy.

## Integrity rules (enforced, not requested)

1. **Scoring is execution-only.** A scaffold produces a candidate repo state; scoring
   is always harbor re-laying the protected `tests/` on a face the scaffold never
   touched. No scaffold ever scores.
2. **Patches may not edit tests.** Submission validation rejects test, traversal and
   Git-metadata paths; protected verifier bytes are also pinned in the replay receipt.
3. **Promotion requires an enforced egress cut, not a request bit.** The signed receipt
   must bind pinned runner/Harbor/image bytes and a container runtime fixed by canonical
   absolute path, binary SHA-256, exact version, and kind. The worker may own or write
   neither the runtime nor its parent; neither may be group- or world-writable. A
   reachable control canary, blocked isolated canary, and `credentials_forwarded=false`
   are also mandatory. Without all of those, the result stays unranked.
4. **Every attempt pins its own image bytes.** Before Harbor starts, the worker copies
   the SIF into a worker-private attempt directory and verifies the policy digest. It
   rechecks that copy at the Harbor-to-canary boundary, revalidates the runtime in the
   canary preflight, and rejects any snapshot mismatch instead of issuing a receipt.
5. **Live tasks are operator-replayed.** Gold and protected bodies stay private;
   pending community patches remain unranked until that replay exists.
6. **Community rankings require complete frozen-roster coverage.** One authenticated
   `(suite, submitter, model build, harness version, task)` cell is accepted. Partial,
   duplicate, cross-date and self-reported-only rows remain in the unranked view;
   official controlled evaluations remain a separate table.

The worker now fails closed on the complete Harbor authority binding: policy and
receipts bind the canonical `harbor_binary_path`, launcher digest/version, canonical
`harbor_package_root`, SHA-256 of the complete Harbor package plus network-patch tree,
and immutable runtime-control facts, and revalidate them before and after replay. The
authoritative result reader rejects symlinks and hardlinks, pins root/run/result with
`O_NOFOLLOW` file descriptors, and performs bounded read, schema/reward validation,
and receipt hashing from one already-open snapshot.

Fake runner and Fake Harbor tests establish only the Python/command boundary. They do
not prove a production replay, network isolation, or an authority deployment.
Production replay remains a blocker until a real Harbor replay and both the reachable
control and blocked isolated canaries pass, and an operator audits distinct signer /
promoter UIDs, the signer-only private-key mount, and read-only manifest/public-key
mounts. The audit must also exercise the Harbor-tree and result-snapshot controls with
the real installed package and replay artifacts.

## Adding a scaffold / harness

Register a `HarnessAdapter` under `terminal_daily_bench.adapters`. Two integration
paths are supported:

- `external-diff`: return `AdapterResult(patch=..., telemetry=...)`; the runner
  sends the diff through the oracle-apply protected-test gate.
- `harbor-agent`: return a declarative `HarborRunSpec`; the runner invokes the
  installed Harbor agent and reads Harbor's protected-test result afterward.

Adapters configure candidate production only. They must never read `result.json`,
compute reward, or inspect protected tests/gold solutions. Credential values must
remain in `HarborRunSpec.process_env`; `agent_env` contains only `${ENV_NAME}`
templates. Add a dry-run assertion and a fake-Harbor command-boundary integration
test like `tests/test_vendor_harness.py` for every installed-agent adapter.
