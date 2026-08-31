#!/usr/bin/env python3
"""Build docs/data/capability.json -- the capability axis, re-derived and gated.

WHY THIS EXISTS. The benchmark's second headline (after "which model solved
what") is WHICH CAPABILITY a task exercises: a 14-axis verb taxonomy, C1..C14,
that the mining pipeline tags every candidate with. The site shipped none of it,
and an earlier audit concluded the codes were undefined -- they are not. They
are declared once, in the research pipeline's ``CAPABILITY_TAXONOMY``, and the
tagger that assigns them is deterministic static rules over the changed-file
paths and the ADDED lines of the two patches. Given a task package you can
recompute its labels and get the shipped answer back.

That reproducibility is the whole product here, so this generator does not read
``capability_labels`` and publish it. It RE-DERIVES every label from the
package's own patches and then asserts the result equals what the package
stores, in BOTH places it is stored (``record.json:capability_labels`` and
``task.toml:keywords``). Disagreement is a hard error: a catalogue whose labels
have drifted from the rules that produced them is not a measurement any more.

    gen_capability_data.py [--release DIR] [--out DIR/docs/data/capability.json]

WHAT IT CANNOT DO, stated in the output rather than papered over:

  * 24 of the 61 catalogued tasks ship LIVE -- they withhold the oracle patch
    and the test diff, which are exactly the tagger's inputs. Their task.toml
    still declares keywords, so the labels exist; they simply cannot be checked
    here. They are reported under ``declared_unverified`` and are never counted
    into an axis's support or its gate arithmetic.

  * The publish gate has three criteria and only two of them are computable from
    task packages. ``min_admitted_subtests`` counts F2P subtests surviving a
    unit-test-validity audit that classifies each one high/medium/low
    confidence; no such audit has been run over THIS catalogue. The one that
    exists measured a different corpus at a different release commit, so its
    per-axis numbers describe that corpus and not this one -- they are
    deliberately not copied here. The criterion is emitted as
    ``measured: false, met: null``. No axis is ever printed as gate-passing on
    two out of three.

  * ``coverage_share`` is emitted per axis because two of them label nearly the
    whole catalogue. A label present on almost every task cannot separate tasks,
    and clearing a support gate does not change that -- it is a property of the
    label, and the site is expected to say so rather than print a green tick.

The vendored rule tables below are a verbatim copy of the research pipeline's
registry, recorded with source path, commit and file digest, because that repo
is a separate checkout that does not exist on a build machine. The re-derivation
check is what keeps the copy honest: if the upstream rules change and this copy
does not, packages stop matching and the build fails loudly.
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover -- py<3.11
    import tomli as tomllib

from gen_site_data import retain_generated_timestamp  # noqa: E402

SCHEMA = "tdb-capability-v1"

# ---------------------------------------------------------------------------
# VENDORED from the research pipeline. Do not edit these tables to change what
# the site shows -- edit them only to track an upstream change, and re-run this
# generator so the re-derivation check re-proves the copy against every package.
# ---------------------------------------------------------------------------
RULES_SOURCE = {
    "repo": "terminal-daily (research pipeline, separate checkout)",
    "path": "experiments/src/td_pipeline/selection.py",
    "symbol": "CAPABILITY_TAXONOMY / label_capabilities",
    "commit": "3538604962867b9671fc585ee2449169abc7de3d",
    "file_sha256": (
        "97835d37bb95ffbfc18234dc27106a97cd5a73c3d7cbb391654d9c774067b359"
    ),
    "vendored_on": "2026-08-27",
    "why_vendored": (
        "the research repo is not present at publish time; the re-derivation "
        "check against every package is what keeps this copy from drifting"
    ),
}

# (code, name, description, path_rules, token_rules, frontier, risky_env)
CAPABILITY_TAXONOMY = (
    ("C1", "filesystem", "filesystem / data wrangling", (), (), False, False),
    ("C2", "build", "build & compile",
     ("makefile", "cmakelists", "configure.ac", "setup.py",
      "pyproject.toml", "package.json", "cargo.toml"), (), False, False),
    ("C3", "debug", "debugging / fault localization", (), (), False, False),
    ("C4", "impl", "code implementation / refactor", (), (), False, False),
    ("C5", "test", "test authoring & verification",
     ("/tests/", "/test/", "test_", "_test."),
     ("def test_", "assert "), False, False),
    ("C6", "data", "data processing / ETL / scientific",
     ("dataset", ".csv", ".sql", "pandas"),
     ("numpy", "pandas"), False, False),
    ("C7", "net", "networking & protocols",
     (".proto", "/net/", "/http/", "socket"),
     ("import socket", "requests.get", "http.client"), True, True),
    ("C8", "sec", "crypto & security",
     ("crypto", "security", "/auth"),
     ("hashlib", "hmac", "base64", "openssl"), True, False),
    ("C9", "ops", "system config & ops",
     ("dockerfile", ".github/workflows", "/ci/"), (), False, True),
    ("C10", "vcs", "version control operations",
     (".gitignore", ".gitmodules"),
     ("rebase", "cherry-pick"), False, False),
    ("C11", "perf", "performance optimization",
     ("/bench", "perf"), (), False, False),
    ("C12", "reverse", "reverse engineering / low-level",
     (".asm", ".s", "disasm"), (), True, False),
    ("C13", "ml", "ML / data-science engineering",
     (".ipynb", "/models/", "train"), ("torch",), False, True),
    ("C14", "orch", "environment / tool orchestration",
     (), ("subprocess", "argparse"), False, False),
)

CAP_TEST = "C5"
CAP_IMPL = "C4"
DEFAULT_CAP = "C3"          # mined PRs are overwhelmingly bug fixes
CAP_CODES = tuple(spec[0] for spec in CAPABILITY_TAXONOMY)
SOURCE_EXTS = (".py", ".c", ".cc", ".cpp", ".go", ".rs", ".js", ".ts", ".java")

PATH_RULES = tuple(
    (needle, spec[0]) for spec in CAPABILITY_TAXONOMY for needle in spec[3]
)
PATCH_TOKEN_RULES = tuple(
    (needle, spec[0]) for spec in CAPABILITY_TAXONOMY for needle in spec[4]
)

# The publish gate the unit-test-validity audit applies to a capability axis.
# The THRESHOLDS are reusable; that audit's per-axis RESULTS are not, because it
# measured a different corpus (see AUDIT_REFERENCE).
PUBLISH_GATE = {
    "min_tasks": 5,
    "min_admitted_subtests": 10,
    "max_single_repo_share": 0.4,
}
GATE_SOURCE = {
    "path": "experiments/src/td_pipeline/unit_test_scoring.py",
    "symbol": "score_subtests",
    "commit": "3538604962867b9671fc585ee2449169abc7de3d",
}
AUDIT_REFERENCE = {
    "path": "experiments/reports/unit-test-validity-r001/SUMMARY.json",
    "schema": "terminal-daily-unit-test-validity-summary-v1",
    "release_commit": "b3fc3e620677215217be3525b86717fce9da7702",
    "generated_at": "2026-08-13T17:37:00Z",
    "file_sha256": (
        "a775f22f7b2a3b2aeeff51073c2b1e0eacc9e69b48960f594619819b024f53ef"
    ),
    "applies_to_this_catalogue": False,
    "reason": (
        "measured a different corpus at a different release commit; its "
        "per-axis counts describe that corpus, so they are not copied here "
        "and min_admitted_subtests stays unmeasured for this catalogue"
    ),
}
UNMEASURED_REASON = (
    "no unit-test-validity audit has classified this catalogue's F2P subtests "
    "high/medium/low confidence, so the admitted-subtest count does not exist"
)
NO_TASKS_REASON = (
    "no task carries this label, so there is no repo distribution to measure; "
    "the axis already fails on min_tasks"
)


# ---------------------------------------------------------------------------
# the tagger, vendored -- matching semantics are load-bearing, see the upstream
# comments: extension rules match the real extension, directory-segment rules
# match whole segments, token rules match ONLY added lines with word boundaries
# ---------------------------------------------------------------------------
def path_rule_matches(needle: str, path_lower: str) -> bool:
    if needle.startswith("."):
        return path_lower.endswith(needle)
    if needle.startswith("/") and not needle.endswith("/"):
        # Whole-segment: '/auth' hits 'src/auth/x' but never 'src/authority.py'.
        idx = path_lower.find(needle)
        while idx != -1:
            end = idx + len(needle)
            if end == len(path_lower) or path_lower[end] == "/":
                return True
            idx = path_lower.find(needle, idx + 1)
        return False
    return needle in path_lower


def looks_like_unified_diff(patch: str) -> bool:
    for line in patch.splitlines():
        if line.startswith(("diff --git ", "@@ ", "--- ", "+++ ")):
            return True
    return False


def added_patch_text(*patches: str) -> str:
    """The ADDED content only -- a deleted ``-import socket`` must not tag C7."""
    out: list[str] = []
    for patch in patches:
        if not patch:
            continue
        if not looks_like_unified_diff(patch):
            out.append(patch)  # plain code: all of it is "added"
            continue
        for line in patch.splitlines():
            if line.startswith("+++"):
                continue  # file header, not added content
            if line.startswith("+"):
                out.append(line[1:])
    return "\n".join(out)


TOKEN_RE_CACHE: dict = {}


def token_matches(needle: str, blob_lower: str) -> bool:
    """Word-boundary match: ``rebase`` must not fire inside ``rebased``."""
    pat = TOKEN_RE_CACHE.get(needle)
    if pat is None:
        left = r"(?<![0-9a-z_])" if needle[:1].isalnum() or needle[:1] == "_" else ""
        right = r"(?![0-9a-z_])" if needle[-1:].isalnum() or needle[-1:] == "_" else ""
        pat = re.compile(left + re.escape(needle) + right)
        TOKEN_RE_CACHE[needle] = pat
    return bool(pat.search(blob_lower))


def label_capabilities(files, solution_patch: str, test_patch: str) -> list:
    """Re-derivation of the pipeline's tagger. Never returns an empty list."""
    hits: "Counter[str]" = Counter()
    paths = [f for f in (files or []) if isinstance(f, str)]

    for path in paths:
        lowered = path.lower()
        for needle, cap in PATH_RULES:
            if path_rule_matches(needle, lowered):
                hits[cap] += 1

    blob = added_patch_text(solution_patch or "", test_patch or "").lower()
    for needle, cap in PATCH_TOKEN_RULES:
        if token_matches(needle, blob):
            hits[cap] += 1

    # A non-empty test diff is direct evidence of the verification capability.
    if (test_patch or "").strip():
        hits[CAP_TEST] += 1

    # Source (non-test) code changes imply implementation/refactor work.
    if any(
        path.endswith(SOURCE_EXTS) and "test" not in path.lower()
        for path in paths
    ):
        hits[CAP_IMPL] += 1

    if not hits:
        hits[DEFAULT_CAP] += 1

    # Stable order: hit count desc, then C-code numeric.
    return [
        cap for cap, _ in
        sorted(hits.items(), key=lambda kv: (-kv[1], int(kv[0][1:])))
    ]


