# Website build

After updating the published data or page sources, run:

```sh
python web/build_site.py
python web/verify_site.py
```

Preview the site at <http://127.0.0.1:8765/>:

```sh
python -m http.server 8765 --bind 127.0.0.1 --directory docs
```

The **Build and deploy website** GitHub Actions workflow builds and checks website changes. Successful builds on `main` deploy to <https://daizedong.github.io/terminal-daily-bench/>. Pull requests run the same checks without deployment. The workflow can also be run manually from the Actions tab.

The build bundles the shared styles, generates task and release pages, refreshes documentation search, creates the public routes, and updates asset versions. Edit shared styles in `docs/assets/site.css`; edit the feature styles in their separate `tdb-*.css` sources above the generated bundle.

Public sections use `/leaderboard/`, `/tasks/`, `/releases/`, `/docs/`, `/submit/`, and `/quality/`. Existing `/registry/`, `/benchmarks/`, and `/guide/` bookmarks continue to work. Generated copies are rebuilt from those source sections.

Publish each evaluation date with its own task matrix and scoring method. `gen_run_details.py` validates attempt records against those results before producing run details. Missing cost or action records remain unavailable.

To import the clean pipeline's persisted per-attempt `eval.json`, keep that input and the provenance audit outside the public checkout and run:

```sh
python web/gen_run_details.py \
  --published docs/data/days/2020-01-02.json \
  --eval-results ../private-run-data/eval.json \
  --out docs/data/run-details/2020-01-02.json \
  --day-out docs/data/days/2020-01-02.json \
  --audit-out ../private-run-data/run-details-audit.json \
  --publish-dir docs/data/run-details
```

The synthetic date illustrates the arguments; select the matching published day for each import. `--board` remains available for an explicit board input. Both inputs must exactly reproduce every published aggregate and existing matrix cell using strict majority across complete trial sequences. A mismatch stops the import; the converter does not change the clean pipeline's scoring policy. `--exclude-spec` removes only an explicitly named model specification and records that exclusion in the private audit. The evaluation adapter accepts finalized scalar call counts from `harness` and omits raw certificates, paths, advisory scores, and trajectories from public output.

Efficiency uses recorded command calls and tool calls. Terminal call counts include each submitted command batch once; total tool counts include non-terminal actions. Neither metric is inferred from elapsed time, token usage, or the displayed replay summary. Scores and rankings use the share of tasks solved by strict majority: at least two successes out of three attempts. Horizontal score bars show an inline ± value for the sample standard deviation across complete run accuracies on the same tasks (runs minus one in the variance denominator). Their thin lines extend one standard deviation around the majority score, clipped to the 0–100% display scale. Capability heatmaps and efficiency scatter plots show scores without error bars. Dates without complete repeat records retain their published score and omit the variation estimate.

When task packages are not part of the website checkout, `docs/data/catalogue-additions.json`, `task-details.json`, and `task-capabilities.json` retain the reviewed public task metadata. Supplemental capability labels remain preliminary. Package records take precedence during data generation.
