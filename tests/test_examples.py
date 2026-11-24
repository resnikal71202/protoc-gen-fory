"""examples/ works as documented in the README."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

import helpers
from protoc_gen_fory.__main__ import options_proto

pytestmark = pytest.mark.needs_buf


def test_example_project_lints_and_generates(tmp_path: Path) -> None:
    project = tmp_path / "example"
    shutil.copytree(helpers.REPO / "examples", project)
    # README step: protoc-gen-fory --options-proto > proto/fory/options.proto
    (project / "proto" / "fory").mkdir()
    (project / "proto" / "fory" / "options.proto").write_text(options_proto())

    env = dict(os.environ, PATH=f"{Path(sys.executable).parent}{os.pathsep}{os.environ['PATH']}")
    for command in (["buf", "format", "--diff", "--exit-code"], ["buf", "lint"], ["buf", "generate"]):
        proc = subprocess.run(command, cwd=project, env=env, capture_output=True, text=True, check=False)
        assert proc.returncode == 0, f"{' '.join(command)}:\n{proc.stdout}{proc.stderr}"

    generated = sorted(p.relative_to(project / "gen").as_posix() for p in (project / "gen").rglob("*") if p.is_file())
    assert generated == [
        "go/acme/shop/v1/acme_shop_v1.go",
        "java/com/acme/acme/shop/v1/Cart.java",
        "java/com/acme/acme/shop/v1/Product.java",
        "java/com/acme/acme/shop/v1/V1ForyModule.java",
        "javascript/shop.ts",
        "python/acme_shop_v1.py",
        "rust/acme_shop_v1.rs",
    ]
    # Managed mode override reached the Fory code.
    assert "package com.acme.acme.shop.v1;" in (project / "gen/java/com/acme/acme/shop/v1/Cart.java").read_text()


def test_shipped_options_proto_matches_the_module() -> None:
    assert options_proto() == helpers.OPTIONS_PROTO.read_text()
