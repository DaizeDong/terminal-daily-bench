#!/usr/bin/env python3
"""Read-only static CI: validate published package bytes, never execute them."""
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import stat


def verify(root):
    manifests = sorted((root / "publication-manifests").glob("*/*.json"))
    if not manifests:
        raise ValueError("no public publication manifest")
    for path in manifests:
        value = json.loads(path.read_bytes())
        if value["schema"] != "td-public-package-inventory/v1":
            raise ValueError("wrong inventory schema")
        package_path = value["package_path"]
        if not re.fullmatch(r"tasks/archive/[A-Za-z0-9][A-Za-z0-9._-]{0,127}", package_path):
            raise ValueError("invalid package path")
        package = root / package_path
        actual = []
        for file in sorted(package.rglob("*")):
            mode = file.lstat().st_mode
            if stat.S_ISLNK(mode):
                raise ValueError("symlink in package")
            if stat.S_ISDIR(mode):
                continue
            if not stat.S_ISREG(mode):
                raise ValueError("special file in package")
            rel = file.relative_to(package).as_posix()
            if PurePosixPath(rel).parts[0] not in {"task.toml", "instruction.md", "README.md", "environment", "tests"}:
                raise ValueError("private path in public package")
            actual.append({"path": rel, "sha256": hashlib.sha256(file.read_bytes()).hexdigest(), "size": file.stat().st_size})
        if actual != value["files"] or not actual:
            raise ValueError("public package differs from exact inventory")
        native_hash = hashlib.sha256()
        for row in actual:
            native_hash.update((row["path"] + "\0" + row["sha256"] + "\n").encode())
        if native_hash.hexdigest() != value["content_hash"]:
            raise ValueError("native package content hash mismatch")
    return len(manifests)


if __name__ == "__main__":
    print("Verified", verify(Path.cwd()), "public package inventories without executing task code")
