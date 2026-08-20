"""Node-local, content-addressed leases for frozen task SIF images.

The campaign state is durable shared storage, while multi-gigabyte SIF images
are execution inputs.  Keeping one private object per content digest on the
compute node avoids copying the same image into every durable cell work tree.
The small receipt and binding records remain portable and auditable.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import shutil
import stat
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping


CACHE_ROOT_ENV = "TD_TASK_SIF_CACHE_ROOT"
CACHE_RECEIPT_SCHEMA = "terminal-daily-task-sif-cache-receipt-v1"
CACHE_BINDING_SCHEMA = "terminal-daily-task-sif-cache-binding-v1"
CACHE_PROOF_SCHEMA = "terminal-daily-task-sif-cache-proof-v1"

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_POPULATE_TEMP_RE = re.compile(
    r"^\.populate-[0-9a-f]{64}-[0-9]+-[a-z0-9_]+$"
)
_CACHE_VERSION = "v1"
_MAX_RECEIPT_BYTES = 64 * 1024
_MIN_FREE_SPACE_RESERVE_BYTES = 16 * 1024 * 1024 * 1024
_STABLE_FIELDS = (
    "st_dev", "st_ino", "st_nlink", "st_size", "st_mtime_ns", "st_ctime_ns",
)
_IDENTITY_KEYS = {
    "st_dev", "st_ino", "st_nlink", "st_size", "st_mtime_ns", "st_ctime_ns",
    "st_uid", "mode",
}


class TaskSIFCacheError(ValueError):
    """A frozen SIF or its node-local cache binding failed validation."""


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise TaskSIFCacheError(f"duplicate task SIF cache receipt key: {key}")
        result[key] = value
    return result


def _mode(value: os.stat_result) -> int:
    return stat.S_IMODE(value.st_mode)


def _stable_facts(value: os.stat_result) -> tuple[int, ...]:
    return tuple(int(getattr(value, field)) for field in _STABLE_FIELDS)


def _identity(value: os.stat_result) -> dict[str, int]:
    return {
        "st_dev": int(value.st_dev),
        "st_ino": int(value.st_ino),
        "st_nlink": int(value.st_nlink),
        "st_size": int(value.st_size),
        "st_mtime_ns": int(value.st_mtime_ns),
        "st_ctime_ns": int(value.st_ctime_ns),
        "st_uid": int(value.st_uid),
        "mode": _mode(value),
    }


def _identity_sha256(value: Mapping[str, int]) -> str:
    return _sha256(_canonical_json(dict(value)))


def default_task_sif_cache_root(
    environ: Mapping[str, str] | None = None,
) -> Path:
    """Return an absolute per-node cache root shared by evaluator processes."""
    env = os.environ if environ is None else environ
    configured = env.get(CACHE_ROOT_ENV)
    if configured:
        root = Path(configured)
        if not root.is_absolute():
            raise TaskSIFCacheError(f"{CACHE_ROOT_ENV} must be an absolute path")
        return root
    # TMPDIR and SLURM_TMPDIR are frequently job-private or redirected to
    # shared campaign storage.  Host /tmp gives all jobs for this UID on one
    # node the same default; formal wrappers still validate its device/mount.
    return Path("/tmp") / f"tdb-task-sif-cache-{os.geteuid()}"


def _validate_directory(path: Path, expected_mode: int) -> os.stat_result:
    try:
        value = path.lstat()
    except OSError as exc:
        raise TaskSIFCacheError(f"task SIF cache directory is unavailable: {path}") from exc
    if not stat.S_ISDIR(value.st_mode):
        raise TaskSIFCacheError(f"task SIF cache path is not a directory: {path}")
    if value.st_uid != os.geteuid():
        raise TaskSIFCacheError(f"task SIF cache directory is not owned by this user: {path}")
    if _mode(value) != expected_mode:
        raise TaskSIFCacheError(
            f"task SIF cache directory must have mode {expected_mode:04o}: {path}"
        )
    return value


def _create_private_directory(path: Path, mode: int = 0o700) -> None:
    try:
        path.mkdir(mode=mode)
    except FileExistsError:
        pass
    _validate_directory(path, mode)


@dataclass(frozen=True)
class _CacheLayout:
    root: Path
    version: Path
    locks: Path
    objects: Path
    sha256_objects: Path
    temporary: Path


def _prepare_layout(root: Path) -> _CacheLayout:
    if not root.is_absolute():
        raise TaskSIFCacheError("task SIF cache root must be absolute")
    try:
        root.mkdir(parents=True, mode=0o700)
    except FileExistsError:
        pass
    _validate_directory(root, 0o700)
    version = root / _CACHE_VERSION
    locks = version / "locks"
    objects = version / "objects"
    sha256_objects = objects / "sha256"
    temporary = version / "tmp"
    for path in (version, locks, objects, sha256_objects, temporary):
        _create_private_directory(path)
    return _CacheLayout(root, version, locks, objects, sha256_objects, temporary)


def _open_private_lock(path: Path) -> int:
    flags = os.O_RDWR | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        fd = os.open(path, flags)
    try:
        path_stat = path.lstat()
        value = os.fstat(fd)
        if (
            not stat.S_ISREG(value.st_mode)
            or value.st_uid != os.geteuid()
            or value.st_nlink != 1
            or _mode(value) != 0o600
            or (value.st_dev, value.st_ino) != (path_stat.st_dev, path_stat.st_ino)
        ):
            raise TaskSIFCacheError(f"unsafe task SIF cache lock: {path}")
        return fd
    except Exception:
        os.close(fd)
        raise


def _fsync_directory(path: Path) -> None:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_DIRECTORY", 0)
    fd = os.open(path, flags)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _write_all(fd: int, value: bytes) -> None:
    view = memoryview(value)
    while view:
        written = os.write(fd, view)
        if written <= 0:
            raise OSError("short write while persisting task SIF cache metadata")
        view = view[written:]


def _write_private_file(path: Path, value: bytes, mode: int = 0o400) -> None:
    flags = (
        os.O_WRONLY | os.O_CREAT | os.O_EXCL
        | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    )
    fd = os.open(path, flags, 0o600)
    try:
        _write_all(fd, value)
        os.fchmod(fd, mode)
        os.fsync(fd)
    finally:
        os.close(fd)


def _atomic_write_private_file(path: Path, value: bytes, mode: int = 0o400) -> None:
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        _write_all(fd, value)
        os.fchmod(fd, mode)
        os.fsync(fd)
        os.close(fd)
        fd = -1
        os.link(temporary, path, follow_symlinks=False)
        temporary.unlink()
    finally:
        if fd >= 0:
            os.close(fd)
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def _read_private_file(path: Path, maximum: int = _MAX_RECEIPT_BYTES) -> tuple[bytes, os.stat_result]:
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    cloexec = getattr(os, "O_CLOEXEC", 0)
    fd = os.open(path, os.O_RDONLY | nofollow | cloexec)
    try:
        path_stat = path.lstat()
        before = os.fstat(fd)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_uid != os.geteuid()
            or before.st_nlink != 1
            or _mode(before) != 0o400
            or (before.st_dev, before.st_ino) != (path_stat.st_dev, path_stat.st_ino)
        ):
            raise TaskSIFCacheError(f"unsafe task SIF cache metadata file: {path}")
        chunks: list[bytes] = []
        remaining = maximum + 1
        while remaining:
            chunk = os.read(fd, min(64 * 1024, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        raw = b"".join(chunks)
        if len(raw) > maximum:
            raise TaskSIFCacheError(f"task SIF cache metadata is too large: {path}")
        after = os.fstat(fd)
        if _stable_facts(before) != _stable_facts(after):
            raise TaskSIFCacheError(f"task SIF cache metadata changed while read: {path}")
        return raw, after
    finally:
        os.close(fd)


def _resolve_source(path: str) -> Path:
    if not os.path.isabs(path):
        raise TaskSIFCacheError("--task-sif must be an absolute path")
    supplied = Path(path)
    try:
        resolved = supplied.resolve(strict=True)
    except OSError as exc:
        raise TaskSIFCacheError("--task-sif does not resolve to a readable file") from exc
    if os.path.abspath(path) != str(resolved):
        raise TaskSIFCacheError("--task-sif must not traverse a symbolic link")
    if resolved.suffix.lower() != ".sif":
        raise TaskSIFCacheError("--task-sif must resolve to a regular .sif file")
    value = resolved.lstat()
    if (
        not stat.S_ISREG(value.st_mode)
        or value.st_uid != os.geteuid()
        or value.st_nlink != 1
        or _mode(value) & 0o022
    ):
        raise TaskSIFCacheError(
            "--task-sif must be an owner-controlled, single-link regular file"
        )
    return resolved


@dataclass(frozen=True)
class _PublishedObject:
    path: Path
    receipt_path: Path
    receipt: dict[str, Any]
    receipt_bytes: bytes
    receipt_sha256: str
    object_identity: dict[str, int]
    receipt_identity: dict[str, int]
    directory_identity: dict[str, int]


def _validate_receipt(value: Any, expected_sha256: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != {
        "schema", "content_sha256", "size", "source", "cached_identity",
        "created_unix_ns", "credential_values_persisted",
    }:
        raise TaskSIFCacheError("task SIF cache receipt has an invalid schema")
    if value.get("schema") != CACHE_RECEIPT_SCHEMA:
        raise TaskSIFCacheError("task SIF cache receipt schema is unsupported")
    if value.get("content_sha256") != expected_sha256:
        raise TaskSIFCacheError("task SIF cache receipt digest does not match its key")
    if type(value.get("size")) is not int or value["size"] <= 0:
        raise TaskSIFCacheError("task SIF cache receipt size is invalid")
    if type(value.get("created_unix_ns")) is not int or value["created_unix_ns"] <= 0:
        raise TaskSIFCacheError("task SIF cache receipt timestamp is invalid")
    if value.get("credential_values_persisted") is not False:
        raise TaskSIFCacheError("task SIF cache receipt is not credential-safe")
    source = value.get("source")
    if not isinstance(source, dict) or set(source) != {"path", "path_sha256", "identity"}:
        raise TaskSIFCacheError("task SIF cache receipt source provenance is invalid")
    if not isinstance(source.get("path"), str) or not source["path"].startswith("/"):
        raise TaskSIFCacheError("task SIF cache receipt source path is invalid")
    if source.get("path_sha256") != _sha256(source["path"].encode("utf-8")):
        raise TaskSIFCacheError("task SIF cache receipt source path digest is invalid")
    for identity_name in ("identity",):
        identity = source.get(identity_name)
        if (
            not isinstance(identity, dict)
            or set(identity) != _IDENTITY_KEYS
            or not all(type(item) is int for item in identity.values())
        ):
            raise TaskSIFCacheError("task SIF cache receipt source identity is invalid")
    cached = value.get("cached_identity")
    if (
        not isinstance(cached, dict)
        or set(cached) != _IDENTITY_KEYS
        or not all(type(item) is int for item in cached.values())
    ):
        raise TaskSIFCacheError("task SIF cache receipt object identity is invalid")
    return value


def _load_published_object(final_dir: Path, expected_sha256: str) -> _PublishedObject:
    directory_stat = _validate_directory(final_dir, 0o500)
    image = final_dir / "task.sif"
    receipt_path = final_dir / "receipt.json"
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    cloexec = getattr(os, "O_CLOEXEC", 0)
    fd = os.open(image, os.O_RDONLY | nofollow | cloexec)
    try:
        image_lstat = image.lstat()
        value = os.fstat(fd)
        if (
            not stat.S_ISREG(value.st_mode)
            or value.st_uid != os.geteuid()
            or value.st_nlink != 1
            or _mode(value) != 0o400
            or (value.st_dev, value.st_ino) != (image_lstat.st_dev, image_lstat.st_ino)
        ):
            raise TaskSIFCacheError("cached task SIF failed private-file validation")
        object_identity = _identity(value)
    finally:
        os.close(fd)
    raw, receipt_stat = _read_private_file(receipt_path)
    try:
        decoded = json.loads(raw, object_pairs_hook=_strict_object)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TaskSIFCacheError("task SIF cache receipt is not valid JSON") from exc
    receipt = _validate_receipt(decoded, expected_sha256)
    if raw != _canonical_json(receipt) + b"\n":
        raise TaskSIFCacheError("task SIF cache receipt is not canonical")
    if receipt["size"] != object_identity["st_size"]:
        raise TaskSIFCacheError("task SIF cache receipt size does not match the object")
    if receipt["cached_identity"] != object_identity:
        raise TaskSIFCacheError("cached task SIF identity differs from its receipt")
    return _PublishedObject(
        path=image,
        receipt_path=receipt_path,
        receipt=receipt,
        receipt_bytes=raw,
        receipt_sha256=_sha256(raw),
        object_identity=object_identity,
        receipt_identity=_identity(receipt_stat),
        directory_identity=_identity(directory_stat),
    )


def _cleanup_temporary(path: Path) -> None:
    if not os.path.lexists(path):
        return
    value = path.lstat()
    if (
        not _POPULATE_TEMP_RE.fullmatch(path.name)
        or not stat.S_ISDIR(value.st_mode)
        or value.st_uid != os.geteuid()
    ):
        raise TaskSIFCacheError(f"unsafe stale task SIF cache temporary entry: {path}")
    os.chmod(path, 0o700)
    children = list(path.iterdir())
    for child in children:
        child_stat = child.lstat()
        if (
            child.name not in {"task.sif", "receipt.json"}
            or not stat.S_ISREG(child_stat.st_mode)
            or child_stat.st_uid != os.geteuid()
            or child_stat.st_nlink != 1
        ):
            raise TaskSIFCacheError(
                f"unsafe file in stale task SIF cache temporary directory: {child}"
            )
    for child in children:
        child.unlink()
    path.rmdir()


def _cleanup_stale_temporaries(layout: _CacheLayout) -> None:
    """Remove killed, unpublished populations while capacity EX is held."""
    entries = list(layout.temporary.iterdir())
    for entry in entries:
        _cleanup_temporary(entry)
    if entries:
        _fsync_directory(layout.temporary)


def _populate(
    layout: _CacheLayout, source: Path, expected_sha256: str, final_dir: Path,
) -> _PublishedObject:
    source_size = source.lstat().st_size
    temp_dir: Path | None = None
    source_fd = destination_fd = None
    try:
        # The caller holds the node-global capacity lock before the digest EX
        # lock.  This ordering is shared with aggregate prewarmers and avoids a
        # capacity<->digest deadlock with lazy workers.
        reserve = max(_MIN_FREE_SPACE_RESERVE_BYTES, source_size // 5)
        free = shutil.disk_usage(layout.temporary).free
        if free < source_size + reserve:
            raise TaskSIFCacheError(
                "insufficient node-local space for frozen task SIF cache population"
            )
        temp_dir = Path(tempfile.mkdtemp(
            prefix=f".populate-{expected_sha256}-{os.getpid()}-",
            dir=layout.temporary,
        ))
        os.chmod(temp_dir, 0o700)
        source_lstat = source.lstat()
        source_fd = os.open(
            source,
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0),
        )
        source_before = os.fstat(source_fd)
        if (
            not stat.S_ISREG(source_before.st_mode)
            or source_before.st_uid != os.geteuid()
            or source_before.st_nlink != 1
            or _mode(source_before) & 0o022
            or (source_before.st_dev, source_before.st_ino)
            != (source_lstat.st_dev, source_lstat.st_ino)
        ):
            raise TaskSIFCacheError(
                "--task-sif must be an owner-controlled, single-link regular file"
            )
        destination = temp_dir / "task.sif"
        destination_fd = os.open(
            destination,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL
            | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0),
            0o600,
        )
        digest = hashlib.sha256()
        copied = 0
        while True:
            chunk = os.read(source_fd, 1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
            copied += len(chunk)
            _write_all(destination_fd, chunk)
        os.fchmod(destination_fd, 0o400)
        os.fsync(destination_fd)
        source_after = os.fstat(source_fd)
        if _stable_facts(source_before) != _stable_facts(source_after):
            raise TaskSIFCacheError("source task SIF changed while it was staged")
        actual = digest.hexdigest()
        if actual != expected_sha256:
            raise TaskSIFCacheError(
                f"task SIF digest mismatch: expected {expected_sha256}, got {actual}"
            )
        cached_stat = os.fstat(destination_fd)
        if (
            not stat.S_ISREG(cached_stat.st_mode)
            or cached_stat.st_uid != os.geteuid()
            or cached_stat.st_nlink != 1
            or cached_stat.st_size != copied
            or _mode(cached_stat) != 0o400
        ):
            raise TaskSIFCacheError("cached task SIF failed private-file validation")
        object_identity = _identity(cached_stat)
        os.close(destination_fd)
        destination_fd = None
        os.close(source_fd)
        source_fd = None

        receipt = {
            "schema": CACHE_RECEIPT_SCHEMA,
            "content_sha256": expected_sha256,
            "size": copied,
            "source": {
                "path": str(source),
                "path_sha256": _sha256(str(source).encode("utf-8")),
                "identity": _identity(source_before),
            },
            "cached_identity": object_identity,
            "created_unix_ns": time.time_ns(),
            "credential_values_persisted": False,
        }
        _write_private_file(temp_dir / "receipt.json", _canonical_json(receipt) + b"\n")
        _fsync_directory(temp_dir)
        os.rename(temp_dir, final_dir)
        os.chmod(final_dir, 0o500)
        _fsync_directory(final_dir)
        _fsync_directory(layout.sha256_objects)
        published = _load_published_object(final_dir, expected_sha256)
        if published.object_identity != object_identity:
            raise TaskSIFCacheError("cached task SIF identity changed during publication")
        return published
    finally:
        for fd in (destination_fd, source_fd):
            if fd is not None:
                os.close(fd)
        if temp_dir is not None:
            _cleanup_temporary(temp_dir)


@dataclass
class TaskSIFCacheLease:
    path: Path
    source: Path
    content_sha256: str
    cache_root: Path
    cache_hit: bool
    size: int
    receipt_bytes: bytes = field(repr=False)
    receipt_sha256: str
    pre_identity: dict[str, int]
    receipt_identity: dict[str, int] = field(repr=False)
    directory_identity: dict[str, int] = field(repr=False)
    _lock_fd: int = field(repr=False)
    _closed: bool = field(default=False, init=False, repr=False)

    @property
    def pre_identity_sha256(self) -> str:
        return _identity_sha256(self.pre_identity)

    def verify_after_run(self) -> str:
        """Require the same published object and receipt after Harbor exits."""
        if self._closed:
            raise TaskSIFCacheError("task SIF cache lease is already closed")
        published = _load_published_object(self.path.parent, self.content_sha256)
        if published.path != self.path:
            raise TaskSIFCacheError("cached task SIF path changed during Harbor execution")
        if published.object_identity != self.pre_identity:
            raise TaskSIFCacheError("cached task SIF identity changed during Harbor execution")
        if published.receipt_identity != self.receipt_identity:
            raise TaskSIFCacheError("task SIF cache receipt identity changed during Harbor execution")
        if published.directory_identity != self.directory_identity:
            raise TaskSIFCacheError("task SIF cache directory identity changed during Harbor execution")
        if (
            published.receipt_sha256 != self.receipt_sha256
            or published.receipt_bytes != self.receipt_bytes
        ):
            raise TaskSIFCacheError("task SIF cache receipt changed during Harbor execution")
        return _identity_sha256(published.object_identity)

    def close(self) -> None:
        if self._closed:
            return
        try:
            fcntl.flock(self._lock_fd, fcntl.LOCK_UN)
        finally:
            os.close(self._lock_fd)
            self._closed = True

    def __enter__(self) -> "TaskSIFCacheLease":
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()


def validate_task_sif_cache_proof(
    proof: Mapping[str, Any],
    *,
    expected_sha256: str,
    expected_size: int,
    task_id: str,
    harness: str,
    model: str,
    source_path: str,
) -> None:
    """Recompute and cross-bind an embedded per-cell SIF cache proof.

    This is the shared acceptance primitive for campaign checkpoints and formal
    receipt promotion.  It intentionally needs no node-local cache object.
    """
    expected = (expected_sha256 or "").lower()
    if not _SHA256_RE.fullmatch(expected):
        raise TaskSIFCacheError("expected task SIF digest is invalid")
    if type(expected_size) is not int or expected_size <= 0:
        raise TaskSIFCacheError("expected task SIF size is invalid")
    if not isinstance(source_path, str) or not source_path.startswith("/"):
        raise TaskSIFCacheError("expected task SIF source path is invalid")
    expected_keys = {
        "schema", "content_sha256", "size",
        "cache_receipt_relative_path", "cache_receipt_file_sha256",
        "binding_relative_path", "binding_file_sha256",
        "cache_receipt", "binding", "pre_identity_sha256",
        "post_identity_sha256", "cache_hit", "portable_content_identity",
        "credential_values_persisted",
    }
    if not isinstance(proof, Mapping) or set(proof) != expected_keys:
        raise TaskSIFCacheError("incomplete task SIF cache proof")
    if proof.get("schema") != CACHE_PROOF_SCHEMA:
        raise TaskSIFCacheError("task SIF cache proof schema is invalid")
    if proof.get("content_sha256") != expected or proof.get("size") != expected_size:
        raise TaskSIFCacheError("task SIF cache proof content identity is invalid")
    for field_name in (
        "cache_receipt_file_sha256", "binding_file_sha256",
        "pre_identity_sha256", "post_identity_sha256",
    ):
        value = proof.get(field_name)
        if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
            raise TaskSIFCacheError(f"task SIF cache proof {field_name} is invalid")
    if proof["pre_identity_sha256"] != proof["post_identity_sha256"]:
        raise TaskSIFCacheError("task SIF cache identity drifted")
    for field_name in ("cache_receipt_relative_path", "binding_relative_path"):
        value = proof.get(field_name)
        candidate = Path(value) if isinstance(value, str) else Path("/")
        if (
            not isinstance(value, str)
            or not value
            or candidate.is_absolute()
            or ".." in candidate.parts
            or candidate.parts[:1] != ("pinned-image",)
            or candidate.as_posix() != value
        ):
            raise TaskSIFCacheError(f"task SIF cache proof {field_name} is invalid")
    if type(proof.get("cache_hit")) is not bool:
        raise TaskSIFCacheError("task SIF cache proof hit flag is invalid")
    if proof.get("portable_content_identity") is not True:
        raise TaskSIFCacheError("task SIF cache proof is not portable")
    if proof.get("credential_values_persisted") is not False:
        raise TaskSIFCacheError("task SIF cache proof is not credential-safe")

    raw_receipt = proof.get("cache_receipt")
    if not isinstance(raw_receipt, Mapping):
        raise TaskSIFCacheError("task SIF cache proof receipt is invalid")
    receipt = _validate_receipt(dict(raw_receipt), expected)
    if receipt["size"] != expected_size:
        raise TaskSIFCacheError("task SIF cache receipt size is inconsistent")
    source_identity = receipt["source"]["identity"]
    if (
        source_identity.get("st_nlink") != 1
        or source_identity.get("st_size") != expected_size
        or source_identity.get("mode", 0) & 0o022
        or source_identity.get("st_uid", -1) < 0
    ):
        raise TaskSIFCacheError("task SIF cache source identity is unsafe")
    cached_identity = receipt["cached_identity"]
    if (
        cached_identity.get("st_size") != expected_size
        or cached_identity.get("st_nlink") != 1
        or cached_identity.get("mode") != 0o400
        or _identity_sha256(cached_identity) != proof["pre_identity_sha256"]
    ):
        raise TaskSIFCacheError("task SIF cache receipt identity is invalid")
    receipt_bytes = _canonical_json(receipt) + b"\n"
    if _sha256(receipt_bytes) != proof["cache_receipt_file_sha256"]:
        raise TaskSIFCacheError("task SIF cache receipt digest is invalid")

    raw_binding = proof.get("binding")
    binding_keys = {
        "schema", "content_sha256", "size", "task_id", "harness", "model",
        "evaluator_pid", "cache_hit", "cache_path_observation",
        "source_path_sha256", "cache_receipt_file_sha256",
        "pre_identity_sha256", "credential_values_persisted",
    }
    if not isinstance(raw_binding, Mapping) or set(raw_binding) != binding_keys:
        raise TaskSIFCacheError("task SIF cache binding is invalid")
    binding = dict(raw_binding)
    if (
        binding.get("schema") != CACHE_BINDING_SCHEMA
        or binding.get("content_sha256") != expected
        or binding.get("size") != expected_size
        or binding.get("task_id") != task_id
        or binding.get("harness") != harness
        or binding.get("model") != model
        or type(binding.get("evaluator_pid")) is not int
        or binding["evaluator_pid"] <= 0
        or binding.get("cache_hit") is not proof["cache_hit"]
        or not isinstance(binding.get("cache_path_observation"), str)
        or not binding["cache_path_observation"].startswith("/")
        or binding.get("source_path_sha256") != _sha256(source_path.encode("utf-8"))
        or binding.get("cache_receipt_file_sha256")
        != proof["cache_receipt_file_sha256"]
        or binding.get("pre_identity_sha256") != proof["pre_identity_sha256"]
        or binding.get("credential_values_persisted") is not False
    ):
        raise TaskSIFCacheError("task SIF cache binding is inconsistent")
    binding_bytes = _canonical_json(binding) + b"\n"
    if _sha256(binding_bytes) != proof["binding_file_sha256"]:
        raise TaskSIFCacheError("task SIF cache binding digest is invalid")


def acquire_task_sif(
    path: str,
    expected_sha256: str,
    cache_root: str | os.PathLike[str] | None = None,
) -> TaskSIFCacheLease:
    """Acquire a shared lease on one verified content-addressed node object."""
    expected = (expected_sha256 or "").lower()
    if not _SHA256_RE.fullmatch(expected):
        raise TaskSIFCacheError(
            "--task-sif-sha256 must be exactly 64 hexadecimal characters"
        )
    source = _resolve_source(path)
    root = default_task_sif_cache_root() if cache_root is None else Path(cache_root)
    layout = _prepare_layout(root)
    final_dir = layout.sha256_objects / expected
    lock_fd = _open_private_lock(layout.locks / f"{expected}.lock")
    capacity_fd: int | None = None
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_SH)
        if os.path.lexists(final_dir):
            published = _load_published_object(final_dir, expected)
            cache_hit = True
        else:
            # All cold paths take capacity EX before digest EX.  A future
            # aggregate prewarmer can hold capacity once and invoke the same
            # internal publication path without lock-order inversion.
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
            capacity_fd = _open_private_lock(layout.locks / "capacity.lock")
            fcntl.flock(capacity_fd, fcntl.LOCK_EX)
            _cleanup_stale_temporaries(layout)
            fcntl.flock(lock_fd, fcntl.LOCK_EX)
            if os.path.lexists(final_dir):
                published = _load_published_object(final_dir, expected)
                cache_hit = True
            else:
                published = _populate(layout, source, expected, final_dir)
                cache_hit = False
            fcntl.flock(lock_fd, fcntl.LOCK_SH)
            # Bind the lease only after the EX->SH transition and a fresh
            # path/receipt validation under the retained shared lock.
            published = _load_published_object(final_dir, expected)
            fcntl.flock(capacity_fd, fcntl.LOCK_UN)
            os.close(capacity_fd)
            capacity_fd = None
        return TaskSIFCacheLease(
            path=published.path,
            source=source,
            content_sha256=expected,
            cache_root=root,
            cache_hit=cache_hit,
            size=published.object_identity["st_size"],
            receipt_bytes=published.receipt_bytes,
            receipt_sha256=published.receipt_sha256,
            pre_identity=published.object_identity,
            receipt_identity=published.receipt_identity,
            directory_identity=published.directory_identity,
            _lock_fd=lock_fd,
        )
    except Exception:
        if capacity_fd is not None:
            try:
                fcntl.flock(capacity_fd, fcntl.LOCK_UN)
            finally:
                os.close(capacity_fd)
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
        finally:
            os.close(lock_fd)
        raise


def persist_cell_binding(
    lease: TaskSIFCacheLease,
    run_root: str | os.PathLike[str],
    *,
    task_id: str,
    harness: str,
    model: str,
) -> dict[str, Any]:
    """Persist only portable, small receipt bytes in a durable cell work tree."""
    root = Path(run_root)
    pinned = root / "pinned-image"
    _create_private_directory(pinned)
    receipt_relative = Path("pinned-image") / "cache-receipt.json"
    binding_relative = Path("pinned-image") / "binding.json"
    _atomic_write_private_file(root / receipt_relative, lease.receipt_bytes)
    cache_receipt = json.loads(lease.receipt_bytes)
    binding = {
        "schema": CACHE_BINDING_SCHEMA,
        "content_sha256": lease.content_sha256,
        "size": lease.size,
        "task_id": task_id,
        "harness": harness,
        "model": model,
        "evaluator_pid": os.getpid(),
        "cache_hit": lease.cache_hit,
        "cache_path_observation": str(lease.path),
        "source_path_sha256": _sha256(str(lease.source).encode("utf-8")),
        "cache_receipt_file_sha256": lease.receipt_sha256,
        "pre_identity_sha256": lease.pre_identity_sha256,
        "credential_values_persisted": False,
    }
    binding_bytes = _canonical_json(binding) + b"\n"
    _atomic_write_private_file(root / binding_relative, binding_bytes)
    _fsync_directory(pinned)
    return {
        "schema": CACHE_PROOF_SCHEMA,
        "content_sha256": lease.content_sha256,
        "size": lease.size,
        "cache_receipt_relative_path": receipt_relative.as_posix(),
        "cache_receipt_file_sha256": lease.receipt_sha256,
        "binding_relative_path": binding_relative.as_posix(),
        "binding_file_sha256": _sha256(binding_bytes),
        "cache_receipt": cache_receipt,
        "binding": binding,
        "pre_identity_sha256": lease.pre_identity_sha256,
        "cache_hit": lease.cache_hit,
        "portable_content_identity": True,
        "credential_values_persisted": False,
    }
