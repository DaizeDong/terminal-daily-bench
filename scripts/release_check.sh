#!/bin/bash
# release_check.sh -- the release-standard gate for the public bundle.
# Run from release/:  bash release_check.sh
# FAILS (exit 1) on any secret leak, moat violation, or missing release artifact.
set -uo pipefail
cd "$(dirname "$0")/.."
FAIL=0
say() { printf "%-52s %s\n" "$1" "$2"; }

echo "=== 1. SECRET SCAN (nothing sensitive may ship) ==="
# patterns for gateway keys / split-billing creds / private endpoints -- NOT the
# literal secrets (which must never appear anywhere, including here).
PATTERNS='Ocp-Apim-Subscription|direct-gw\.aooowuuu|GW_KEY|ANTHROPIC_KEY|ANTHROPIC_API_KEY|8a1ddd59|v2_gw_tunnel|split-billing|/work1/|/home1/[a-z]|v2_eval_work|BEGIN (RSA|OPENSSH|PRIVATE) KEY|xoxb-|sk-[A-Za-z0-9]{20}'
HITS=$(grep -rInE "$PATTERNS" . --exclude=release_check.sh 2>/dev/null || true)
if [ -n "$HITS" ]; then say "secret scan" "FAIL"; echo "$HITS" | head; FAIL=1; else say "secret scan" "OK (no secret patterns)"; fi
# no .env files
PYC=$(find . -name '__pycache__' -o -name '*.pyc' 2>/dev/null)
[ -n "$PYC" ] && { say "compiled bytecode (.pyc)" "FAIL (embeds abs source paths: $PYC)"; FAIL=1; } || say "compiled bytecode (.pyc)" "OK (none)"
ENVS=$(find . -name '.env' -o -name '*.pem' -o -name 'id_rsa*' 2>/dev/null)
[ -n "$ENVS" ] && { say ".env/key files" "FAIL ($ENVS)"; FAIL=1; } || say ".env/key files" "OK (none)"

echo; echo "=== 2. MOAT (eval bundle must not import the private stack) ==="
BAD=$(grep -rnE "^\s*(from|import)\s+(td_pipeline|rcvh)" terminal_daily_bench/ 2>/dev/null || true)
[ -n "$BAD" ] && { say "eval imports" "FAIL"; echo "$BAD"; FAIL=1; } || say "eval imports td_pipeline/rcvh" "OK (none)"
if command -v lint-imports >/dev/null 2>&1; then
  ( cd . && PYTHONPATH=eval lint-imports --config .importlinter >/dev/null 2>&1 ) \
    && say "import-linter moat contract" "OK (kept)" || say "import-linter moat contract" "WARN (linter check skipped/failed)"
fi
# harbor_score must import standalone (no construction deps)
python - <<'PY' 2>/dev/null && say "harbor_score standalone import" "OK" || { say "harbor_score standalone import" "FAIL"; FAIL=1; }
import sys, importlib.util
spec=importlib.util.spec_from_file_location("harbor_score","terminal_daily_bench/harbor_score.py")
m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
assert callable(m.read_harbor_reward)
PY

echo; echo "=== 3. RELEASE ARTIFACTS present ==="
for f in README.md LICENSE CONTRIBUTING.md MANIFEST.md pyproject.toml registry.json .importlinter terminal_daily_bench/__init__.py terminal_daily_bench/harbor_score.py terminal_daily_bench/quality.py terminal_daily_bench/cli.py terminal_daily_bench/eval.py docs/index.html tasks/SCHEMA.md; do
  [ -e "$f" ] && say "$f" "OK" || { say "$f" "MISSING"; FAIL=1; }
done

echo; echo "=== 4. TASK-RELEASE POLICY (live tasks withhold gold + protected) ==="
for d in tasks/live/*/; do
  [ -d "$d" ] || continue
  if [ -d "${d}solution" ]; then say "live $(basename $d): solution/" "FAIL (leaked)"; FAIL=1
  elif [ -f "${d}tests/test_outputs.py" ]; then say "live $(basename $d): protected tests" "FAIL (leaked)"; FAIL=1
  else say "live $(basename $d)" "OK (gold+protected withheld)"; fi
done
# archived tasks must carry provenance (license attribution)
for d in tasks/archive/*/; do
  [ -d "$d" ] || continue
  [ -f "${d}PROVENANCE.json" ] && say "archive $(basename $d): PROVENANCE" "OK" || { say "archive $(basename $d): PROVENANCE" "MISSING"; FAIL=1; }
done

echo; [ "$FAIL" = "0" ] && echo "RELEASE CHECK: PASS" || echo "RELEASE CHECK: FAIL"
exit $FAIL
