"""ZIP-based JAR reading: list, read, search operations."""

from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass
from pathlib import Path


@dataclass
class SearchMatch:
    path: str
    line_number: int
    line: str
    context_before: list[str]
    context_after: list[str]


def list_files(jar_path: Path, prefix: str | None = None) -> list[str]:
    """List file entries in the JAR, optionally filtered by path prefix."""
    with zipfile.ZipFile(jar_path, "r") as zf:
        names = [n for n in zf.namelist() if not n.endswith("/")]
        if prefix:
            normalized = prefix.rstrip("/")
            names = [
                n for n in names
                if n.startswith(normalized + "/") or n == normalized
            ]
        return sorted(names)


def read_file(jar_path: Path, path: str) -> str:
    """Read a specific file from the JAR, decoded as UTF-8."""
    with zipfile.ZipFile(jar_path, "r") as zf:
        try:
            data = zf.read(path)
        except KeyError:
            raise FileNotFoundError(f"File '{path}' not found in JAR")
        return data.decode("utf-8", errors="replace")


def _is_binary(data: bytes) -> bool:
    """Check if data appears to be binary (null byte in first 512 bytes)."""
    return b"\x00" in data[:512]


def search(
    jar_path: Path,
    query: str,
    case_insensitive: bool = False,
    context_lines: int = 3,
    max_matches: int = 500,
) -> list[SearchMatch]:
    """Search all text files in the JAR for a regex pattern."""
    flags = re.IGNORECASE if case_insensitive else 0
    try:
        pattern = re.compile(query, flags)
    except re.error as e:
        raise ValueError(f"Invalid regex pattern: {e}")

    matches: list[SearchMatch] = []

    with zipfile.ZipFile(jar_path, "r") as zf:
        for entry in zf.namelist():
            if entry.endswith("/"):
                continue

            data = zf.read(entry)
            if _is_binary(data):
                continue

            text = data.decode("utf-8", errors="replace")
            lines = text.splitlines()
            for i, line in enumerate(lines):
                if pattern.search(line):
                    start = max(0, i - context_lines)
                    end = min(len(lines), i + context_lines + 1)
                    matches.append(SearchMatch(
                        path=entry,
                        line_number=i + 1,
                        line=line,
                        context_before=lines[start:i],
                        context_after=lines[i + 1:end],
                    ))
                    if len(matches) >= max_matches:
                        return matches

    return matches


def format_search_results(matches: list[SearchMatch], max_matches: int = 500) -> str:
    """Format search matches into ripgrep-style grouped output."""
    if not matches:
        return "No matches found."

    by_file: dict[str, list[SearchMatch]] = {}
    for m in matches:
        by_file.setdefault(m.path, []).append(m)

    parts: list[str] = []
    for path, file_matches in by_file.items():
        parts.append(f"=== {path} ===")
        for m in file_matches:
            for ctx_line in m.context_before:
                parts.append(f"  {ctx_line}")
            parts.append(f"{path}:{m.line_number}: {m.line}")
            for ctx_line in m.context_after:
                parts.append(f"  {ctx_line}")
            parts.append("")

    if len(matches) >= max_matches:
        parts.append(f"(truncated at {max_matches} matches)")

    return "\n".join(parts)


def suggest_similar_paths(
    jar_path: Path, target: str, max_suggestions: int = 5
) -> list[str]:
    """Suggest similar paths when a file is not found."""
    target_name = target.rsplit("/", 1)[-1] if "/" in target else target
    all_files = list_files(jar_path)
    suggestions = [
        f for f in all_files
        if f.rsplit("/", 1)[-1] == target_name or target_name in f
    ]
    return suggestions[:max_suggestions]
