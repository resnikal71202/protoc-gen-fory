"""Golden test: `buf generate` with the plugin == foryc on the same schema, byte for byte."""

from __future__ import annotations

from pathlib import Path

import pytest

import helpers

pytestmark = pytest.mark.needs_buf


def _diff(expected: dict[str, str], actual: dict[str, str]) -> str:
    import difflib

    lines = [f"foryc files:  {sorted(expected)}", f"plugin files: {sorted(actual)}"]
    for path in sorted(set(expected) | set(actual)):
        if expected.get(path) != actual.get(path):
            lines += difflib.unified_diff(
                (expected.get(path) or "").splitlines(),
                (actual.get(path) or "").splitlines(),
                f"foryc/{path}",
                f"plugin/{path}",
                lineterm="",
            )
    return "\n".join(lines[:200])


@pytest.mark.parametrize("lang", helpers.LANGUAGES)
@pytest.mark.parametrize("fixture", helpers.FIXTURE_NAMES)
def test_plugin_output_equals_foryc(tmp_path: Path, fixture: str, lang: str) -> None:
    expected = helpers.run_foryc(helpers.FIXTURES / fixture, lang, tmp_path / "foryc")
    actual = helpers.run_buf(helpers.FIXTURES / fixture, lang, tmp_path / "buf")
    assert expected, "foryc generated nothing"
    assert actual == expected, _diff(expected, actual)


@pytest.mark.parametrize("lang", helpers.LANGUAGES)
def test_directory_strategy_gives_the_same_files(tmp_path: Path, lang: str) -> None:
    """buf's default strategy (one request per directory) must not change the output."""
    fixture = helpers.FIXTURES / "multi"
    expected = helpers.run_buf(fixture, lang, tmp_path / "all", strategy="all")
    actual = helpers.run_buf(fixture, lang, tmp_path / "directory", strategy="directory")
    assert actual == expected, _diff(expected, actual)


def test_go_nested_type_style_is_passed_through(tmp_path: Path) -> None:
    fixture = helpers.FIXTURES / "nesting"
    expected = helpers.run_foryc(
        fixture, "go", tmp_path / "foryc", ["--go_nested_type_style", "camelcase"]
    )
    actual = helpers.run_buf(fixture, "go", tmp_path / "buf", opts=["go_nested_type_style=camelcase"])
    assert actual == expected, _diff(expected, actual)
    default = helpers.run_buf(fixture, "go", tmp_path / "default")
    assert default != actual
