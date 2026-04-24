"""JAR resolution: Gradle cache -> Maven local -> Maven Central."""

from __future__ import annotations

import glob
import os
from dataclasses import dataclass
from pathlib import Path

import httpx

from jvm_mcp.cache import is_cached, jar_cache_path, store


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
            return ResolvedJar(path=cache_path, source="maven_central", jar_type=jar_type)

        filename = f"{artifact_id}-{version}-{classifier}.jar"
        url = f"{base_url}/{filename}"
        async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
            response = await client.get(url)
            if response.status_code == 200:
                store(cache_path, response.content)
                return ResolvedJar(
                    path=cache_path, source="maven_central", jar_type=jar_type
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
