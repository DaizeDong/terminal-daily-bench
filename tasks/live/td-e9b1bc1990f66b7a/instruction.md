# fix: AR verification reports correctly + reporting/threat-score correctness

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

Follow-up to [redacted-ref], working the deferred correctness findings from the audit.

### Active-Response verification tools were reporting wrong answers
The `check_*` tools that confirm a state-changing action built free-text `'"1.2.3.4" AND "firewall-drop"'` queries. These route through the Indexer's `simple_query_string`, where `AND` is a literal search term and `default_operator=AND` then requires the token "and" in the document — which AR alerts don't contain — so they **reliably matched nothing and reported a blocked IP / isolated host / disabled user as *not* actioned**. Now they use structured `srcip`/`rule_groups`/`agent_id` filters with a bounded time window.

- `check_agent_isolation` no longer equates "disconnected" with "isolated" — Wazuh host-isolation deliberately preserves the manager link, so the old heuristic both missed real isolations and misfired on merely-offline agents.
- `check_process` queries the specific PID instead of paging the first 500 (a running process beyond the page was reported killed) and surfaces the inventory scan time.
- `check_file_quarantine` keys off a FIM deletion of the exact path, not a substring match over the stringified event (which false-positived on any path containing "quarantine").

### Reporting correctness
- `get_sca_policy_checks` scores over applicable checks only — 50 passed + 50 N/A previously read as 50%.
- `get_top_security_threats` uses a severity-weighted score that no longer saturates, so a chatty level-3 rule can't outrank a targeted level-15 attack (verified by a ranking test).

### Tool descriptions
Corrected the LLM-facing descriptions that overstated capability (`analyze_security_threat`, `check_ioc_reputation`, log-collector stats, `block` duration).

### Session store
Don't wipe the store on shutdown — a single pod restart previously 404'd every other instance's live Redis sessions; TTL handles expiry.

+7 regression tests (structured-query assertions, PID query, N/A denominator, threat ranking); full suite **266 passing**, lint clean, boots and serves 55 tools. `docs/AUDIT_FINDINGS.md` updated.

<!-- This is an auto-generated comment: release notes by coderabbit.ai -->

## Summary by CodeRabbit

* **Bug Fixes**
  * Improved threat scoring by prioritizing severity and affected-agent spread.
  * Corrected SCA scoring to exclude not-applicable checks.
  * Improved vulnerability, quarantine, process, and active-response verification accuracy.
  * Preserved shared sessions when shutting down an instance.
  * Clarified tool descriptions and analysis results.

* **Documentation**
  * Updated audit documentation with resolved verification and scoring findings, while retaining outstanding issues.

* **Tests**
  * Added regression coverage for verification queries, SCA scoring, and threat ranking.

<!-- end of auto-generated comment: release notes by coderabbit.ai -->

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
