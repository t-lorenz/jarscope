"""JAR resolution: Gradle cache -> Maven local -> Maven Central."""

from __future__ import annotations

import asyncio
import glob
import io
import os
import re as _re
import zipfile
from dataclasses import dataclass
from pathlib import Path

import httpx

from jarscope.cache import cache_dir, is_cached, jar_cache_path, store

# Maven coordinates contain only alphanumeric, dots, hyphens, underscores.
_COORD_PART_RE = _re.compile(r"^[A-Za-z0-9._-]+$")

# Total timeout for a single Maven Central download.
_DOWNLOAD_TIMEOUT_SECONDS = 60


@dataclass
class ResolvedJar:
    path: Path
    source: str   # "gradle_cache" | "maven_local" | "maven_central"
    jar_type: str  # "sources" | "javadoc"


class InvalidCoordinate(Exception):
    pass


class SourcesUnavailable(Exception):
    pass


def parse_coordinate(coordinate: str) -> tuple[str, str, str]:
    """Parse 'groupId:artifactId:version' into components."""
    parts = coordinate.split(":")
    if len(parts) != 3 or not all(parts):
        raise InvalidCoordinate(
            f"Invalid coordinate '{coordinate}'. "
            "Expected format: groupId:artifactId:version"
        )
    for part in parts:
        if not _COORD_PART_RE.match(part):
            raise InvalidCoordinate(
                f"Invalid character in coordinate: {part!r}. "
                "Only alphanumeric, dots, hyphens, and underscores are allowed."
            )
    return parts[0], parts[1], parts[2]


def _find_in_gradle_cache(
    group_id: str, artifact_id: str, version: str
) -> ResolvedJar | None:
    """Search ~/.gradle/caches/modules-2/files-2.1/{groupId}/{artifactId}/{version}/."""
    gradle_base = Path.home() / ".gradle" / "caches" / "modules-2" / "files-2.1"
    version_dir = gradle_base / group_id / artifact_id / version
    if not version_dir.is_dir():
        return None

    for classifier, jar_type in [("sources", "sources"), ("javadoc", "javadoc")]:
        pattern = str(version_dir / "*" / f"*-{classifier}.jar")
        matches = glob.glob(pattern)
        if matches:
            return ResolvedJar(path=Path(matches[0]), source="gradle_cache", jar_type=jar_type)
    return None


def _find_in_maven_local(
    group_id: str, artifact_id: str, version: str
) -> ResolvedJar | None:
    """Search ~/.m2/repository/{group/path}/{artifactId}/{version}/."""
    group_path = group_id.replace(".", os.sep)
    maven_base = Path.home() / ".m2" / "repository"
    version_dir = maven_base / group_path / artifact_id / version

    for classifier, jar_type in [("sources", "sources"), ("javadoc", "javadoc")]:
        jar_path = version_dir / f"{artifact_id}-{version}-{classifier}.jar"
        if jar_path.is_file():
            return ResolvedJar(path=jar_path, source="maven_local", jar_type=jar_type)
    return None


async def _fetch_from_maven_central(
    group_id: str, artifact_id: str, version: str
) -> ResolvedJar:
    """Download from Maven Central. Tries sources, then javadoc."""
    group_path = group_id.replace(".", "/")
    base_url = f"https://repo1.maven.org/maven2/{group_path}/{artifact_id}/{version}"

    for classifier, jar_type in [("sources", "sources"), ("javadoc", "javadoc")]:
        cache_path = jar_cache_path(group_id, artifact_id, version, classifier)
        if is_cached(cache_path, version):
            # Verify cached file is still a valid ZIP.
            try:
                zipfile.ZipFile(cache_path).close()
            except (zipfile.BadZipFile, OSError):
                cache_path.unlink(missing_ok=True)
            else:
                return ResolvedJar(
                    path=cache_path, source="maven_central", jar_type=jar_type
                )

        filename = f"{artifact_id}-{version}-{classifier}.jar"
        url = f"{base_url}/{filename}"
        try:
            timeout = httpx.Timeout(connect=10.0, read=30.0, write=10.0, pool=5.0)
            async with httpx.AsyncClient(
                follow_redirects=True, timeout=timeout
            ) as client:
                response = await asyncio.wait_for(
                    client.get(url), timeout=_DOWNLOAD_TIMEOUT_SECONDS
                )
                if response.status_code == 200:
                    # Validate it's actually a ZIP before caching.
                    try:
                        zipfile.ZipFile(io.BytesIO(response.content)).close()
                    except zipfile.BadZipFile:
                        raise SourcesUnavailable(
                            f"Downloaded file from {url} is not a valid JAR"
                        )
                    # Verify cache path doesn't escape the cache directory.
                    expected_root = str(cache_dir().resolve())
                    cache_path.parent.mkdir(parents=True, exist_ok=True)
                    if not str(cache_path.resolve()).startswith(expected_root):
                        raise InvalidCoordinate("Path traversal detected")
                    store(cache_path, response.content)
                    return ResolvedJar(
                        path=cache_path, source="maven_central", jar_type=jar_type
                    )
                elif response.status_code in (404, 403):
                    continue  # Try next classifier.
                else:
                    raise SourcesUnavailable(
                        f"Maven Central returned HTTP {response.status_code} for {url}"
                    )
        except (httpx.TransportError, httpx.TooManyRedirects) as e:
            raise SourcesUnavailable(
                f"Network error fetching {url}: {e}"
            )
        except asyncio.TimeoutError:
            raise SourcesUnavailable(
                f"Download timed out after {_DOWNLOAD_TIMEOUT_SECONDS}s for {url}"
            )

    raise SourcesUnavailable(
        f"Neither sources nor javadoc JAR available on Maven Central "
        f"for {group_id}:{artifact_id}:{version}"
    )


async def resolve(coordinate: str) -> ResolvedJar:
    """Resolve a Maven coordinate to a local JAR path.

    Tries: Gradle cache -> Maven local -> Maven Central.
    """
    group_id, artifact_id, version = parse_coordinate(coordinate)

    result = _find_in_gradle_cache(group_id, artifact_id, version)
    if result:
        return result

    result = _find_in_maven_local(group_id, artifact_id, version)
    if result:
        return result

    return await _fetch_from_maven_central(group_id, artifact_id, version)
