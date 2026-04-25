"""Download cache for JARs fetched from Maven Central."""

from __future__ import annotations

import os
import tempfile
import time
from pathlib import Path

import platformdirs

SNAPSHOT_TTL_SECONDS = 3600  # 1 hour


def cache_dir() -> Path:
    return Path(platformdirs.user_cache_dir("jarscope"))


def jar_cache_path(
    group_id: str, artifact_id: str, version: str, classifier: str = "sources"
) -> Path:
    """Maven-layout path under the cache directory."""
    group_path = group_id.replace(".", os.sep)
    filename = f"{artifact_id}-{version}-{classifier}.jar"
    return cache_dir() / group_path / artifact_id / version / filename


def is_cached(path: Path, version: str) -> bool:
    """Check if a cached file exists and is fresh (SNAPSHOT TTL applies)."""
    if not path.is_file():
        return False
    if version.endswith("-SNAPSHOT"):
        age = time.time() - path.stat().st_mtime
        return age < SNAPSHOT_TTL_SECONDS
    return True


def store(path: Path, data: bytes) -> None:
    """Atomically write data to path (temp file + os.replace)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path_str: str | None = None
    try:
        fd, tmp_path_str = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.replace(tmp_path_str, path)
    except BaseException:
        if tmp_path_str and os.path.exists(tmp_path_str):
            os.unlink(tmp_path_str)
        raise
