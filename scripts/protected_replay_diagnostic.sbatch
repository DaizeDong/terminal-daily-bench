#!/usr/bin/env bash
#SBATCH --job-name=td-w4-replay-diag
#SBATCH --partition=devel
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --time=00:25:00

set -euo pipefail

: "${TDB_PUBLIC_REPO:?export the public repository path}"
: "${TDB_VENV_BIN:?export the environment bin directory containing tdb and harbor}"
: "${TDB_W4_EVIDENCE_ROOT:?export a private persistent evidence directory}"
: "${TDB_W4_TASK_SIF:?export the absolute prebuilt task SIF path}"
: "${TDB_W4_TASK_SIF_SHA256:?export the pinned task SIF SHA-256}"

umask 077
mkdir -p "${TDB_W4_EVIDENCE_ROOT}"
python3 "${TDB_PUBLIC_REPO}/scripts/protected_replay_diagnostic.py" \
  --task "${TDB_PUBLIC_REPO}/tasks/archive/td-fc90ea8b76d5f6b6" \
  --task-sif "${TDB_W4_TASK_SIF}" \
  --task-sif-sha256 "${TDB_W4_TASK_SIF_SHA256}" \
  --bad-patch "${TDB_PUBLIC_REPO}/scripts/diagnostics/td-fc90ea8b76d5f6b6-bad.patch" \
  --tdb "${TDB_VENV_BIN}/tdb" \
  --harbor "${TDB_VENV_BIN}/harbor" \
  --runtime /usr/bin/apptainer \
  --out "${TDB_W4_EVIDENCE_ROOT}/run-${SLURM_JOB_ID}" \
  --harbor-timeout 480
