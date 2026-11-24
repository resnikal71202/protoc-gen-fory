"""scripts/ci/build_version.py and scripts/ci/changelog.py."""

from __future__ import annotations

import importlib.util
import subprocess
import re
import sys
from pathlib import Path
from types import ModuleType

import pytest

import helpers

SCRIPTS = helpers.REPO / "scripts" / "ci"


def _load(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


build_version = _load("build_version")
changelog = _load("changelog")


class TestBuildVersion:
    def test_main_keeps_the_base_version(self) -> None:
        assert build_version.build_version("0.1.0", "main", "42") == "0.1.0"

    @pytest.mark.parametrize(
        ("branch", "expected"),
        [
            ("feature-x", "0.1.0+feature.x.42"),
            ("feature/Foo_bar", "0.1.0+feature.foo.bar.42"),
            ("dependabot/github_actions/actions-abc", "0.1.0+dependabot.github.actions.actions.abc.42"),
            ("--weird--", "0.1.0+weird.42"),
        ],
    )
    def test_branches_get_a_local_label(self, branch: str, expected: str) -> None:
        assert build_version.build_version("0.1.0", branch, "42") == expected

    @pytest.mark.parametrize(
        ("base", "branch", "number"),
        [("0.1.0+x", "b", "1"), ("0.1.0", "b", "x1"), ("0.1.0", "///", "1")],
    )
    def test_invalid_input(self, base: str, branch: str, number: str) -> None:
        with pytest.raises(ValueError):
            build_version.build_version(base, branch, number)

    def test_result_is_accepted_by_uv(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text('[project]\nname = "x"\nversion = "0.1.0"\n')
        version = build_version.build_version("0.1.0", "feature/Foo-bar", "7")
        proc = subprocess.run(
            ["uv", "version", version, "--frozen"],
            cwd=tmp_path, capture_output=True, text=True, check=False,
        )
        if proc.returncode != 0 and "unexpected argument" in proc.stderr:
            pytest.skip("uv too old for `uv version <value>`")
        assert proc.returncode == 0, proc.stderr
        assert f'version = "{version}"' in (tmp_path / "pyproject.toml").read_text()


TEXT = """\
# Changelog

## [Unreleased]

- next thing

## [0.2.0] - 2026-12-01

### Fixed

- a bug

## [0.1.0] - Unreleased

- first

[0.2.0]: https://example.com/0.2.0
[0.1.0]: https://example.com/0.1.0
"""


class TestChangelog:
    def test_sections(self) -> None:
        found = changelog.sections(TEXT)
        assert found["0.2.0"] == ("2026-12-01", "### Fixed\n\n- a bug")
        assert found["0.1.0"] == ("Unreleased", "- first")
        assert found["Unreleased"] == (None, "- next thing")

    def test_check_accepts_undated_and_local_versions(self) -> None:
        assert changelog.section(TEXT, "0.1.0+feature.x.3", require_date=False) == "- first"

    def test_release_needs_a_date(self) -> None:
        assert changelog.section(TEXT, "0.2.0", require_date=True) == "### Fixed\n\n- a bug"
        with pytest.raises(changelog.ChangelogError, match="needs a release date"):
            changelog.section(TEXT, "0.1.0", require_date=True)

    def test_missing_section(self) -> None:
        with pytest.raises(changelog.ChangelogError, match=r"no section '## \[9.9.9\]'"):
            changelog.section(TEXT, "9.9.9", require_date=False)

    def test_repo_changelog_covers_the_project_version(self) -> None:
        # No tomllib: it needs Python 3.11, CI also runs 3.10.
        match = re.search(r'^version = "([^"]+)"', (helpers.REPO / "pyproject.toml").read_text(), re.M)
        assert match
        changelog.section(changelog.CHANGELOG.read_text(), match.group(1), require_date=False)

    def test_cli(self) -> None:
        script = str(SCRIPTS / "changelog.py")
        ok = subprocess.run([sys.executable, "-I", script, "check", "0.1.0"], capture_output=True, text=True)
        assert ok.returncode == 0, ok.stdout
        bad = subprocess.run([sys.executable, "-I", script, "check", "9.9.9"], capture_output=True, text=True)
        assert bad.returncode == 1 and "::error file=CHANGELOG.md::" in bad.stdout
