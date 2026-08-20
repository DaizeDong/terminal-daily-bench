# W1 fixed-50: run on another cluster

This is the authoritative handoff for reproducing and running the frozen
Terminal Daily W1 fixed-50 set on another cluster.

## Frozen authority

- Repository: `https://github.com/DaizeDong/terminal-daily-bench.git`
- Branch: `codex/w1-image-publish-20260820`
- Frozen publication commit: `8bc06faa88df2cc6a023b019933ae8151b9c4f8b`
- Public registry: `ghcr.io/daizedong/terminal-daily-task-envs`
- Image manifest: `docs/registry/w1-fixed50-images.json`
- Publication receipt: `docs/registry/w1-fixed50-publish-receipt.json`
- Manifest SHA-256: `ffde4a161c38710dbbd83302784a4d30ca38804e80a6157ba5ffb7b2a3971d6a`
- Frozen roster SHA-256: `44b722079e4b47901b21f4086f77001fe8578b7279be62773ca347222bfaf6f1`

Do not reselect tasks or PRs, rebuild the images, or replace the image
identities. The manifest is the sole task-to-image authority: 50 task IDs map
to 49 unique images.

## 1. Clone and verify

```bash
git clone --branch codex/w1-image-publish-20260820 \
  --single-branch \
  https://github.com/DaizeDong/terminal-daily-bench.git

cd terminal-daily-bench

git merge-base --is-ancestor \
  8bc06faa88df2cc6a023b019933ae8151b9c4f8b HEAD

test "$(sha256sum docs/registry/w1-fixed50-images.json | cut -d' ' -f1)" = \
  "ffde4a161c38710dbbd83302784a4d30ca38804e80a6157ba5ffb7b2a3971d6a"

jq -e '
  .public_pull_verified == true
  and .task_count == 50
  and .image_count == 49
' docs/registry/w1-fixed50-publish-receipt.json
```

## 2. Pull the frozen images; do not rebuild them

The registry is public and requires no credentials.

For Docker, pull all 49 unique immutable OCI references with bounded
parallelism:

```bash
jq -r '.images[].canonical_ref' \
  docs/registry/w1-fixed50-images.json |
xargs -r -n1 -P3 docker pull --platform=linux/amd64
```

For Apptainer/Singularity, deduplicate by `.images[]` and pull the exact
`linux_amd64_manifest_digest` from:

```text
docker://ghcr.io/daizedong/terminal-daily-task-envs@<linux_amd64_manifest_digest>
```

Store one local SIF per `archive_sha256`, and keep a task-ID-to-SIF mapping.
The two PaperBanana tasks intentionally share one image.

The manifest records two different identities:

- `archive_sha256` authenticates the original deterministic gzip OCI archive.
- `linux_amd64_manifest_digest` authenticates the runnable registry image.

An Apptainer-generated native SIF will have a different local file SHA-256.
Record that local SHA separately; do not compare it with `archive_sha256`.

## 3. Preflight one canary

Use `td-626b33ab47f3a6eb` as the canary before spending model calls.

1. Confirm Python, the project-compatible patched Harbor, and
   Apptainer/Singularity are available.
2. Run `tdb doctor` for the canary task.
3. Bind the canary to its manifest-pinned image.
4. Run the oracle baseline and require `reward = 1.0`.
5. Confirm the model/harness cannot read `solution/` or protected test bodies.
6. Supply API credentials only through environment variables; never write them
   into commands, logs, or result records.

Do not silently substitute stock Harbor if it lacks the required Singularity
backend options. If the patched Harbor is absent, finish staging the checkout,
49 images, and task-image mapping, then report that exact blocker.

## 4. Run and resume all 50 tasks

Generate the queue only from `.tasks[].task_id` in the image manifest. Use any
eligible CPU nodes instead of waiting in one queue. As soon as a node starts,
let it claim an unfinished task.

For every model and harness combination:

- write an atomic checkpoint after every task;
- resume only missing or failed tasks;
- never rerun a successful cell merely for validation;
- retain stdout, stderr, patch, result JSON, runtime, and failure information;
- bind every result to task ID, repository, PR, base SHA, registry OCI digest,
  local SIF SHA, model build, harness version, Harbor version, and container
  runtime version.

The protected solution and tests are evaluation assets. Do not expose them to
the model process.

## 5. Completion criteria

The run is complete only when:

- all 50 unique task IDs have a terminal result;
- no task is missing or scored twice;
- each result is bound to its manifest-pinned OCI digest;
- one combined result JSONL and one run receipt are saved;
- success, failure, and retry-required task lists are explicit;
- the frozen checkout remains clean.

The image publisher and its checkpointing implementation are in
`scripts/publish_w1_fixed50_images.py`. Publication provenance is documented in
`docs/registry/`.
