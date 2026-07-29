# Execution backend (harbor / apptainer)

Tasks run under **harbor** on an apptainer/singularity host. Two properties are
enforced here and are what make `false_accept = 0` real:

1. **Protected-test re-lay.** After a candidate patch is applied, harbor RE-LAYS the
   trusted `tests/` from the task package and runs them — the model's workspace edits
   to `tests/` are discarded. Reward = the re-laid tests' outcome.
2. **Runtime egress cut.** For run-offline tasks (`task.toml allow_internet = false`),
   the container runs with the network cut (`--network=none` / netns), so a solution
   cannot phone home. See `terminal_daily_bench/eval.py::_maybe_inject_offline_eks`.

Each task's `task.toml` sets `environment.docker_image` (portable: build from the task
`environment/Dockerfile`). Override cache/overlay locations via `TDB_SIF_CACHE` /
`TDB_OVERLAY_DIR`. Configure the model endpoint via `OPENAI_BASE_URL` / `OPENAI_API_KEY`.
