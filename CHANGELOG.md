# Changelog

## 0.1.0 (unreleased) -- first public bundle
- Professional Python package `terminal_daily_bench` with the `tdb` CLI
  (`run` / `oracle` / `quality`).
- Gate-free execution scoring (`harbor_score`) extracted from the private stack;
  `false_accept = 0` preserved without the construction pipeline (moat contract).
- Multi-angle Selection-Quality instrument (`quality`): discrimination / difficulty
  coverage / monotonicity / angle coverage / diversity / IRT information / KR-20
  reliability + bootstrap CIs + power + readiness verdict.
- Pluggable harness adapters (`single_shot`, `terminus` stub).
- Task-release policy: `live` (gold + protected withheld, server-side scored) vs
  `archive` (>= 2 weeks, full); `publish_tasks.py` sanitizes host paths on publish.
- Release gate `scripts/release_check.sh` (secret scan + moat + artifacts + policy)
  and `tests/test_release.py`. Generic OpenAI-compatible model endpoint (no private
  gateway coupling).
