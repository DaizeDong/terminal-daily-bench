# Receipt authority deployment registry

The checked-in `deployment.json` is intentionally **inactive**. It is a
deployment template, not evidence that the GitHub authority boundary exists.
While `active` is `false`, both authority workflows terminate with an unranked
blocked decision and the publisher has no path to the ledger.

`deployment_status.blockers` is the machine-readable current gap report. As of
2026-08-06 the repository has only one human collaborator, so that person
cannot both dispatch a run and satisfy `prevent_self_review`. No external
service actor currently dispatches the authority workflows. The registry must
remain inactive until either a real second reviewer exists or an externally
controlled App becomes the source-bound dispatch actor while the human reviews;
a second account or bot controlled by the same person is not independence.

Activation requires a reviewed main-branch change that replaces every template
pin with observed values and activates all six declarations. In particular:

1. Protect `main` with the exact status-check context **and dedicated external
   GitHub App ID** pairs and review controls recorded in the registry. The
   importer and publisher require a successful check from those Apps on the
   exact live source commit; a snapshot of current branch settings is not proof
   that a commit entered while those settings were active. A same-named check
   from a different app is not authority. The built-in GitHub Actions App
   (`id=15368`, `slug=github-actions`) is explicitly forbidden here because
   every same-repository workflow receives that App's `GITHUB_TOKEN` identity.
2. Create distinct `receipt-importer` and `receipt-publisher` environments with
   the exact user IDs recorded in the reviewer registry, required approvals,
   self-review disabled, administrator bypass disabled, and
   protected-branch-only rules. Import and publication re-query immutable
   workflow-run actors and environment review history; a candidate actor or
   dispatching actor cannot approve its own promotion.
3. Pin the exact GitHub CLI executable digest/version used for artifact
   attestation verification.
4. Pin all three workflow file digests and register one real replay signer,
   frozen suite, and Ed25519 public-key registry. Those referenced files must
   exist in the same main checkout and match their digests.
5. Create the dedicated `receipt-authority-ledger` branch, record its immutable
   genesis commit, and protect it against deletion, force pushes and non-linear
   history. Pin an active branch ruleset whose `update`, `deletion`,
   `non_fast_forward`, and `required_linear_history` rules apply to the ledger
   ref. Independently restrict classic branch pushes to one dedicated external
   GitHub App's exact ID and slug, with no user or team push actor and admin
   enforcement enabled. That writer App must be distinct from the external
   source-authorizer Apps and must never be the built-in GitHub Actions App.
   Its short-lived installation token must come from an external OIDC broker or
   equivalent custody boundary that pins the publisher workflow identity; an
   ordinary same-repository `GITHUB_TOKEN` cannot satisfy this requirement.
   Only then set the registry entry active. The
   publisher checks ancestry and protection before its atomic non-force ref
   update and indexes candidate, receipt, import-record and import-attestation
   identities; any duplicate is rejected.

The importer always re-queries GitHub's branch/environment/ref APIs and invokes
`gh attestation verify` itself. Caller-provided control evidence is not an
accepted input. The publisher repeats those checks under a different protected
environment before using the dedicated writer App token. Its ordinary
`GITHUB_TOKEN` remains read-only.

Those control APIs include branch/environment administration reads that an
ordinary `GITHUB_TOKEN` may not expose. Deployment must therefore obtain a
least-privilege, short-lived control-reader token from the external identity
boundary as well; absence of that token is a hard API failure, never a reason to
trust caller-supplied settings. Only the separately allowlisted writer App may
receive ledger-write authority.

Every authority stage also requires its source commit to still be the live
`refs/heads/main` head. The publisher repeats that check together with ledger
protection immediately before compare-and-swap, so a queued old run cannot
continue after a main-branch revocation. The pinned `gh` bytes are copied into a
sealed in-memory executable before either version or attestation verification;
verifier stdout is streamed through a hard size limit.

Different GitHub-hosted jobs and different OIDC subjects are useful provenance
facts, but they are not by themselves distinct write principals. OIDC binds an
attestation to workflow source; it does not narrow the repository-wide
`GITHUB_TOKEN` installation identity used at the Git API. Likewise, current
branch/environment settings cannot prove historical approval after an
administrator temporarily disabled and restored them. The external source App
check and dedicated writer App are therefore required trust roots, not optional
hardening. With only the repository owner and no externally controlled App or
reviewer, this registry must remain inactive.

Do not set a control to `true` merely to make a workflow pass. A mismatch
between registry claims and live state fails closed.
