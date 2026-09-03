# [Feature] Major Updates to SPT Web

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## Description

This PR adds a large batch of web viewer improvements.

### State persistence & URL sharing
All interactive state (visible runs, filters, grouping, sort, axes, theme, etc.) is serialised to `localStorage` on every mutation and restored on page load. Visible run IDs and the active tab are also reflected in the URL fragment (`#runs=...&tab=...`) via `history.replaceState`, so shared URLs land on the sender's exact view.

### Chart value annotations
Each uPlot chart panel now renders a compact annotation table below it showing the last and best logged value per visible series. A `lowerIsBetter` heuristic handles loss/error/perplexity metrics automatically. The best-value row is bolded. Clicking a row toggles that series' visibility.

### Runs table view
A fourth Table tab renders all visible runs as a sortable, filterable, horizontally-scrollable table. Columns are the union of all `hparams` and `summary` keys. Cells that differ across runs are highlighted amber; uniform cells are dimmed. Headers and the run-ID column are sticky. Column sort cycles asc → desc → none. A debounced column search box with a count badge is persisted to `localStorage`. Row clicks open the existing detail modal.

### Run display names & inline editing
Sidebar rows now show `display_name` as the primary label with the raw `run_id` dimmed below it. Double-clicking the name opens an inline editor that commits via `PATCH /api/run-meta` with optimistic rollback on failure. The table tab was also fixed to use `display_name`.

### Notes editing
The run detail modal gained a Notes textarea that auto-resizes to content. Edits commit on blur or `Ctrl+Enter` via the same `PATCH /api/run-meta` endpoint.

### Live log tail
The `.out` and `.err` log tabs auto-refresh every 10 s for running/stale runs, showing a pulsing live badge. A pause button and manual refresh button are provided. Scroll position is preserved across refreshes.

### Run elapsed time / duration
Backend: `Logger.finalize()` now records `ended_at` and exposes it through the sidecar and scan serialiser. Frontend: each run row shows a formatted elapsed/total duration, updated on a 60 s tick. The detail modal shows `started`, `ended`, and `duration` fields.

### Heartbeat staleness indicator
Runs whose heartbeat file mtime is more than 5 minutes old are treated as stale. Stale rows show an amber ⚠ dot with a tooltip. The status stat chip, filter/group-by/sort consumers, and the figures-tab overview (activity timeline, stat card, status bars) all reflect the stale state via a centralised `effectiveStatus()` helper.

### Scatter plot
A scatter plot is rendered at the bottom of the figures tab when two or more runs are visible. X and Y axes are user-selectable from any numeric `hparams.*` or `summary.*` key across visible runs. Each run is a single coloured dot; axis selection and visibility are persisted to `localStorage`.

### Metric CSV export
A download CSV button exports all visible runs × filtered metrics × steps from in-memory state (no server round-trip) as `spt_metrics.csv` with columns `run_id, run_name, metric, step, epoch, value`.

### Zoom reset on charts
Each chart panel shows a hidden ⤢ reset button that appears after a drag-zoom. Clicking it resets all charts simultaneously (they share a uPlot sync key). The drag-selection rectangle is now visually styled.

### Sidebar resize + virtual scroll
A drag handle lets the user resize the sidebar between 160–600 px (persisted to `localStorage`). The run list scrolls independently of the fixed sidebar controls. Lists exceeding 300 ungrouped runs switch to a virtual scroll renderer using spacer divs and a scroll listener, keeping DOM size bounded.

### Keyboard shortcuts
Six shortcuts: `/` (focus metric search), `r` (focus run search), `t` (cycle tabs), `Shift+A` (select all), `Shift+C` (clear selection), `?` (toggle help popover). All are suppressed inside text inputs. A styled help popover lists all shortcuts with `<kbd>` key chips.

### Tag editing from UI
Tags in the run detail modal are now interactive pills with × remove buttons. An expanding inline input with datalist autocomplete (populated from other runs' tags) handles additions on `Enter` or `,`. All mutations go through `PATCH /api/run-meta` with optimistic rollback. No backend changes were needed.

### Combine metrics into one chart
Each chart panel title bar has a `+` toggle button. Selecting two or more metrics reveals a **Combine (N)** button in the figures toolbar; clicking it creates a persistent combined chart panel pinned above the metric grid. Combined panels show all visible runs' series for all listed metrics in one uPlot instance, with a full annotation table. Combined chart state persists to `localStorage`.

### Per-chart PNG export
Each chart panel has a `⬇` download button (revealed on hover). Clicking it composites the uPlot canvas onto an offscreen canvas with a padded border and bold metric-name title, filled with the current theme's colours. The result is downloaded as a full-resolution (HiDPI-aware) PNG named after the metric.

### Per-metric direction override
Each chart panel title bar has a `↓ min` / `↑ max` toggle button. On first render it reflects the `lowerIsBetter` heuristic; clicking flips the direction and stores an explicit override in `state.metricDir`. The button turns accent colour when an override is active. Overrides persist to `localStorage` and immediately re-highlight the best-value annotation row.

### Hide same-value columns in table
A **hide same** toggle in the table controls bar filters the rendered columns to only those whose values differ across visible runs. The column-count badge updates to show `"N diff / M cols"` when active. State persists to `localStorage` as `tableHideSame`.

### Light mode visual refinement
The light-mode palette was replaced with warm off-white neutrals (`--bg: #f0ede9`, `--surface: #f9f8f6`, `--surface-2: #f3f1ee`) and the accent shifted to indigo (`[redacted-ref]f46e5`) for stronger contrast. Run count text and stale-run chip backgrounds were hardened for both themes.

### File-deletion safety (TOCTOU fixes + deletion toast)
Three check-then-open races in `scan.py` (`metrics_json`, `metrics_stream`, `log_content`) were replaced with direct `try/except OSError` opens, eliminating windows where file deletion between the check and the open would crash a server thread. On the frontend, if a run that was selected or open in the detail modal disappears from disk, a dismissible amber toast notification is shown automatically.

### Rename / edit robustness
Four edge-case bugs fixed: (1) `renderRunList` now calls `.blur()` on any active inline rename input before tearing out the DOM, so in-flight edits are never silently lost; (2) `do_PATCH` catches `OSError` from `write_sidecar` and returns a 500 JSON response instead of dropping the TCP connection; (3) `patch_run_meta` validates field types (`display_name`/`notes` → `str | None`, `tags` → `list`, `archived` → `bool`); (4) rename and notes failure handlers now call `showToast(...)` with the server error message and look up a fresh run reference from `state.runs` instead of using a potentially stale closure.

## Checklist

<!-- - Go over all the following points, and put an `x` in all the boxes that apply. -->

- [x] I have read the [**Contributing**]([redacted-url]) document.
- [x] The documentation is up-to-date with the changes I made (check build artifacts).
- [x] All tests passed, and additional code has been **covered with new tests**.
- [x] I have added the PR to the [**RELEASES.rst**](../RELEASES.rst) file.

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
