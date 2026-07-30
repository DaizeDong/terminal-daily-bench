#!/bin/sh
# build_task_image.sh -- turn a released task's environment/Dockerfile into a
# locally runnable container image, and print the image path/ref on stdout.
#
# WHY THIS EXISTS
# ---------------
# A published task ships `task.toml` with the PORTABLE image reference
#
#     [environment]
#     docker_image = "environment/Dockerfile"   # build from the task Dockerfile
#
# (see tasks/publish_tasks.py::_sanitize_task_toml -- the producer's host-specific
# absolute .sif path is deliberately NOT shipped). Nothing can execute that string
# as-is: `terminal_daily_bench/eval.py` hands `environment.docker_image` to harbor
# (`harbor run -e singularity`) and also `os.path.exists()`-checks it to read repo
# files out of the image. So a downloaded task needs ONE local step first: build the
# Dockerfile into an image and point `docker_image` at the result. This script is
# that step.
#
# USAGE
#   scripts/build_task_image.sh [options] <TASK_DIR>
#
#   options:
#     --force               rebuild even if the cached image already exists
#     --builder BUILDER     auto (default) | apptainer | docker
#     --via-docker          build with docker, then convert to .sif with apptainer
#                           (highest fidelity for Dockerfiles this script's own
#                            translator cannot express; needs BOTH tools)
#     --cache DIR           image cache dir (overrides $TDB_SIF_CACHE)
#     --no-server-deps      do not bake uvicorn/fastapi into the .sif (see below)
#     -h, --help            this help
#
# OUTPUT
#   stdout: exactly one line -- the image path (.sif) or docker tag. Everything
#           else (progress, warnings, hints) goes to stderr, so the script composes:
#               IMG="$(scripts/build_task_image.sh tasks/archive/<id>)"
#
# CACHE / IDEMPOTENCY
#   Images land in $TDB_SIF_CACHE (default ./.tdb_work/sif_cache -- the same default
#   eval.py uses for `singularity_image_cache_dir`). The file name is
#   <task-id>-<first 12 hex of sha256(Dockerfile)>.sif, so an unchanged Dockerfile
#   maps to the same image and a second run is a no-op ("skip, already built").
#   --force deletes and rebuilds.
#
# BUILDERS
#   apptainer/singularity CANNOT read a Dockerfile directly, so the apptainer path
#   TRANSLATES the Dockerfile into an apptainer definition file (a documented,
#   deliberately small subset: FROM / ARG / ENV / WORKDIR / RUN / COPY, plus a few
#   instructions that are irrelevant under harbor and are skipped). Anything the
#   translator does not understand is a HARD ERROR with an actionable message --
#   it never guesses. Use --via-docker (or --builder docker) for those.
#   Every tool flag used below is probed against the installed binary's own --help
#   before use; nothing is assumed to exist.
#
# NOTE ON --no-server-deps
#   Harbor's singularity backend starts a small in-container HTTP server, and a
#   run-offline task (`allow_internet = false`) has no egress to install it at run
#   time. The reference build therefore bakes uvicorn+fastapi into the image
#   best-effort (never fatal). Pass --no-server-deps to build the Dockerfile
#   verbatim instead.
#
# POSIX sh; no bashisms.

set -eu

ME="build_task_image.sh"

log()  { printf '[%s] %s\n' "$ME" "$*" >&2; }
die()  { printf '[%s] ERROR: %s\n' "$ME" "$*" >&2; exit 1; }
have() { command -v "$1" >/dev/null 2>&1; }

usage() {
    cat >&2 <<'EOF'
usage: build_task_image.sh [options] <TASK_DIR>

Build a released task's environment/Dockerfile into a local container image and
print the image path (stdout) so it can be put into task.toml's
[environment] docker_image.

options:
  --force             rebuild even if the cached image already exists
  --builder BUILDER   auto (default) | apptainer | docker
  --via-docker        build with docker, then convert to .sif with apptainer
  --cache DIR         image cache dir (default $TDB_SIF_CACHE or ./.tdb_work/sif_cache)
  --no-server-deps    do not bake uvicorn/fastapi into the image
  -h, --help          show this help

example:
  IMG=$(scripts/build_task_image.sh tasks/archive/td-fc90ea8b76d5f6b6)
EOF
}

# --- flag support probe: only use a flag the installed binary actually documents.
supports_flag() {   # supports_flag <bin> <subcmd> <--flag>
    "$1" "$2" --help 2>&1 | grep -q -- "$3"
}

