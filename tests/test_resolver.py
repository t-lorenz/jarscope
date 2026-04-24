import pytest
from jvm_mcp.resolver import parse_coordinate, InvalidCoordinate


class TestParseCoordinate:
    def test_valid(self):
        g, a, v = parse_coordinate("org.example:lib:1.0")
        assert (g, a, v) == ("org.example", "lib", "1.0")

    def test_snapshot_version(self):
        _, _, v = parse_coordinate("org.example:lib:1.0-SNAPSHOT")
        assert v == "1.0-SNAPSHOT"

    def test_too_few_parts(self):
        with pytest.raises(InvalidCoordinate):
            parse_coordinate("org.example:lib")

    def test_too_many_parts(self):
        with pytest.raises(InvalidCoordinate):
            parse_coordinate("org.example:lib:1.0:extra")

    def test_empty_part(self):
        with pytest.raises(InvalidCoordinate):
            parse_coordinate("org.example::1.0")

    def test_empty_string(self):
        with pytest.raises(InvalidCoordinate):
            parse_coordinate("")

    def test_single_word(self):
        with pytest.raises(InvalidCoordinate):
            parse_coordinate("just-a-string")
