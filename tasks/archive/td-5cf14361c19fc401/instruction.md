# fix(locale): use Japanese date formats for the ja locale

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

The `ja` locale's `date_formats` were left with the English/US defaults, so localized format tokens render Japanese dates in English order with US separators:

```python
dt = [redacted-repo].datetime(2026, 6, 30, 13, 5)
dt.format("L",    locale="ja")  # "06/30/2026"
dt.format("LL",   locale="ja")  # "6月 30, 2026"  (a Japanese month token in English "month day, year" order)
dt.format("LLLL", locale="ja")  # "火曜日, 6月 30, 2026 1:05 午後"
```

Every other CJK locale already localizes these. `zh` uses `YYYY年MMMD日` / `Ah点mm分` and `ko` uses `YYYY년 MMMM D일` / `A h시 m분`, so `ja` is the one left on the defaults. The values here match the standard Japanese formats used by Moment.js and Day.js (`locale/ja`):

```
LT    HH:mm
LTS   HH:mm:ss
L     YYYY/MM/DD
LL    YYYY年M月D日
LLL   YYYY年M月D日 HH:mm
LLLL  YYYY年M月D日 dddd HH:mm
```

After the change:

```python
dt.format("L",    locale="ja")  # "2026/06/30"
dt.format("LL",   locale="ja")  # "2026年6月30日"
dt.format("LLLL", locale="ja")  # "2026年6月30日 火曜日 13:05"
```

Only the format strings change; the day and month names still come from the existing `ja` CLDR data. I added a `ja` block to `test_date_formats` next to the existing `fr` assertions. It fails on the old formats and passes on the new ones, and `zh`/`ko` output is unchanged.

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
