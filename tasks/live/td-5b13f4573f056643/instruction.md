# feat: rank keyword search with BM25

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

The default search path was the worst one, measurably. `search unemployment` on Eurostat put **`UNE_RT_M` — the monthly unemployment rate — at position 65 of 146**. `search "gross domestic product"` put `NAMA_10_GDP` at 16 of 29.

The cause is the scorer, not the corpus: it summed raw token occurrences with no length denominator and weighed every query word the same. A long title beat a relevant one, and "di" counted like "disoccupazione". Handing it more text changed nothing — the extended-text arm scored 0.075 against the baseline 0.073, inside the noise.

Ranking is now BM25 (`src/[redacted-repo]/ranking.py`): `idf` down-weights common terms, `b` normalises for document length. The field boosts (id ×3, first 60 characters ×2) survive, rescaled to the BM25 unit.

## Measured on two blind gold sets

A second gold set was written for **Eurostat** with the same protocol as the ISTAT one: 25 information needs and their queries written with `gold: null` **saved to disk before looking at the catalogue**, gold filled in a second pass, family gold, one need discarded as undecidable → 24 needs, 48 queries. Eurostat embeddings were built for the run — the first time the semantic arm has been measured on a provider **without** harvested prose.

| MRR | Eurostat | Eurostat `en` | ISTAT | ISTAT `it` |
|---|---|---|---|---|
| before | 0.086 | 0.172 | 0.073 | 0.133 |
| **after** | **0.166** | **0.330** | **0.169** | **0.326** |
| semantic | 0.241 | 0.308 | 0.327 | 0.343 |

**In the provider's own language the keyword path now matches the semantic one** — Eurostat 0.330 vs 0.308, ISTAT 0.326 vs 0.343 — with no model, no server and no index build. That is the case most users are in, on most providers.

**Cross-language is untouched, and is not fixable lexically.** Italian queries on Eurostat score **0.000** across 24 queries before this change and 0.001 after. Only the semantic arm scores at all (0.174). No term weighting invents words a document does not contain.

## What it looks like on real queries

| query | before | after |
|---|---|---|
| `tasso di disoccupazione` (ISTAT) | `...TAXDISOCCUMENS1_UNT2020` — the series **closed in 2020** | `151_874` — the current monthly series |
| `popolazione residente` (ISTAT) | `164_346` — intercensal *reconstruction* 1971 | `22_315` — "Popolazione residente - bilancio" |
| `unemployment` (Eurostat) | `LFSQ_UPGAL` — top three all *long-term* unemployment | `LFSA_URGAN` — unemployment **rates** |
| `population on 1 January` (Eurostat) | `PROJ_19RP3` — top three all *projections* | `TPS00001` — the observation |

Of ten queries compared, four change clearly for the better, four change little or debatably, two are identical. The gain concentrates where the old scorer failed *systematically*; where the title was already short and specific, nothing moved. Full table in `docs/search.md`.

## What deliberately did not change

**The candidate set is chosen exactly as before** — AND over every token, OR only when that is empty. BM25 alone would score any document sharing one token, so `"tasso di disoccupazione"` would report **2405** matches on ISTAT instead of 28: correct at the top, useless as a total. Only the ordering changed, so result counts, the pagination title, `--page` and `--all` behave as they did.

## Two details that would otherwise have made this silently worse

**Tokenisation splits on the underscore.** `\w` swallows it and would turn `UNE_RT_M` into a single term, so no query could ever match an id exactly and the id boost would be dead. A pre-existing test caught this — it was the only failure in the suite.

**Prefix expansion.** A query token with no exact match expands to the terms it *prefixes*, at half weight, so an exact hit always outranks a prefix hit. Without it, whole-token BM25 kills prefix search outright: `search comun -p istat` goes from 605 results to **0**, and that behaviour ships in the `search --help` example. Prefix, not arbitrary substring — `comun` reaches "comuni" and "comunali", not "incomunicabile".

Queries with no word characters (`search "["`) fall back to literal substring matching.

## Cost

The index is built per call **over the whole catalogue**, never over the candidate set: idf is a property of the corpus, and a candidate set selected by the query contains its terms in every row, which would flatten the signal BM25 exists to provide.

Measured: 0.14 s build on the largest catalogue (Eurostat, 8150 dataflows), 28 ms on OECD, queries 1–18 ms — against a command whose Python import alone is ~1.9 s. No disk index, so nothing to invalidate when the dataflow or category cache refreshes.

## Multi-provider

No provider-specific branch. Length normalisation is relative to each corpus, so the 5× spread in title length across providers (unicef averages 2.6 words per title, abs 13.7) needs no tuning. Verified live on eurostat, istat, oecd, ecb, ilo and abs — including providers with no category cache, where the corpus is title + id only.

## Also

`score` is now a float on the BM25 scale, formatted to 2 decimals in table, JSON and CSV. `_score_results` is off the search path but kept: `eval/retrieval.py` uses it as the baseline arm, and deleting it would make the measurement that justified this change unreproducible.

`docs/search.md` records the measurement, its **three declared limitations** (the Eurostat gold pairs topics across registers so 24 needs are not 24 independent observations; its topics are easier than ISTAT's; two families are too narrow and were **not** retrofitted after seeing results), and the before/after table.

## Verification

ruff clean · mypy strict clean on 16 source files · **394 tests green**, 9 new covering the tokenizer, idf, length normalisation, prefix expansion, the empty-corpus NaN guard, and the punctuation fallback.

🤖 Generated with [Claude Code]([redacted-url])

[redacted-url]

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
