#!/usr/bin/env bash
# model-eval driver: score one MODEL on one TASK by the execution gate.
#
# The model call goes to a GENERIC OpenAI-compatible endpoint you configure via env:
#   OPENAI_BASE_URL   default https://api.openai.com/v1  (OpenAI / OpenRouter / vLLM / ...)
#   OPENAI_API_KEY    bearer key for that endpoint
# Scoring needs a singularity/apptainer host (harbor re-lays the protected tests).
# Run ONE at a time on a host with apptainer. 'oracle' needs no endpoint (gate baseline).
#
# Usage:  model_eval.sh <MODEL> <TASK_DIR> [OUT_JSON]
set -uo pipefail
MODEL="${1:?usage: model_eval.sh <MODEL> <TASK_DIR> [OUT_JSON]}"
TASK_DIR="${2:?usage: model_eval.sh <MODEL> <TASK_DIR> [OUT_JSON]}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORK="${TDB_WORK:-$PWD/.tdb_work}"
TASK_ID="$(basename "${TASK_DIR%/}")"
OUT="${3:-${WORK}/results/${TASK_ID}__$(echo "$MODEL" | tr -c 'A-Za-z0-9._-' '-').json}"
mkdir -p "$(dirname "$OUT")"

if [ "$(echo "$MODEL" | tr '[:upper:]' '[:lower:]')" != "oracle" ] && [ -z "${OPENAI_API_KEY:-}" ]; then
  echo "[model_eval] WARN: OPENAI_API_KEY unset; a real model call will fail (oracle needs no key)" >&2
fi
export PYTHONPATH="${HERE}${PYTHONPATH:+:$PYTHONPATH}"   # so model_eval imports harbor_score
python "${HERE}/model_eval.py" --model "$MODEL" --task "$TASK_DIR" --out "$OUT" --work "$WORK"
