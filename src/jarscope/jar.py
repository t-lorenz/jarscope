"""ZIP-based JAR reading: list, read, search operations."""

import concurrent.futures
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path

# Skip individual ZIP entries larger than 10 MB (uncompressed).
MAX_ENTRY_BYTES = 10 * 1024 * 1024

# Timeout for regex matching against a single file's contents.
_REGEX_TIMEOUT_SECONDS = 5


@dataclass
class SearchMatch:
    path: str
    line_number: int
    line: str
    context_before: list[str]
    context_after: list[str]


def list_files(
    jar_path: Path,
    prefix: str | None = None,
    max_entries: int = 10000,
) -> list[str]:
    """List file entries in the JAR, optionally filtered by path prefix."""
    with zipfile.ZipFile(jar_path, "r") as zf:
        names = [n for n in zf.namelist() if not n.endswith("/")]
        if prefix:
            normalized = prefix.rstrip("/")
            names = [
                n for n in names
                if n.startswith(normalized + "/") or n == normalized
            ]
        result = sorted(names)
        if len(result) > max_entries:
            return result[:max_entries]
        return result


def read_file(jar_path: Path, path: str) -> str:
    """Read a specific file from the JAR, decoded as UTF-8."""
    with zipfile.ZipFile(jar_path, "r") as zf:
        try:
            info = zf.getinfo(path)
        except KeyError:
            raise FileNotFoundError(f"File '{path}' not found in JAR")
        if info.file_size > MAX_ENTRY_BYTES:
            raise ValueError(
                f"File '{path}' is too large ({info.file_size} bytes, "
                f"limit {MAX_ENTRY_BYTES})"
            )
        data = zf.read(path)
        return data.decode("utf-8", errors="replace")


def _is_binary(data: bytes) -> bool:
    """Check if data appears to be binary (null byte in first 512 bytes)."""
    return b"\x00" in data[:512]


def _search_file(
    lines: list[str], pattern: re.Pattern, entry: str,
    context_lines: int, remaining: int,
) -> list[SearchMatch]:
    """Search a single file's lines. Runs in a thread for timeout safety."""
    matches: list[SearchMatch] = []
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
            if len(matches) >= remaining:
                break
    return matches


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
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)

    with zipfile.ZipFile(jar_path, "r") as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            if info.file_size > MAX_ENTRY_BYTES:
                continue

            data = zf.read(info.filename)
            if _is_binary(data):
                continue

            text = data.decode("utf-8", errors="replace")
            lines = text.splitlines()

            remaining = max_matches - len(matches)
            future = executor.submit(
                _search_file, lines, pattern, info.filename,
                context_lines, remaining,
            )
            try:
                file_matches = future.result(timeout=_REGEX_TIMEOUT_SECONDS)
            except concurrent.futures.TimeoutError:
                future.cancel()
                continue  # Skip this file, regex took too long.

            matches.extend(file_matches)
            if len(matches) >= max_matches:
                break

    executor.shutdown(wait=False)
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
