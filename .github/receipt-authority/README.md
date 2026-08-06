# Receipt authority deployment registry

The checked-in `deployment.json` is intentionally **inactive**. It is a
deployment template, not evidence that the GitHub authority boundary exists.
While `active` is `false`, both authority workflows terminate with an unranked
blocked decision and the publisher has no path to the ledger.

`deployment_status.blockers` is the machine-readable current gap report. As of
2026-08-06 the repository has only one collaborator, so the dispatching actor
cannot also satisfy `prevent_self_review`. No automation trigger creates an
independent reviewer. The registry must remain inactive until a real second
reviewer with repository access and the other listed controls exist.

Activation requires a reviewed main-branch change that replaces every template
pin with observed values and activates all six declarations. In particular:

1. Protect `main` with the exact status-check context **and GitHub App ID** pairs
   and review controls recorded in the registry. A same-named check from a
   different app is not authority.
2. Create distinct `receipt-importer` and `receipt-publisher` environments with
   the exact user IDs recorded in the reviewer registry, required approvals,
   self-review disabled, and protected-branch-only rules. Import and publication
   re-query immutable workflow-run actors and environment review history; a
   candidate actor or dispatching actor cannot approve its own promotion.
3. Pin the exact GitHub CLI executable digest/version used for artifact
   attestation verification.
4. Pin all three workflow file digests and register one real replay signer,
   frozen suite, and Ed25519 public-key registry. Those referenced files must
   exist in the same main checkout and match their digests.
5. Create the dedicated `receipt-authority-ledger` branch, record its immutable
   genesis commit, and protect it against deletion, force pushes and non-linear
   history. Pin an active branch ruleset whose `update`, `deletion`,
   `non_fast_forward`, and `required_linear_history` rules apply to the ledger
   ref. Independently restrict classic branch pushes to the one pinned GitHub
   App ID, with no user or team push actor and admin enforcement enabled. Only
   then set the registry entry active. The
   publisher checks ancestry and protection before its atomic non-force ref
   update and indexes candidate, receipt, import-record and import-attestation
   identities; any duplicate is rejected.

The importer always re-queries GitHub's branch/environment/ref APIs and invokes
`gh attestation verify` itself. Caller-provided control evidence is not an
accepted input. The publisher repeats those checks under a different protected
environment before receiving `contents: write`.

Every authority stage also requires its source commit to still be the live
`refs/heads/main` head. The publisher repeats that check together with ledger
protection immediately before compare-and-swap, so a queued old run cannot
continue after a main-branch revocation. The pinned `gh` bytes are copied into a
sealed in-memory executable before either version or attestation verification;
verifier stdout is streamed through a hard size limit.

Do not set a control to `true` merely to make a workflow pass. A mismatch
between registry claims and live state fails closed.
