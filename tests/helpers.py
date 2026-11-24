"""Run the same schema through foryc directly and through buf + protoc-gen-fory."""

from __future__ import annotations

import contextlib
import dataclasses
import io
import re
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path
from typing import Any

from fory_compiler import cli as fory_cli
from fory_compiler.frontend.proto.lexer import Lexer
from fory_compiler.frontend.proto.parser import Parser

# Registers the fory extensions before any descriptor is parsed.
from protoc_gen_fory import options as _options  # noqa: F401
from google.protobuf import descriptor_pb2

REPO = Path(__file__).resolve().parent.parent
FIXTURES = REPO / "tests" / "fixtures"
OPTIONS_PROTO = REPO / "proto" / "fory" / "options.proto"

LANGUAGES = ("java", "python", "go", "rust", "javascript")
FIXTURE_NAMES = sorted(p.name for p in FIXTURES.iterdir() if p.is_dir())

_NEW_OPTION = re.compile(r"\(fory\.(?:file|message|field|enum)\)")
_OPTIONS_IMPORT = re.compile(r'^[ \t]*import[ \t]+"fory/options\.proto"\s*;[^\n]*\n', re.MULTILINE)


_PACKAGE = re.compile(r"^\s*package\s+([\w.]+)\s*;", re.MULTILINE)


def fixture_packages(fixture: Path) -> list[str]:
    return sorted({m.group(1) for p in proto_files(fixture) for m in _PACKAGE.finditer(p.read_text())})


def to_foryc_syntax(source: str, packages: list[str] | None = None) -> str:
    """Rewrite a buf-compatible fixture the way a foryc user would write it.

    * ``(fory.field).ref`` -> ``(fory).ref``; the options import becomes an
      empty line (line numbers stay the same), since foryc cannot parse ``extend``.
    * Package prefixes of type references are dropped (``demo.common.Money`` ->
      ``Money``): foryc resolves types without packages, and qualified names
      produce broken code in several generators.
    """
    out = _NEW_OPTION.sub("(fory)", _OPTIONS_IMPORT.sub("\n", source))
    lines = []
    for line in out.splitlines(keepends=True):
        if not _PACKAGE.match(line):
            for package in sorted(packages or [], key=len, reverse=True):
                line = re.sub(rf"(?<![\w.\"]){re.escape(package)}\.(?=[A-Za-z_])", "", line)
        lines.append(line)
    return "".join(lines)


def proto_files(root: Path) -> list[Path]:
    return sorted(root.rglob("*.proto"))


def read_tree(root: Path) -> dict[str, str]:
    return {
        p.relative_to(root).as_posix(): p.read_text()
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


# --- foryc -------------------------------------------------------------------


def write_foryc_sources(fixture: Path, dest: Path) -> list[Path]:
    packages = fixture_packages(fixture)
    for path in proto_files(fixture):
        target = dest / path.relative_to(fixture)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(to_foryc_syntax(path.read_text(), packages))
    return proto_files(dest)


def run_foryc(
    fixture: Path, lang: str, work: Path, extra_args: list[str] | None = None, check: bool = True
) -> dict[str, str] | tuple[int, str]:
    """foryc on the fixture (converted to foryc syntax); returns the generated tree."""
    src = work / "foryc-src"
    out = work / "foryc-out"
    files = write_foryc_sources(fixture, src)
    out.mkdir(parents=True)
    args = [str(p) for p in files]
    args += ["-I", str(src), f"--{lang}_out", str(out), *(extra_args or [])]
    log = io.StringIO()
    with contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
        code = fory_cli.main(args)
    if not check:
        return code, log.getvalue()
    if code != 0:
        raise AssertionError(f"foryc failed:\n{log.getvalue()}")
    return read_tree(out)


def foryc_ast(source: str, filename: str) -> Any:
    return Parser(Lexer(source, filename).tokenize(), filename).parse()


# --- buf ---------------------------------------------------------------------


def buf_available() -> bool:
    return shutil.which("buf") is not None


def plugin_command() -> str:
    """Path of the protoc-gen-fory executable in the active environment."""
    exe = Path(sys.executable).parent / "protoc-gen-fory"
    if not exe.exists():
        raise AssertionError(f"{exe} missing; run `uv sync` first")
    return str(exe)


def prepare_buf_workspace(fixture: Path, work: Path) -> Path:
    """Copy the fixture and fory/options.proto into a buf workspace; returns the module dir."""
    module = work / "buf-src"
    shutil.copytree(fixture, module)
    (module / "fory").mkdir(exist_ok=True)
    shutil.copy(OPTIONS_PROTO, module / "fory" / "options.proto")
    (work / "buf.yaml").write_text("version: v2\nmodules:\n  - path: buf-src\n")
    return module


def buf_image(fixture: Path, work: Path) -> descriptor_pb2.FileDescriptorSet:
    """`buf build` of the fixture: all files incl. imports, with source info, in topological order."""
    prepare_buf_workspace(fixture, work)
    image = work / "image.binpb"
    proc = subprocess.run(
        ["buf", "build", "-o", str(image)], cwd=work, capture_output=True, text=True, check=False
    )
    if proc.returncode != 0:
        raise AssertionError(f"buf build failed:\n{proc.stderr}")
    return descriptor_pb2.FileDescriptorSet.FromString(image.read_bytes())


def run_buf(
    fixture: Path,
    lang: str,
    work: Path,
    opts: list[str] | None = None,
    strategy: str = "all",
    managed: str = "",
    check: bool = True,
    inputs_exclude: list[str] | None = None,
) -> Any:
    """buf generate with the local plugin; returns the generated tree (or the process if check=False)."""
    prepare_buf_workspace(fixture, work)
    opt_lines = "".join(f"\n      - {o}" for o in [f"lang={lang}", *(opts or [])])
    exclude = ", ".join(f"buf-src/{p}" for p in ["fory", *(inputs_exclude or [])])
    (work / "buf.gen.yaml").write_text(
        textwrap.dedent(
            f"""\
            version: v2
            inputs:
              - directory: buf-src
                exclude_paths: [{exclude}]
            plugins:
              - local: {plugin_command()}
                out: buf-out
                strategy: {strategy}
                opt:"""
        )
        + opt_lines
        + "\n"
        + managed
    )
    proc = subprocess.run(["buf", "generate"], cwd=work, capture_output=True, text=True, check=False)
    if not check:
        return proc
    if proc.returncode != 0:
        raise AssertionError(f"buf generate failed:\n{proc.stdout}{proc.stderr}")
    out = work / "buf-out"
    return read_tree(out) if out.exists() else {}


# --- AST comparison ----------------------------------------------------------


def ast_to_data(node: Any, positions: bool = True) -> Any:
    """Dataclass tree -> plain data, optionally without line/column."""
    if dataclasses.is_dataclass(node) and not isinstance(node, type):
        return {
            f.name: ast_to_data(getattr(node, f.name), positions)
            for f in dataclasses.fields(node)
            if f.name != "source_file" and (positions or f.name not in ("line", "column"))
        }
    if isinstance(node, list):
        return [ast_to_data(item, positions) for item in node]
    if isinstance(node, dict):
        return {key: ast_to_data(value, positions) for key, value in node.items()}
    return node