# ---------------------------------------------------------------------------
# reading task packages
# ---------------------------------------------------------------------------
DIFF_GIT = re.compile(r"^diff --git a/(.+?) b/(.+)$")


def changed_files(*patches: str) -> list:
    """The PR's changed-file list, recovered from the two shipped diffs.

    The package does not store the list; ``diff --git a/X b/Y`` headers carry
    it, and both sides are kept because a rename changes the path the rules see.
    """
    out: list = []
    for patch in patches:
        for line in (patch or "").splitlines():
            found = DIFF_GIT.match(line)
            if not found:
                continue
            for path in (found.group(1), found.group(2)):
                if path != "/dev/null" and path not in out:
                    out.append(path)
    return out


def read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 -- a missing/odd file just means fewer fields
        return {}


def declared_keywords(task_dir: Path) -> list:
    """The C-codes task.toml declares. Non-C keywords are not capabilities."""
    text = read_text(task_dir / "task.toml")
    if not text:
        return []
    try:
        doc = tomllib.loads(text)
    except Exception:  # noqa: BLE001 -- a malformed package declares nothing
        return []
    words = (doc.get("task") or {}).get("keywords") or []
    return [str(w) for w in words if str(w) in CAP_CODES]


def read_packages(release: Path) -> list:
    """Every task package, each marked verifiable or not.

    A package is VERIFIABLE when it ships the tagger's inputs -- the oracle
    patch and/or the test diff -- plus the stored labels to check the result
    against. Live packages withhold the oracle patch by design; that is the
    point of a live split, so they carry only a declaration.
    """
    packages = []
    for status in ("archive", "live"):
        root = release / "tasks" / status
        if not root.is_dir():
            continue
        for task_dir in sorted(p for p in root.iterdir() if p.is_dir()):
            record = read_json(task_dir / "record.json")
            provenance = read_json(task_dir / "PROVENANCE.json")
            failing = read_json(task_dir / "FAILING_TESTS.json")
            f2p = record.get("fail_to_pass") or failing.get("failing_test_ids") or []
            solution = read_text(task_dir / "solution" / "oracle.patch")
            test_patch = read_text(task_dir / "tests" / "test_patch.diff")
            stored = record.get("capability_labels")
            verifiable = bool(solution or test_patch) and isinstance(stored, list)
            packages.append({
                "id": task_dir.name,
                "status": status,
                "repo": record.get("repo") or provenance.get("source_repo") or "",
                "n_f2p": len(f2p) if isinstance(f2p, list) else 0,
                "stored": stored if isinstance(stored, list) else None,
                "declared": declared_keywords(task_dir),
                "verifiable": verifiable,
                "labels": (
                    label_capabilities(
                        changed_files(solution, test_patch), solution, test_patch
                    )
                    if verifiable else None
                ),
            })
    return packages