# ---------------------------------------------------------------------------
# arguments
# ---------------------------------------------------------------------------
FORCE=0
BUILDER=auto
VIA_DOCKER=0
CACHE_DIR="${TDB_SIF_CACHE:-./.tdb_work/sif_cache}"
SERVER_DEPS=1
TASK_DIR=""

while [ $# -gt 0 ]; do
    case "$1" in
        --force)          FORCE=1 ;;
        --builder)        shift; [ $# -gt 0 ] || die "--builder needs a value"; BUILDER="$1" ;;
        --builder=*)      BUILDER="${1#--builder=}" ;;
        --via-docker)     VIA_DOCKER=1 ;;
        --cache)          shift; [ $# -gt 0 ] || die "--cache needs a value"; CACHE_DIR="$1" ;;
        --cache=*)        CACHE_DIR="${1#--cache=}" ;;
        --no-server-deps) SERVER_DEPS=0 ;;
        -h|--help)        usage; exit 0 ;;
        -*)               die "unknown option '$1' (try --help)" ;;
        *)                [ -z "$TASK_DIR" ] || die "only one TASK_DIR expected (got '$TASK_DIR' and '$1')"
                          TASK_DIR="$1" ;;
    esac
    shift
done

[ -n "$TASK_DIR" ] || { usage; exit 2; }
case "$BUILDER" in auto|apptainer|docker) ;; *) die "--builder must be auto|apptainer|docker (got '$BUILDER')" ;; esac

[ -d "$TASK_DIR" ] || die "task dir not found: $TASK_DIR"
DOCKERFILE="$TASK_DIR/environment/Dockerfile"
[ -f "$DOCKERFILE" ] || die "no environment/Dockerfile in task dir: $TASK_DIR
This script builds a task package's own environment; point it at a directory like
tasks/archive/td-xxxxxxxxxxxxxxxx/."

# absolute paths (the printed image ref must be usable from any cwd)
TASK_DIR=$(cd "$TASK_DIR" && pwd)
DOCKERFILE="$TASK_DIR/environment/Dockerfile"
TASK_ID=$(basename "$TASK_DIR")

# ---------------------------------------------------------------------------
# cache key: <task-id>-<sha256(Dockerfile) prefix>
# ---------------------------------------------------------------------------
hash_file() {
    if have sha256sum;  then sha256sum "$1"      | cut -c1-12; return; fi
    if have shasum;     then shasum -a 256 "$1"  | cut -c1-12; return; fi
    if have openssl;    then openssl dgst -sha256 "$1" | tr -d ' ' | sed 's/.*=//' | cut -c1-12; return; fi
    # last resort: cksum is not cryptographic, but it still keys the cache on content
    cksum "$1" | awk '{printf "c%s\n", $1}'
}
DF_HASH=$(hash_file "$DOCKERFILE")
[ -n "$DF_HASH" ] || die "could not hash $DOCKERFILE"

mkdir -p "$CACHE_DIR"
CACHE_DIR=$(cd "$CACHE_DIR" && pwd)
SIF_PATH="$CACHE_DIR/${TASK_ID}-${DF_HASH}.sif"
DOCKER_TAG="terminal-daily/${TASK_ID}:${DF_HASH}"

# ---------------------------------------------------------------------------
# builder detection -- fail LOUDLY if there is nothing to build with
# ---------------------------------------------------------------------------
APPTAINER_BIN=""
if   have apptainer;   then APPTAINER_BIN=apptainer
elif have singularity; then APPTAINER_BIN=singularity
fi

DOCKER_BIN=""
if have docker; then
    if docker info >/dev/null 2>&1; then
        DOCKER_BIN=docker
    else
        log "WARN: 'docker' is on PATH but the daemon is not reachable ('docker info' failed); ignoring it."
    fi
fi

if [ -z "$APPTAINER_BIN" ] && [ -z "$DOCKER_BIN" ]; then
    die "no container builder found.
