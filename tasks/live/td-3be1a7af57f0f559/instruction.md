# fix(parser): diagnose MinerU/pdftext PageChars incompatibility

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

Refs [redacted-ref]

## What this is

A diagnostics improvement, **not** a functional fix for [redacted-ref]. The crash happens
inside MinerU's own process and cannot be prevented from [redacted-repo]. This PR
makes the failure self-diagnosing instead of opaque.

## Root cause

pdftext 0.7.0 changed its character-extraction API to return a `PageChars`
object instead of an iterable list. MinerU <= 3.4.0 iterates that value directly
in `_deduplicate_near_identical_chars` (`mineru/utils/pdf_text_tool.py`), giving
`TypeError: 'PageChars' object is not iterable`.

Fixed upstream in MinerU 3.4.1, which added compatibility shims and constrained
the dependency to `pdftext>=0.6.3,<0.8.0`:

- opendatalab/MinerU[redacted-ref]
- opendatalab/MinerU[redacted-ref]

[redacted-ref] was filed one day before that release.

`.xlsx` reproduces it every time because Office formats have no native MinerU
path: `MineruParser.parse_office_doc` converts them to PDF via LibreOffice, and
that output is born-digital text, so MinerU's pipeline always takes the pdftext
route and never OCR. Scanned PDFs avoid the bug; converted spreadsheets cannot.

Since `mineru[core]` is unpinned in `pyproject.toml`, fresh installs now resolve
to a fixed MinerU. Only environments with an older pin still break — and today
they get an error naming neither MinerU's version nor pdftext.

## Changes

- `raganything/parser.py`: add `_MINERU_KNOWN_FAILURES` (signature to
  remediation) and `_diagnose_mineru_failure()`. `MineruExecutionError` takes an
  optional `hint`, inferring it when omitted and appending it to the message.
  `_run_mineru_command` logs the hint before raising.
- `raganything/processor.py`: append the hint to the persisted
  `doc_status.error_msg`, so it appears in the LightRAG UI, not just the logs.
- `tests/test_mineru_error_hints.py`: 11 tests driven by the verbatim stderr
  from [redacted-ref], including one that runs `_run_mineru_command` against a mocked
  `Popen` to prove the traceback line survives the `"error"` substring filter.

The hint points at `pip install -U "mineru[core]>=3.4.1"`, the `pdftext==0.6.3`
pin as an alternative, and `parser="docling"` as an immediate workaround —
`DoclingParser.parse_office_doc` reads `.xlsx` natively without LibreOffice, PDF
conversion, or MinerU.

## Not included

I did not raise the `mineru[core]` floor to `>=3.4.1`. That would drop the
MinerU 2.x versions this code still accommodates (the field-name normalization
in `_read_output_files`), which is a maintainer policy call. Happy to add it if
you'd prefer.

## Testing

`pytest tests/` — 270 passed, 1 skipped. `ruff format` and
`ruff check --ignore=E402` clean, matching `.pre-commit-config.yaml`.

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