def check_no_drift(packages: list) -> dict:
    """Re-derived labels must equal BOTH stored copies, or the build stops.

    This is the assertion that makes the vendored tables above trustworthy. A
    warning here would be worthless: a label that no longer follows from the
    rules is not a measurement, and shipping it anyway would restate the exact
    claim this generator exists to make good on.
    """
    mismatches = []
    for pkg in packages:
        if not pkg["verifiable"]:
            continue
        got = pkg["labels"]
        if got != pkg["stored"]:
            mismatches.append(
                pkg["id"] + ": record.json capability_labels="
                + json.dumps(pkg["stored"]) + " but the rules derive "
                + json.dumps(got)
            )
        if pkg["declared"] and got != pkg["declared"]:
            mismatches.append(
                pkg["id"] + ": task.toml keywords="
                + json.dumps(pkg["declared"]) + " but the rules derive "
                + json.dumps(got)
            )
    if mismatches:
        raise SystemExit(
            "FATAL: capability labels have drifted from the rules that produced "
            "them. Either the vendored tables in web/gen_capability_data.py are "
            "stale (re-vendor from " + RULES_SOURCE["path"] + ") or a package "
            "was hand-edited.\n  " + "\n  ".join(mismatches)
        )
    return {
        "stored_labels_match_rederivation": True,
        "checked_packages": sum(1 for p in packages if p["verifiable"]),
        "sources_checked": ["record.json:capability_labels", "task.toml:keywords"],
    }


