"""Dependency-free structural fixtures for the static v3 capability frontend."""
from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HOME = (ROOT / "docs" / "index.html").read_text(encoding="utf-8")
LEADERBOARD = (ROOT / "docs" / "leaderboard" / "index.html").read_text(
    encoding="utf-8"
)
REGISTRY = (ROOT / "docs" / "registry" / "index.html").read_text(
    encoding="utf-8"
)
SHELL = (ROOT / "docs" / "assets" / "site.js").read_text(encoding="utf-8")
PAGE_GENERATOR = (ROOT / "web" / "gen_pages.py").read_text(encoding="utf-8")
DATA_GENERATOR = (ROOT / "web" / "gen_site_data.py").read_text(encoding="utf-8")


def test_home_and_full_board_require_code_approved_relative_v3_authority():
    for source in (HOME, LEADERBOARD):
        assert 'schema_version === "td-relative-capability-v3"' in source
        assert "scoring.official_ranking === true" in source
        assert (
            'scoring.publication_registry_mode === "code-controlled-allowlist"'
            in source
        )
        assert "scoring.publication_bundle_approved === true" in source
        assert "scoring.relative_report_digest_matches === true" in source
        assert "scoring.anti_cheat_deployment_active === true" in source
        assert "input.frozen_task_roster_n === 50" in source
        assert "input.task_roster_digest_trusted === true" in source
        assert "input.cell_manifest_digest_trusted === true" in source
        assert "publishable === true" in source

    assert "var rows = (board && board.leaderboard) || []" not in HOME
    assert "discoverHarnesses" not in HOME
    assert "KNOWN_HARNESSES" not in LEADERBOARD
    assert "build(b)" not in LEADERBOARD


def test_site_data_generator_rejects_legacy_or_partial_matrix_authority():
    assert 'RELATIVE_SCHEMA = "td-relative-capability-v3"' in DATA_GENERATOR
    assert "FORMAL_TASK_TARGET = 50" in DATA_GENERATOR
    assert 'PUBLICATION_BUNDLE_SCHEMA = "td-relative-publication-bundle-v1"' in DATA_GENERATOR
    assert 'PUBLICATION_REGISTRY_MODE = "code-controlled-allowlist"' in DATA_GENERATOR
    assert "APPROVED_PUBLICATION_BUNDLE_SHA256S" in DATA_GENERATOR
    assert "ANTI_CHEAT_DEPLOYMENT_ACTIVE = False" in DATA_GENERATOR
    assert "matrix_task_id_roster_sha256" in DATA_GENERATOR
    assert "relative_report_digest_matches" in DATA_GENERATOR
    assert "def scoring_status(" in DATA_GENERATOR
    assert "def _published_matrix(" in DATA_GENERATOR
    assert 'state = "awaiting-certified-50-task-results"' in DATA_GENERATOR
    assert '"legacy_snapshot_present": legacy_present' in DATA_GENERATOR


def test_relative_axes_are_authority_bounded_and_task_family_is_unavailable():
    assert (
        "var ALLOWED_DIMENSIONS = { overall: true, language: true, capability: true };"
        in LEADERBOARD
    )
    assert "!ALLOWED_DIMENSIONS[axis.dimension]" in LEADERBOARD
    assert "Task-family: unavailable." in LEADERBOARD
    assert "canonical C1&ndash;C14 capability labels" in LEADERBOARD
    assert "does not infer one from tracks, merged labels" in LEADERBOARD
    assert '["task-family", null, "unavailable; not inferred and not zero"]' in LEADERBOARD


def test_non_success_statuses_are_null_not_zero_and_never_ranked():
    for status in ("FAILED", "BLOCKED", "NOT_RUN"):
        assert f'"{status}"' in LEADERBOARD
    assert "use <code>outcome:null</code>" in LEADERBOARD
    assert "excluded from ratings" in LEADERBOARD
    assert "authenticated_counts" in LEADERBOARD
    assert "untrusted_declared_counts" in LEADERBOARD
    assert "counted in coverage, not outcomes" in LEADERBOARD
    assert "worth zero" not in PAGE_GENERATOR.lower()
    assert "attempt worth zero" not in PAGE_GENERATOR.lower()


