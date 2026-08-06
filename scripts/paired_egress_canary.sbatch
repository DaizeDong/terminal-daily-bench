#!/usr/bin/env bash
#SBATCH --job-name=td-egress-canary
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --time=00:10:00

set -euo pipefail
umask 077
export PYTHONDONTWRITEBYTECODE=1

if [[ "$#" -ne 6 ]]; then
    echo "usage: paired_egress_canary.sbatch IMAGE RUNTIME HOST PORT WORK_ROOT OUT" >&2
    exit 2
fi

REPO_ROOT="${TD_PUBLIC_REPO_ROOT:-${SLURM_SUBMIT_DIR:-}}"
if [[ -z "${REPO_ROOT}" || ! -r "${REPO_ROOT}/scripts/paired_egress_canary.py" ]]; then
    echo "paired egress canary source is not readable on the compute node" >&2
    exit 3
fi

python3 "${REPO_ROOT}/scripts/paired_egress_canary.py" \
    --image "$1" \
    --runtime "$2" \
    --host "$3" \
    --port "$4" \
    --work-root "$5" \
    --out "$6"
