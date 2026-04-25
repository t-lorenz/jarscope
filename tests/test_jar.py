import io
import zipfile
from pathlib import Path

import pytest

from jarscope.jar import (
    _is_binary,
    format_search_results,
    list_files,
    read_file,
    search,
    suggest_similar_paths,
)


@pytest.fixture
def sample_jar(tmp_path) -> Path:
    """Create a synthetic JAR with known contents."""
    jar_path = tmp_path / "test.jar"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(
            "com/example/Foo.kt",
            "package com.example\n\nclass Foo {\n    fun bar() = 42\n}\n",
        )
        zf.writestr(
            "com/example/Bar.kt",
            'package com.example\n\nclass Bar {\n    fun baz() = "hello"\n}\n',
        )
        zf.writestr(
            "com/example/util/Helper.kt",
            "package com.example.util\n\nobject Helper {\n    fun help() = true\n}\n",
        )
        zf.writestr("META-INF/MANIFEST.MF", "Manifest-Version: 1.0\n")
        zf.writestr("com/example/data.bin", b"\x00\x01\x02" + b"\x00" * 100)
    jar_path.write_bytes(buf.getvalue())
    return jar_path


class TestListFiles:
    def test_list_all(self, sample_jar):
        files = list_files(sample_jar)
        assert "com/example/Foo.kt" in files
        assert "com/example/Bar.kt" in files
        assert "com/example/util/Helper.kt" in files
        assert len(files) == 5

    def test_prefix(self, sample_jar):
        files = list_files(sample_jar, prefix="com/example/util")
        assert files == ["com/example/util/Helper.kt"]

    def test_prefix_trailing_slash(self, sample_jar):
        files = list_files(sample_jar, prefix="com/example/util/")
        assert files == ["com/example/util/Helper.kt"]

    def test_prefix_no_match(self, sample_jar):
        files = list_files(sample_jar, prefix="nonexistent")
        assert files == []


class TestReadFile:
    def test_read_existing(self, sample_jar):
        content = read_file(sample_jar, "com/example/Foo.kt")
        assert "class Foo" in content

    def test_read_nonexistent(self, sample_jar):
        with pytest.raises(FileNotFoundError):
            read_file(sample_jar, "nonexistent.kt")


class TestSearch:
    def test_basic(self, sample_jar):
        matches = search(sample_jar, "class")
        assert len(matches) >= 2

    def test_case_insensitive(self, sample_jar):
        matches = search(sample_jar, "CLASS", case_insensitive=True)
        assert len(matches) >= 2

    def test_case_sensitive_no_match(self, sample_jar):
        matches = search(sample_jar, "CLASS", case_insensitive=False)
        assert len(matches) == 0

    def test_context_lines(self, sample_jar):
        matches = search(sample_jar, "fun bar", context_lines=1)
        assert len(matches) == 1
        assert len(matches[0].context_before) > 0
        assert len(matches[0].context_after) > 0

    def test_invalid_regex(self, sample_jar):
        with pytest.raises(ValueError):
            search(sample_jar, "[invalid")

    def test_skips_binary(self, sample_jar):
        matches = search(sample_jar, ".*", case_insensitive=False)
        paths = {m.path for m in matches}
        assert "com/example/data.bin" not in paths

    def test_max_matches(self, sample_jar):
        matches = search(sample_jar, ".", max_matches=2)
        assert len(matches) == 2


class TestFormatSearchResults:
    def test_no_matches(self):
        assert format_search_results([]) == "No matches found."

    def test_truncation_notice(self, sample_jar):
        matches = search(sample_jar, ".", max_matches=2)
        formatted = format_search_results(matches, max_matches=2)
        assert "(truncated at 2 matches)" in formatted


class TestIsBinary:
    def test_text(self):
        assert not _is_binary(b"hello world")

    def test_binary(self):
        assert _is_binary(b"\x00\x01\x02")

    def test_empty(self):
        assert not _is_binary(b"")


class TestSuggestSimilarPaths:
    def test_by_filename(self, sample_jar):
        suggestions = suggest_similar_paths(sample_jar, "wrong/path/Foo.kt")
        assert "com/example/Foo.kt" in suggestions

    def test_no_match(self, sample_jar):
        suggestions = suggest_similar_paths(sample_jar, "ZZZ.xyz")
        assert suggestions == []
