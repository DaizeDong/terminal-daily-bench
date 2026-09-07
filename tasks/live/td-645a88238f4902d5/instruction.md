# Avoid shared language_detector and locale cache in search_dates

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

[redacted-ref].

`search_dates` runs through a process-wide `DateSearchWithDetection` singleton. Two leftover store-then-load races from [redacted-ref] can make concurrent calls return `None` or a date built from the wrong locale:

1. `detect_language` stashed a `FullTextLanguageDetector` on `self` and then loaded it. That detector is single-use: `_best_language` narrows `self.languages` in place. A concurrent call can observe another call's already-narrowed detector.
2. `_ExactLanguageSearch` kept `self.language` as a 1-slot cache on the same singleton. A store from another thread between `get_current_language` and `translate_search` uses the wrong locale.

Neither value needs to be instance state. Build the detector as a local, and have `get_current_language` return the locale (`LocaleDataLoader.get_locale` already caches). Public API is unchanged.

Thanks @serhii73 for the report and the diagnosis.

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