# ---------------------------------------------------------------------------
# per-axis support and the gate
# ---------------------------------------------------------------------------
def criterion(threshold, observed, met, measured=True, note=None) -> dict:
    row = {"threshold": threshold, "observed": observed,
           "measured": measured, "met": met}
    if note:
        row["note"] = note
    return row


def axis_rows(verified: list, unverified: list) -> list:
    n_verified = len(verified)
    rows = []
    for spec in CAPABILITY_TAXONOMY:
        code, name, description = spec[0], spec[1], spec[2]
        frontier, risky = spec[5], spec[6]
        tagged = [p for p in verified if code in (p["labels"] or [])]
        repos = Counter(p["repo"] for p in tagged if p["repo"])
        n_tasks = len(tagged)
        top_repo, top_count = (repos.most_common(1)[0] if repos else ("", 0))
        # The audit computes repo share over TASKS, one repo per task.
        top_share = (top_count / n_tasks) if n_tasks else None
        declared = [p for p in unverified if code in p["declared"]]

        met_tasks = n_tasks >= PUBLISH_GATE["min_tasks"]
        # An axis with no tasks has no repo distribution. Upstream folds that
        # into a 1.0 share so the axis fails; here it is reported as what it is
        # -- unmeasurable -- because min_tasks already fails the axis and a
        # fabricated 100%-one-repo reading would render as a real concentration.
        share_row = (
            criterion(PUBLISH_GATE["max_single_repo_share"], top_share,
                      top_share <= PUBLISH_GATE["max_single_repo_share"])
            if n_tasks else
            criterion(PUBLISH_GATE["max_single_repo_share"], None, None,
                      measured=False, note=NO_TASKS_REASON)
        )
        criteria = {
            "min_tasks": criterion(PUBLISH_GATE["min_tasks"], n_tasks, met_tasks),
            "min_admitted_subtests": criterion(
                PUBLISH_GATE["min_admitted_subtests"], None, None,
                measured=False, note=UNMEASURED_REASON),
            "max_single_repo_share": share_row,
        }
        blockers = [key for key, row in criteria.items() if row["met"] is False]
        unmeasured = [key for key, row in criteria.items() if not row["measured"]]
        # Never "pass": one criterion of three cannot be computed here, so the
        # best any axis reaches is "every measurable criterion holds".
        verdict = "fail" if blockers else "blocked-unmeasured"

        rows.append({
            "code": code,
            "name": name,
            "description": description,
            "frontier": frontier,
            "risky_env": risky,
            "n_tasks": n_tasks,
            # Share of the verifiable catalogue this label covers. An axis near
            # 1.0 separates nothing; that is a property of the label, not of the
            # tasks, and no support gate can repair it.
            "coverage_share": (n_tasks / n_verified) if n_verified else None,
            "n_fail_to_pass": sum(p["n_f2p"] for p in tagged),
            "n_repos": len(repos),
            "repos": sorted(repos),
            "top_repo": top_repo,
            "top_repo_share": top_share,
            "task_ids": sorted(p["id"] for p in tagged),
            "criteria": criteria,
            "gate_verdict": verdict,
            "gate_blockers": blockers,
            "gate_unmeasured": unmeasured,
            "declared_unverified": {
                "n_tasks": len(declared),
                "task_ids": sorted(p["id"] for p in declared),
            },
        })
    return rows


