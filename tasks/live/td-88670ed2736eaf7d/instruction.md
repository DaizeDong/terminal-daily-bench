# Neutral, dead-end-free threat-group and case-study selectors

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

Automated by **agent-loop** — pi worked this issue on a fresh clone of `[redacted-repo]`; changes were gated outside the agent on agent-1.

[redacted-ref]

## How to test
```bash
git fetch origin && git checkout agent/[redacted-ref]
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
streamlit run "00_👋_Welcome.py"
```
Then open the printed local URL.

**Confirm each acceptance criterion:**
- [x] Threat-group and ATLAS case-study selectors have no pre-selected first item; the first visible state is a neutral prompt
- [x] Every selectable group resolves to at least one associated technique; every selectable ATLAS case study has a usable procedure and extracted technique set
- [x] Groups/case studies with no usable techniques are removed or explicitly disabled with a reason, not silently selectable
- [x] Search by group name and alias remains available
- [x] Tests against the shipped Enterprise, ICS, and ATLAS data assert every enabled option resolves to ≥1 technique and that no implicit first selection exists

## Gates (non-authoritative)
- ✅ **files_non_empty** — 3 non-empty file(s) changed
- ✅ **containment** — diff stays within the allowed lane
- ✅ **verify** — pytest: 247 passed, no failures (browser/e2e excluded)

> **Draft.** Browser/e2e tests were NOT run in-gate — run them and review before merging. Nothing here is auto-merged.

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