This task's environment must be built before it can run, and neither builder is usable:
  * apptainer / singularity : not on PATH   (install apptainer -- https://apptainer.org/docs/admin/main/installation.html)
  * docker                  : not on PATH, or the daemon is not running/reachable
terminal-daily-bench scores tasks with 'harbor run ... -e singularity', so apptainer
is the primary target; docker works if you drive harbor with '-e docker' instead."
fi

if [ "$VIA_DOCKER" -eq 1 ]; then
    [ -n "$DOCKER_BIN" ]    || die "--via-docker needs a usable docker daemon (see 'docker info')"
    [ -n "$APPTAINER_BIN" ] || die "--via-docker needs apptainer/singularity to convert the docker image to .sif"
    BUILDER=apptainer
fi

if [ "$BUILDER" = auto ]; then
    if [ -n "$APPTAINER_BIN" ]; then BUILDER=apptainer; else BUILDER=docker; fi
fi
[ "$BUILDER" != apptainer ] || [ -n "$APPTAINER_BIN" ] || die "--builder apptainer requested but no apptainer/singularity on PATH"
[ "$BUILDER" != docker    ] || [ -n "$DOCKER_BIN"    ] || die "--builder docker requested but no usable docker daemon"

# ---------------------------------------------------------------------------
# idempotency: already built?
# ---------------------------------------------------------------------------
already_built() {
    if [ "$BUILDER" = apptainer ]; then
        [ -s "$SIF_PATH" ]
    else
        docker image inspect "$DOCKER_TAG" >/dev/null 2>&1
    fi
}

final_ref() {
    if [ "$BUILDER" = apptainer ]; then printf '%s\n' "$SIF_PATH"; else printf '%s\n' "$DOCKER_TAG"; fi
}

hint() {
    if [ "$BUILDER" = apptainer ]; then
        log "next: point the task at it, e.g."
        log "      sed -i 's|^docker_image .*|docker_image = \"$SIF_PATH\"|' $TASK_DIR/task.toml"
        log "      tdb oracle $TASK_DIR      # expect reward = 1.0"
    else
        log "next: set docker_image = \"$DOCKER_TAG\" in $TASK_DIR/task.toml and drive harbor with '-e docker'."
    fi
}

if already_built; then
    if [ "$FORCE" -eq 0 ]; then
        log "already built (unchanged Dockerfile): $(final_ref)  [use --force to rebuild]"
        hint
        final_ref
        exit 0
    fi
    log "--force: rebuilding $(final_ref)"
    [ "$BUILDER" != apptainer ] || rm -f "$SIF_PATH"
fi

# ---------------------------------------------------------------------------
# Dockerfile -> apptainer definition translation
# ---------------------------------------------------------------------------
# Supported subset (everything a published terminal-daily environment/Dockerfile
# uses): FROM (single stage) / ARG / ENV / WORKDIR / RUN / COPY.
# Skipped as irrelevant under harbor (it exec's its own command):
#   CMD ENTRYPOINT EXPOSE LABEL MAINTAINER VOLUME STOPSIGNAL HEALTHCHECK
# Hard error (semantics we refuse to fake): ADD USER SHELL ONBUILD, multi-stage
# FROM, COPY --from=.
# Docker semantics preserved: each RUN starts in the current WORKDIR (apptainer's
# %post is ONE shell script, so we cd back before every RUN), ARG/ENV become shell
# variables, and %post runs under `set -e` so any failing step aborts the build --
# never a silently half-built environment.
write_def() {   # write_def <dockerfile> <out.def> <server_deps 0|1>
    awk -v SERVER_DEPS="$3" -v CTX="$(dirname "$1")" '
    function fail(msg) { printf "TRANSLATE_ERROR: %s\n", msg > "/dev/stderr"; exit_code = 1; exit 1 }
    function emit_post(line) { post[++np] = line }
    BEGIN { wd = "/"; nfrom = 0; np = 0; nenv = 0; nfiles = 0 }

    # --- join backslash continuations into one logical instruction -----------
    {
        line = $0
        sub(/\r$/, "", line)
        if (cont) {
            sub(/^[ \t]+/, "", line)
            if (line ~ /^#/) next               # comments inside a continuation are dropped
            buf = buf " " line
        } else {
            if (line ~ /^[ \t]*#/) next         # standalone comment
            if (line ~ /^[ \t]*$/) next         # blank
            buf = line
        }
        if (buf ~ /\\[ \t]*$/) { sub(/\\[ \t]*$/, "", buf); cont = 1; next }
        cont = 0
        process(buf)
        next
    }

    function process(l,   instr, rest, i, k, v, dest, src) {
        sub(/^[ \t]+/, "", l)
        i = match(l, /[ \t]/)
        if (i == 0) fail("cannot parse instruction: " l)
        instr = toupper(substr(l, 1, i - 1))
        rest  = substr(l, i + 1)
        sub(/^[ \t]+/, "", rest); sub(/[ \t]+$/, "", rest)

        if (instr == "FROM") {
            if (++nfrom > 1) fail("multi-stage build (more than one FROM) -- rerun with --via-docker")
            if (rest ~ /^--/) fail("FROM flags (e.g. --platform) are not translated -- rerun with --via-docker")
            if (toupper(rest) ~ / AS /) fail("named build stage (FROM ... AS ...) -- rerun with --via-docker")
            base = rest
            return
        }
        if (instr == "ARG") {
            if (index(rest, "=") == 0) {
                # ARG with no default: require it in the environment rather than
                # silently building with an empty value.
                emit_post("    : \"${" rest "?required build arg: export " rest "=... before building}\"")
                emit_post("    export " rest)
                return
            }
            k = substr(rest, 1, index(rest, "=") - 1)
            v = substr(rest, index(rest, "=") + 1)
            gsub(/^"|"$/, "", v)
            if (index(v, "\"") > 0) fail("ARG default containing a double quote is not translated: " rest)
            # ${K:-default} keeps docker'\''s "overridable build arg" semantics:
            # export REPO_URL=... before building to override.
            emit_post("    export " k "=\"${" k ":-" v "}\"")
            return
        }
        if (instr == "ENV") {
            if (index(rest, "=") == 0) {          # ENV KEY VALUE (legacy form)
                k = rest; sub(/[ \t].*$/, "", k)
                v = rest; sub(/^[^ \t]+[ \t]+/, "", v)
                rest = k "=\"" v "\""
            }
            emit_post("    export " rest)
            envs[++nenv] = "    export " rest
            return
        }
        if (instr == "WORKDIR") {
            wd = rest
            emit_post("    mkdir -p \"" wd "\"")
            emit_post("    cd \"" wd "\"")
            return
        }
        if (instr == "RUN") {
            if (rest ~ /^\[/) fail("RUN in JSON/exec form is not translated -- rerun with --via-docker")
            if (rest ~ /^--/) fail("RUN flags (e.g. --mount) are not translated -- rerun with --via-docker")
            emit_post("    cd \"" wd "\"")       # docker restarts every RUN in WORKDIR
            emit_post("    " rest)
            return
        }
        if (instr == "COPY") {
            if (rest ~ /--from=/) fail("COPY --from= (multi-stage) -- rerun with --via-docker")
            sub(/^--[^ \t]+[ \t]+/, "", rest)     # tolerate --chown=/--chmod=
            dest = rest; sub(/^.*[ \t]/, "", dest)
            src  = rest; sub(/[ \t][^ \t]+$/, "", src)
            if (dest !~ /^\//) dest = wd "/" dest
            # COPY sources are relative to the build context (the task environment/
            # dir); apptainer resolves %files sources relative to the CWD, so anchor.
            if (src !~ /^\//) src = CTX "/" src
            files[++nfiles] = src " " dest
            printf "TRANSLATE_WARN: COPY %s -> %s is emitted as an apptainer %%files entry, which runs BEFORE %%post (docker would copy it in order). Use --via-docker if ordering matters.\n", src, dest > "/dev/stderr"
            return
        }
        if (instr == "CMD" || instr == "ENTRYPOINT" || instr == "EXPOSE" || instr == "LABEL" ||
            instr == "MAINTAINER" || instr == "VOLUME" || instr == "STOPSIGNAL" || instr == "HEALTHCHECK") {
            printf "TRANSLATE_NOTE: skipping %s (harbor execs its own command inside the image)\n", instr > "/dev/stderr"
            return
        }
        fail(instr " is not supported by the Dockerfile->apptainer translator -- rerun with --via-docker (docker build + apptainer conversion)")
    }

    END {
        if (exit_code) exit 1
        if (cont) { printf "TRANSLATE_ERROR: Dockerfile ends with a dangling line continuation\n" > "/dev/stderr"; exit 1 }
        if (nfrom == 0) { printf "TRANSLATE_ERROR: Dockerfile has no FROM instruction\n" > "/dev/stderr"; exit 1 }

        print "Bootstrap: docker"
        print "From: " base
        print ""
        if (nfiles) {
            print "%files"
            for (i = 1; i <= nfiles; i++) print "    " files[i]
            print ""
        }
        print "%post"
        print "    # generated from the task environment/Dockerfile by build_task_image.sh"
        print "    set -e"
        print "    # Debian 12+/Ubuntu 24+ bases mark the system python externally-managed"
        print "    # (PEP 668); the reference build opts out so a root pip install works."
        print "    export PIP_BREAK_SYSTEM_PACKAGES=1"
        print "    export PIP_ROOT_USER_ACTION=ignore"
        for (i = 1; i <= np; i++) print post[i]
        if (SERVER_DEPS == 1) {
            print "    # harbor'\''s singularity backend starts an in-container HTTP server and a"
            print "    # run-offline task has no egress at run time -> bake the deps now."
            print "    # Best-effort: harbor can also fall back to a bind-mounted deps dir."
            print "    (python -m pip install --no-cache-dir uvicorn fastapi || true)"
        }
        if (nenv) {
            print ""
            print "%environment"
            for (i = 1; i <= nenv; i++) print envs[i]
        }
    }
    ' "$1" > "$2"
}

# ---------------------------------------------------------------------------
# build
# ---------------------------------------------------------------------------
WORK_TMP="${TMPDIR:-/tmp}/${ME}.$$"
mkdir -p "$WORK_TMP"
cleanup() { rm -rf "$WORK_TMP"; }
trap cleanup EXIT INT TERM

build_with_docker() {   # build_with_docker <tag>
    log "docker build -t $1 (context: $TASK_DIR/environment)"
    docker build -t "$1" -f "$DOCKERFILE" "$TASK_DIR/environment" >&2 \
        || die "docker build failed for $TASK_ID (see the log above)"
}

build_sif_from_def() {
    DEF="$WORK_TMP/${TASK_ID}.def"
    log "translating Dockerfile -> apptainer definition"
    write_def "$DOCKERFILE" "$DEF" "$SERVER_DEPS" \
        || die "could not translate $DOCKERFILE into an apptainer definition (see TRANSLATE_ERROR above).
Workaround: install/start docker and rerun with --via-docker, which builds the
Dockerfile with docker and converts the result to .sif."
    cp "$DEF" "$CACHE_DIR/${TASK_ID}-${DF_HASH}.def"   # keep the recipe next to the image (auditable)

    set -- build
    # --fakeroot: needed for an unprivileged build whose %post runs apt/pip as root.
    # Probe the installed binary's help before using it; skip it when already root.
    if [ "$(id -u)" -ne 0 ] && supports_flag "$APPTAINER_BIN" build --fakeroot; then
        set -- "$@" --fakeroot
    fi
    if supports_flag "$APPTAINER_BIN" build --force; then
        set -- "$@" --force
    fi
    if run_apptainer "$@" "$SIF_PATH" "$DEF"; then return 0; fi

    # Known apptainer failure mode: the base image ships no usable `fakeroot`
    # helper (musl/alpine bases), and apptainer itself tells you to retry with
    # --ignore-fakeroot-command. That flag is not listed in `build --help`, so we
    # probe the binary for it (rather than assuming) before retrying ONCE.
    if grep -qi 'fakeroot' "$BUILD_LOG" 2>/dev/null &&
       "$APPTAINER_BIN" build --ignore-fakeroot-command --help >/dev/null 2>&1; then
        log "retrying once with --ignore-fakeroot-command (the base image has no usable fakeroot helper)"
        if run_apptainer "$@" --ignore-fakeroot-command "$SIF_PATH" "$DEF"; then return 0; fi
    fi

    die "apptainer build failed for $TASK_ID (see the log above).
Common causes: no network for the base image / repo clone (the build stage needs
egress even though the scored run is offline), or a dependency install that the
task's Dockerfile intentionally hard-fails on."
}

# Run apptainer, STREAMING its output to stderr while also capturing it to
# $BUILD_LOG (POSIX sh has no pipefail, so the exit status goes through a file).
run_apptainer() {
    BUILD_LOG="$WORK_TMP/build.log"
    log "$APPTAINER_BIN $*"
    { "$APPTAINER_BIN" "$@" 2>&1; echo $? > "$WORK_TMP/rc"; } | tee "$BUILD_LOG" >&2
    [ "$(cat "$WORK_TMP/rc")" = 0 ]
}

build_sif_from_docker() {
    build_with_docker "$DOCKER_TAG"
    set -- build
    if supports_flag "$APPTAINER_BIN" build --force; then set -- "$@" --force; fi
    run_apptainer "$@" "$SIF_PATH" "docker-daemon://$DOCKER_TAG" \
        || die "converting docker image $DOCKER_TAG to $SIF_PATH failed (see the log above)"
}

if [ "$BUILDER" = apptainer ]; then
    if [ "$VIA_DOCKER" -eq 1 ]; then build_sif_from_docker; else build_sif_from_def; fi
    [ -s "$SIF_PATH" ] || die "build reported success but $SIF_PATH is missing/empty"
else
    build_with_docker "$DOCKER_TAG"
    docker image inspect "$DOCKER_TAG" >/dev/null 2>&1 \
        || die "build reported success but docker image $DOCKER_TAG is missing"
fi

log "built $(final_ref)"
hint
final_ref