def collect(release: Path) -> dict:
    packages = read_packages(release)
    verification = check_no_drift(packages)

    # One row per task id: a task can ship in BOTH splits, and the archive copy
    # is the one that carries the tagger's inputs.
    by_id: dict = {}
    for pkg in packages:
        prev = by_id.get(pkg["id"])
        if prev is None or (pkg["verifiable"] and not prev["verifiable"]):
            by_id[pkg["id"]] = pkg
    tasks = sorted(by_id.values(), key=lambda p: p["id"])
    verified = [p for p in tasks if p["verifiable"]]
    unverified = [p for p in tasks if not p["verifiable"]]

    rows = axis_rows(verified, unverified)
    coverage = [r["coverage_share"] for r in rows if r["coverage_share"]]
    return {
        "schema_version": SCHEMA,
        "generated": datetime.datetime.now(datetime.timezone.utc)
                             .strftime("%Y-%m-%dT%H:%M:%SZ"),
        "generator": "web/gen_capability_data.py",
        "rules_source": RULES_SOURCE,
        "gate_source": GATE_SOURCE,
        "publish_gate": PUBLISH_GATE,
        "publish_gate_computable": ["min_tasks", "max_single_repo_share"],
        "publish_gate_unmeasured": ["min_admitted_subtests"],
        "publish_gate_unmeasured_reason": UNMEASURED_REASON,
        "unit_test_validity_reference": AUDIT_REFERENCE,
        "verification": verification,
        "catalogue": {
            "n_packages_scanned": len(packages),
            "n_tasks": len(tasks),
            "n_tasks_verifiable": len(verified),
            "n_tasks_unverifiable": len(unverified),
            "unverifiable_reason": (
                "live packages withhold solution/oracle.patch and "
                "tests/test_patch.diff -- the tagger's only inputs -- so their "
                "task.toml keywords are reported as declared, never re-derived"
            ),
            "unverifiable_task_ids": sorted(p["id"] for p in unverified),
            "n_fail_to_pass_verifiable": sum(p["n_f2p"] for p in verified),
            "n_axes": len(CAPABILITY_TAXONOMY),
            "n_axes_with_tasks": sum(1 for r in rows if r["n_tasks"]),
            "n_axes_gate_blocked_only_by_unmeasured": sum(
                1 for r in rows if r["gate_verdict"] == "blocked-unmeasured"),
            "max_axis_coverage_share": max(coverage) if coverage else None,
        },
        "axes": rows,
    }


def main() -> int:
    here = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser()
    parser.add_argument("--release", default=str(here.parent))
    parser.add_argument("--out", default=None)
    args = parser.parse_args()
    release = Path(args.release)
    out = Path(args.out) if args.out else release / "docs" / "data" / "capability.json"
    data = retain_generated_timestamp(read_json(out), collect(release))
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(out.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=1)
        handle.write("\n")
    os.replace(tmp, out)
    cat = data["catalogue"]
    print(
        "capability axes: {} of {} carry tasks; {} of {} tasks re-derived and "
        "matched, {} withhold the oracle patch; {} gate criterion unmeasured "
        "-> {}".format(
            cat["n_axes_with_tasks"], cat["n_axes"],
            cat["n_tasks_verifiable"], cat["n_tasks"],
            cat["n_tasks_unverifiable"],
            len(data["publish_gate_unmeasured"]), out,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
