# fix(arena): credential custody scanning/cleanup + strict lease identity (H2/H3)

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

H1 ([redacted-ref]) wave work targeting the `arena` integration branch: three bounded-read / decomposition hardening fixes in `core/arena`, each RED-controlled or characterization-guarded before the change. Full `tests/core/arena/` is green (411 passed).

## [redacted-ref] — bound label companion reads before summary decode
`label_summary_for_trace(..., limit=1)` globbed `*/<trace>/labels.jsonl.gz` across the whole corpus and decoded every matching companion before slicing `rows[:limit]`. A 64-project probe decoded all 64.

**Change:** resolve the single owning companion first (a bare-trace address is owned by exactly one project) and decode only that companion. Directory listing stays cheap; the per-companion gzip decode is the avoided cost. A companion set that can't be bound to one canonical owning project fails closed instead of silently unioning across projects. `verify_labels` over the decoded rows and the deterministic envelope (count/items/truncated) are unchanged.

**RED→GREEN:** `test_limit_one_summary_reads_only_the_owning_companion` counts `_decode_rows` calls with 64 planted companions.
Before: `AssertionError: assert 64 == 1`. After: 1 decode; forged/mismatched companions still fail closed.

`[redacted-ref]`

## [redacted-ref] — extract authoritative Trace Map resolver from labels
`authoritative_trace_materialization_ref` had accreted project-registration parsing, source-repo resolution, and Trail-projection reconstruction inside generic label persistence, making `labels.py` a second owner of project identity and Trail reconstruction.

**Change (no observable behavior change):**
- `repo_identity.registered_source_repo` now interprets `~/.[redacted-repo]/projects/<slug>/project.json` (the repository-identity boundary): `None` when unregistered, a fail-closed `ProjectRegistrationError` with the frozen messages otherwise.
- new focused `core/arena/trace_materialization.py` owns the resolver + Trail reconstruction, mapping the registration signal onto the same `LabelIntegrityError` messages.
- `labels.py` re-exports the resolver; `origin.py` and label reverification use the exact same resolver object. The label module no longer parses project identity or builds Trail projections.

**Characterization-first:** `tests/core/arena/test_trace_materialization.py` locks all five branches (registered rebuild, unregistered record-only fallback, no-source-field, unavailable source, failing Trail reconstruction), written and green before the extraction and still green after.

`[redacted-ref]`

## [redacted-ref] — bound action-output reads in run-as-trace preview
`_bounded_text` (the reader the issue names `_read_text`) read the complete stored stdout/stderr via `Path.read_text` and only then truncated to the 4096-char preview, fully loading an oversized valid output into memory.

**Change:** read only `handle.read(remaining + 1)` via a text-mode handle — enough for the preview plus one char to detect overflow. Text-mode read decodes exactly the bytes needed for those characters, so UTF-8 `errors="replace"` behavior and the visible truncated output are byte-identical to whole-file decode. `RunStore.verify()` still hashes the full bytes in binary mode, so integrity verification is unweakened.

**RED→GREEN:** `test_large_action_output_is_previewed_without_reading_the_whole_file` wraps `Path.open` on a 200k-char stdout and asserts the text-mode reader issued no unbounded read.
Before: `assert all(size not in (-1, None) ...)` → `assert False` (an unbounded `read(-1)`). After: a single bounded read; preview unchanged.

`[redacted-ref]`

## Review repair (non-author codex review, DOES NOT WORK → repaired)

**Category A — [redacted-ref] owning-companion selection could pick a stale owner** (`[redacted-sha]`). The first cut inferred ownership from legacy `traces/v1/.../trace.json` presence. A supported `trace_record_only=True` ingest writes the fresh canonical v2 record + labels companion but skips the `trace.json` projection (`core/ingest.py`), so a stale project could be the only `trace.json` holder: the helper silently selected it, omitted the fresher project's current labels, and bypassed fail-closed ambiguity handling.

Repair (RED-first): ownership now binds through the same canonical corpus/freshness resolution normal reads use (`trace_corpus.resolve`). With multiple cross-project companions, only the resolved owner's companion is decoded (boundedness kept: at most one decode); when the corpus cannot bind exactly one owning companion, the read fails closed (`LabelIntegrityError`, never a silent pick or cross-project union).

