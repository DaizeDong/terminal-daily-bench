# Add genome-alignment and RNA004 support ([redacted-repo] v2.2)

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## Summary

This PR adds support for **genome-aligned** f5c eventalign output and for **RNA004** dRNA chemistry, and bumps [redacted-repo] to **v2.2**. Previously [redacted-repo] was only compatible with transcriptome alignments and had the RNA002 kmer model. 

## What's changed

### Genome-alignment support
- New `--kmer_source {reference_kmer,model_kmer}` flag on `[redacted-repo] dataprep` (default `reference_kmer`, unchanged for transcriptome alignments). Use  `--kmer_source model_kmer` for genome alignments.
- `combine()` now selects the k-mer column based on `kmer_source`. For `model_kmer` it accepts both direct **and reverse-complement** matches so reverse-oriented genome-aligned reads aren't filtered out.
- `preprocess_tx` groups by `(position, kmer)` when using `model_kmer`, so forward/reverse reads at the same position are kept as separate entries with their respective k-mers.
- Guard rail: `dataprep` raises a clear error if the eventalign reference name starts with `chr` (i.e. looks like a genome alignment) while using `--kmer_source reference_kmer`, which would otherwise silently filter all reverse reads.

### RNA004 support
- Added `RNA004_5mer_model.csv` and renamed `model_kmer.csv` →`RNA002_5mer_model.csv` (to clarify naming).
- `[redacted-repo]-diffmod` now uses the **RNA004 model as the default prior**. RNA002 users can set `prior:` to the bundled `RNA002_5mer_model.csv`.
- Updated `MANIFEST.in` to ship both model files.

### Read-count handling fixes
- `dataprep`: `--readcount_max` now caps reads **per site** rather than hard-stopping on total reads per gene/transcript, and accepts `None` for no limit.
- `preprocess_gene` / `preprocess_tx`: on a k-mer mismatch between `model_kmer` and `reference_kmer`, `continue` to the next position instead of `break` (previously a single mismatch discarded all remaining sites on a transcript).
- `diffmod` `io.load_data`: sites exceeding the diffmod `readcount_max` are now truncated to the first N reads instead of dropping the site silently.

### Misc
- Version bumped to v2.2 (`setup.py`, `[redacted-repo]/__init__.py`).
- Docs: documented genome-alignment and RNA004 support, added a quickstart command table, and updated the demo (RNA002) config instructions; minor README release-history fixes.

## Type of change

- [x] New feature (mostly non-breaking — see note below)

This is PR largely non-breaking. The only differences from v2.1 [redacted-repo] (on transcriptome-aligned data) comes from max read count being applied per-site rather than per aligned reference (gene/transcript for transcriptome aligned, chromosome for genome-aligned), so in genes with read counts close to or above the max (i.e. 1000 reads for [redacted-repo] v2.1) there will be some very minor differences at some sites (e.g. sites with coverage at ~999 for [redacted-repo] v2.1 due to reads being capped, whereas for [redacted-repo] v2.2 a site may have 1000 datapoints from >1000 reads). 

> ⚠️ Note: the new `[redacted-repo]-diffmod` default prior is the RNA004 model. Existing RNA002 workflows must now point `prior:` at the bundled `RNA002_5mer_model.csv` to reproduce previous results (see docs/quickstart).

## Testing

Tested locally on RNA002 and RNA004 data ensuring backwards compatibility & identical outputs - see testing details below

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
