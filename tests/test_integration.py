"""Integration tests that hit Maven Central. Run with: pytest -m integration"""

import json

import pytest

from jarscope.server import jar_list, jar_read, jar_search

pytestmark = pytest.mark.integration

COORD = "org.jetbrains.kotlinx:kotlinx-serialization-json:1.6.0"


async def test_list_files():
    result = json.loads(await jar_list(COORD))
    assert result["status"] == "ok"
    assert len(result["data"]) > 0
    assert result["jar_type"] in ("sources", "javadoc")
    assert result["source"] in ("gradle_cache", "maven_local", "maven_central")


async def test_search():
    result = json.loads(await jar_search(COORD, "class Json"))
    assert result["status"] == "ok"
    assert "Json" in result["data"]


async def test_read():
    files_result = json.loads(await jar_list(COORD))
    first_kt = next(f for f in files_result["data"] if f.endswith(".kt"))
    result = json.loads(await jar_read(COORD, first_kt))
    assert result["status"] == "ok"
    assert len(result["data"]) > 0


async def test_invalid_coordinate():
    result = json.loads(await jar_list("bad"))
    assert result["status"] == "invalid_coordinate"


async def test_file_not_found():
    result = json.loads(await jar_read(COORD, "nonexistent.kt"))
    assert result["status"] == "file_not_found"