def test_registry_never_reconstructs_tasks_or_scores_from_legacy_matrix():
    assert 'T.getJSON("leaderboard_data.json")' not in REGISTRY
    assert "board.matrix" not in REGISTRY
    assert "Official Solves" in REGISTRY
    assert "means awaiting formal coverage, not zero solves" in REGISTRY
    assert "official score coverage" in REGISTRY


def test_output_values_are_escaped_before_entering_v3_tables():
    assert "esc(row.axis)" in LEADERBOARD
    assert "esc(row.kind)" in LEADERBOARD
    assert "esc(participant(row))" in LEADERBOARD
    assert "shown(rating.rank_within_component)" in LEADERBOARD
    assert "ratio(rating.attempt_coverage_numerator" in LEADERBOARD


def test_stat_values_are_not_document_headings():
    assert "<p data-tdb-stat-value" in HOME
    assert "<p data-tdb-stat-value" in PAGE_GENERATOR
    assert '<h2 class="mt-2 line-clamp-1 font-mono text-xl' not in HOME
    assert (
        '<h2 class="line-clamp-1 font-mono text-xl font-medium tabular-nums"'
        not in PAGE_GENERATOR
    )

    generated = sorted((ROOT / "docs" / "benchmarks").glob("*/index.html"))
    generated += sorted((ROOT / "docs" / "registry").glob("*/index.html"))
    assert generated
    for page in generated:
        source = page.read_text(encoding="utf-8")
        assert "<p data-tdb-stat-value" in source, page
        assert (
            '<h2 class="line-clamp-1 font-mono text-xl font-medium tabular-nums"'
            not in source
        ), page


def test_mobile_menu_is_opaque_non_overlapping_and_accessible():
    assert "bg-fd-background px-4 py-3 lg:hidden" in SHELL
    assert 'menu.setAttribute("aria-hidden", open ? "false" : "true")' in SHELL
    assert 'pageMain.style.paddingTop = open ? head.offsetHeight + "px" : ""' in SHELL
    assert 'ev.key === "Escape"' in SHELL


def test_shell_mounts_a_real_footer_landmark():
    assert 'document.createElement("footer")' in SHELL
    assert 'footer.id = "tdb-footer"' in SHELL
    assert 'footer.setAttribute("aria-label", "Site footer")' in SHELL
    assert "document.body.appendChild(footer)" in SHELL


def test_homepage_integrity_facts_match_current_operator_evidence():
    assert "data-tdb-integrity-details" in HOME
    assert "integrity limits and current blockers" in HOME
    assert "Protected tests decide published scores" in HOME
    assert "paired staged-SIF egress canary passed" in HOME
    assert "no production protected replay has run" in HOME
    assert "active=false" in HOME
    assert "code-controlled allowlist" in HOME
    assert "self-signed report/matrix pins cannot approve themselves" in HOME
    assert "one collaborator" in HOME
    assert "deployment egress canary is still pending" not in HOME
    assert "unpublished patched Harbor fork" in HOME
    assert "stock Harbor 0.13.1 is insufficient" in HOME


def test_homepage_previews_stay_short_and_link_to_full_views():
    assert "var BOARD_PREVIEW_LIMIT = 5;" in HOME
    assert "rows.slice(0, BOARD_PREVIEW_LIMIT)" in HOME
    assert "var TASK_PREVIEW_LIMIT = 3;" in HOME
    assert "scoped.slice(0, TASK_PREVIEW_LIMIT)" in HOME
    assert 'href="./leaderboard/">full leaderboard' in HOME
    assert 'href="./registry/">all tasks' in HOME