RED→GREEN evidence (both controls fail on pre-repair head `[redacted-sha]`):
- `test_summary_follows_the_canonical_corpus_owner_not_a_stale_trace_json_owner` — combines the two `test_origin_join` halves into the stale-owner scenario (older `trace.json` owner with 1 stale row vs fresher canonical-only owner with 2 current rows). Before: `AssertionError: assert 1 == 2`. After: summary reflects the fresher owner's full labels.
- `test_summary_fails_closed_when_no_canonical_owner_binds_the_companions` — before: `Failed: DID NOT RAISE LabelIntegrityError`. After: fails closed on genuine ambiguity.
- The [redacted-ref] read-counting control re-proves boundedness post-repair: still exactly one `_decode_rows` call with 64 matching companions.

**Category B — [redacted-ref] test strength** (`[redacted-sha]`). Added `test_bounded_preview_is_byte_identical_to_whole_read_then_slice`: an 11-case parity matrix computing the expected preview via the old implementation verbatim (whole-file `Path.read_text(errors="replace")` then slice) and asserting byte-identical output plus identical remaining-budget arithmetic. Covers the exact 4096/4097 boundary, a 4-byte char straddling the preview read window, multibyte throughout, malformed bytes (early / truncated at boundary / truncated at EOF), and `\r\n` + lone-`\r` universal-newline translation parity. All cases green against the bounded implementation.

Post-repair gate: `pytest tests/core/arena/ tests/cli/test_bench_cli.py -q` → **438 passed**.

---

## Review repair (non-author codex review at [redacted-sha])

A fresh non-author review returned DOES NOT WORK with five Category A findings and one Category B. All repaired RED-first on this branch (commits `[redacted-sha]`, `[redacted-sha]`); the chunk-overlap scanner logic itself was verified correct by the review (exhaustive boundary-combination check) and is byte-identical.

**A1 — deliberate ASCII-only lease-identity narrowing (box.py).** The shared selector refuses a clean id fused to a non-ASCII separator (em dash, NBSP) where the old permissive regex accepted it. Ruling option (b) chosen: keep ASCII-only fail-closed — real Crabbox output delimits the lease id with ASCII whitespace/punctuation, and the timed-out path has pinned exactly this refusal (unicode-left/right cases) since A7; widening the completed path would re-split the two paths' accept sets. The narrowing is now documented in the parser docstring and pinned as intended behavior by `test_completed_warmup_refuses_non_ascii_fused_separator_by_design` (em dash + NBSP, refusal with no guessed inspect/stop). No behavior change.

**A2 — repair fallback chmod-through-link (engine.py).** RED: injected generic OSError + post-lstat symlink swap proved the fallback chmod-ed the link TARGET (victim 0o400 -> 0o644). Fix: only `NotImplementedError` (genuinely unsupported no-follow chmod) enters the fallback, which re-lstats and skips anything that became a symlink; generic OSError is swallowed. No-follow now holds unconditionally (`test_permission_repair_never_chmods_through_a_swapped_symlink`).

**A3 — unbounded repair enqueue (engine.py).** RED: with a budget of 2, one scandir loop consumed all 50 children. Fix: the budget is enforced inside the enumeration (`seen + len(stack) >= _MAX_PURGE_REPAIR_ENTRIES` stops appending); an under-repaired tree routes to the unrecoverable marker path on retry (`test_permission_repair_enqueue_is_bounded_by_the_entry_budget`).

**A4 — marker could carry credential bytes (engine.py).** RED: a RunStore root containing the credential put the bytes into `contaminated_staging_path`. Fix: every marker field passes through `_credential_free_marker_value` (hash-replace on sensitive-byte match, same posture as `_safe_sensitive_path_finding`), with `sensitive_values` threaded through the purge call sites. The marker is unconditionally credential-free (`test_cleanup_marker_is_credential_free_even_when_store_path_carries_secret`).

**A5 — exception identity and masking (engine.py).** RED × 2: retries overwrote `purge_error` so the FINAL retry's exception propagated ("denial-3" instead of "denial-1"); and a marker-write failure (marker dir occupied by a file) replaced the primary purge error. Fix: the first deletion exception is captured once and always re-raised; marker IO is wrapped in its own try/except that records via `sanitize_reason` and never wraps the re-raise (`test_purge_reraises_the_original_deletion_error_not_the_final_retry`, `test_marker_write_failure_never_masks_the_primary_purge_error`).

**B — chunk-straddle test now kills the overlap off-by-one mutant.** The straddle control is parametrized over splits including the one only a full `credential_length - 1` overlap catches (secret crosses the boundary with exactly one byte in the next chunk, i.e. L-1 bytes in the previous chunk). Verified by mutation: with `overlap = L-2` applied, the new `one-byte-after` param goes RED while the old mid-split passes; mutant reverted, scanner unchanged.

Post-repair: `pytest tests/core/arena/ -q` -> **420 passed** at head `[redacted-sha]`.

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
