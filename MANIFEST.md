# MANIFEST -- what ships, what is deliberately withheld

## Shipped (this public bundle)
- `terminal_daily_bench/` — execution scorer, CLI, and first-party harness adapters.
- `web/` — dashboard, pending submission recorder, official replay worker, aggregate.
- `tasks/` — task-package SCHEMA + archived (full) tasks + live (replay-gated) tasks.
- `.importlinter` — the moat contract; `README`, `CONTRIBUTING`, `LICENSE`.

Replay operators install the optional authority dependency with
`pip install -e '.[replay]'`. Receipt signing and verification use the in-process
Ed25519 implementation from Python `cryptography`; the authority code does not search
`PATH` or invoke an external OpenSSL process.

## Deliberately NOT shipped (the moat)
- The **task-construction pipeline** (`td_pipeline/`: mining, selection, env
  generation, difficulty synthesis, repo universe) — how the daily set is chosen/built.
- The **RC-VH acceptance gate** (`rcvh/`: cascade, gate, auditor, certificate, the
  mutant/sentinel soundness probes) — how a task is certified before it enters the set.
- Any secret — model-endpoint credentials, billing configuration, API keys, private
  hostnames — MUST NEVER appear here (enforced by the release secret-scan). The
  public `model_eval` calls a generic OpenAI-compatible endpoint you configure by env.
- The production Ed25519 receipt private key, frozen execution policy, deployment
  ACLs/service identities, canary endpoint, and replay artifacts are not shipped.

## Why the cut is safe
Protected-test replay is the only reward authority; a submitted claim cannot bypass
it. That is an execution-integrity property, not evidence that every verifier rejects
every semantically wrong patch. The shipped package does not import `td_pipeline` or
`rcvh`; consumers cannot reproduce task construction/certification.

The receipt authority exists only in a deployment where signer and ingest/promoter
are distinct UIDs (or equivalent service identities), the private key is signer-only,
and the manifest/public-key registry are read-only promoter mounts. `0600`/`0444`
under one shared owner is not isolation. The code rejects obvious key co-location and
records UID/mode facts, but this bundle is not evidence that those deployment
boundaries or the real Harbor/egress canary have been exercised.

The signer process cannot directly publish a score: it can only transition a row to
`receipt_ready`, where the receipt digest is visible but `verified_reward` stays null.
Promotion is a separate command that re-verifies the receipt and fails closed when
its effective UID is root or equals the signed worker UID. This is code-boundary
evidence, not a substitute for an operator proving the two real service identities.

The frozen policy also pins the container runtime by canonical absolute path, binary
SHA-256, exact version, and kind. The worker must not own or be able to write the
runtime or its parent, and neither may be group- or world-writable. Each replay copies
the SIF into a worker-private attempt directory, fixes its policy digest, checks it
before Harbor and at the Harbor-to-canary boundary, and revalidates runtime facts in
the canary preflight. Snapshot mismatch fails closed.

The code now fails closed on the complete Harbor authority binding. Policy and
receipts bind the canonical `harbor_binary_path`, launcher digest/version, canonical
`harbor_package_root`, SHA-256 of the complete Harbor package and network-patch tree,
and immutable runtime-control facts, and revalidate them before and after replay. The
authoritative result reader rejects symlinks and hardlinks, pins root/run/result with
`O_NOFOLLOW` file descriptors, and uses one bounded, already-open snapshot for reward
validation and hashing.

Fake runner and Fake Harbor tests prove code boundaries only. They do not prove a
production replay, network isolation, or receipt-authority deployment. Production
replay remains a blocker until a real Harbor replay plus reachable-control and
blocked-isolated canaries succeed and an operator audits distinct signer/promoter
UIDs, a signer-only private-key mount, and read-only manifest/public-key mounts, and
the Harbor-tree/result-snapshot controls are exercised and audited against the real
installed package and replay artifacts.

## Scope of this bundle (honest)
- **Functional adapters shipped:** `single_shot` plus Harbor-native `claude-code` and
  `codex`. The command boundary is locally tested; real provider/container cells still
  require the unpublished patched Harbor/Singularity environment described in README.
- **Sample tasks:** 1 per split (archive/live) as a template; full dated daily suites are
  served from the site (live submissions require official replay receipts).
- **`web/leaderboard_data.json`** is reference data from the full evaluation, not a
  bundle-reproduced artifact.
