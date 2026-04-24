"""FastMCP server exposing search, read, and list_files tools."""

from __future__ import annotations

import json
from typing import Any

from mcp.server.fastmcp import FastMCP

from jvm_mcp import jar
from jvm_mcp.resolver import (
    InvalidCoordinate,
    ResolvedJar,
    SourcesUnavailable,
    resolve,
)

mcp = FastMCP(
    "jvm-mcp",
    instructions=(
        "JVM Library Docs server. Provides search, read, and list_files tools "
        "for browsing JVM library source JARs by Maven coordinate "
        "(groupId:artifactId:version)."
    ),
)


def _envelope(
    status: str,
    coordinate: str,
    resolved: ResolvedJar | None = None,
    data: Any = None,
    message: str | None = None,
) -> str:
    result: dict[str, Any] = {"status": status, "coordinate": coordinate}
    if resolved:
        result["resolved_version"] = coordinate.split(":")[-1]
        result["jar_type"] = resolved.jar_type
        result["source"] = resolved.source
    if data is not None:
        result["data"] = data
    if message:
        result["message"] = message
    return json.dumps(result, indent=2)


async def _resolve_or_error(
    coordinate: str,
) -> tuple[ResolvedJar | None, str | None]:
    """Attempt resolution. Returns (jar, None) on success or (None, error_json)."""
    try:
        resolved = await resolve(coordinate)
        return resolved, None
    except InvalidCoordinate as e:
        return None, _envelope("invalid_coordinate", coordinate, message=str(e))
    except SourcesUnavailable as e:
        return None, _envelope("sources_unavailable", coordinate, message=str(e))
    except Exception as e:
        return None, _envelope("error", coordinate, message=str(e))


@mcp.tool(
    description=(
        "Search library sources for a regex pattern. Returns matching lines "
        "with surrounding context, grouped by file. "
        "Coordinate format: groupId:artifactId:version"
    )
)
async def search(
    coordinate: str,
    query: str,
    case_insensitive: bool = False,
    context_lines: int = 3,
) -> str:
    resolved, error = await _resolve_or_error(coordinate)
    if error:
        return error

    try:
        matches = jar.search(
            resolved.path,
            query,
            case_insensitive=case_insensitive,
            context_lines=context_lines,
        )
        formatted = jar.format_search_results(matches)
        return _envelope("ok", coordinate, resolved=resolved, data=formatted)
    except ValueError as e:
        return _envelope("error", coordinate, resolved=resolved, message=str(e))
    except Exception as e:
        return _envelope("error", coordinate, resolved=resolved, message=str(e))


@mcp.tool(
    description=(
        "Read a specific file from a library's source JAR. "
        "Coordinate format: groupId:artifactId:version. "
        "Path is the file path within the JAR (e.g., com/example/Foo.kt)."
    )
)
async def read(coordinate: str, path: str) -> str:
    resolved, error = await _resolve_or_error(coordinate)
    if error:
        return error

    try:
        content = jar.read_file(resolved.path, path)
        return _envelope("ok", coordinate, resolved=resolved, data=content)
    except FileNotFoundError:
        suggestions = jar.suggest_similar_paths(resolved.path, path)
        message = f"File '{path}' not found in JAR."
        if suggestions:
            message += f" Similar paths: {', '.join(suggestions)}"
        return _envelope(
            "file_not_found", coordinate, resolved=resolved, message=message
        )
    except Exception as e:
        return _envelope("error", coordinate, resolved=resolved, message=str(e))


@mcp.tool(
    description=(
        "List files in a library's source JAR. "
        "Coordinate format: groupId:artifactId:version. "
        "Optional prefix filters the listing (e.g., com/example/)."
    )
)
async def list_files(coordinate: str, prefix: str | None = None) -> str:
    resolved, error = await _resolve_or_error(coordinate)
    if error:
        return error

    try:
        files = jar.list_files(resolved.path, prefix=prefix)
        return _envelope("ok", coordinate, resolved=resolved, data=files)
    except Exception as e:
        return _envelope("error", coordinate, resolved=resolved, message=str(e))


def main():
    mcp.run(transport="stdio")
