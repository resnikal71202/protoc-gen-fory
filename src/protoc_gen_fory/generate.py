"""Run foryc's compile pipeline on schemas adapted from a CodeGeneratorRequest.

foryc's CLI does the per-file work: import merging, validation, generator
calls, Go output directories, output collision checks. The plugin reuses
that code as is and only swaps out the source of the schemas:

* Every adapted file gets an empty placeholder at ``<tmp>/src/<proto name>``,
  so foryc's path-based import resolution works like it does on real files.
* ``parse_idl_file`` (imported by name into the CLI and the generators) is
  replaced during the run by a resolver that translates the adapted AST
  instead of reading the placeholder.
* ``resolve_import_path`` is replaced too: buf import paths are relative to
  the module root, while foryc tries the importing file's directory first.
* Output is written to ``<tmp>/out`` and collected afterwards.

Only files in ``file_to_generate`` produce output; their dependencies are
marked as already generated.
"""

from __future__ import annotations

import contextlib
import copy
import io
import sys
import tempfile
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import Any

import fory_compiler
import fory_compiler.cli as fory_cli
from fory_compiler.frontend.proto.ast import ProtoSchema
from fory_compiler.frontend.proto.translator import ProtoTranslator
from fory_compiler.generators.base import BaseGenerator
from google.protobuf import descriptor_pb2

from protoc_gen_fory.adapter import TypeIndex, adapt_file, is_adapted, select_files
from protoc_gen_fory.params import Params


class GenerationError(Exception):
    """foryc rejected the schema (reported to buf as a user error)."""


@contextlib.contextmanager
def _patched_fory(resolver: Any, src: Path, writers: dict[Path, str]) -> Iterator[None]:
    """Swap in the resolvers and record which source file wrote each output file."""

    def resolve_import_path(
        import_stmt: str, importing_file: Path, import_paths: list[Path]
    ) -> Path | None:
        candidate = (src / import_stmt).resolve()
        return candidate if candidate.exists() else None

    replacements = {"parse_idl_file": resolver, "resolve_import_path": resolve_import_path}
    patched: list[tuple[Any, str, Any]] = []
    for name, module in list(sys.modules.items()):
        if not (name == "fory_compiler" or name.startswith("fory_compiler.")):
            continue
        for attr, replacement in replacements.items():
            if hasattr(module, attr):
                patched.append((module, attr, getattr(module, attr)))
                setattr(module, attr, replacement)

    original_write = BaseGenerator.write_files

    def write_files(self: Any, files: Any) -> None:
        source = self.schema.source_file or "<input>"
        for file in files:
            target = (self.options.output_dir / file.path).resolve()
            previous = writers.get(target)
            if previous is not None and previous != source:
                # foryc overwrites silently; types from the earlier file are lost.
                print(
                    f"Warning: {file.path} is generated from both {previous} and "
                    f"{source}; the later one wins. Put each package in a single "
                    f".proto file for this language.",
                    file=sys.stderr,
                )
            writers[target] = source
        original_write(self, files)

    patched.append((BaseGenerator, "write_files", original_write))
    setattr(BaseGenerator, "write_files", write_files)
    try:
        yield
    finally:
        for owner, attr, original in patched:
            setattr(owner, attr, original)


def generate(
    proto_files: Sequence[descriptor_pb2.FileDescriptorProto],
    files_to_generate: Sequence[str],
    params: Params,
) -> list[tuple[str, str]]:
    """Return ``(relative path, content)`` of every generated file, sorted by path."""
    adapted_files, imports = select_files(proto_files, files_to_generate)
    index = TypeIndex(adapted_files, imports)

    with tempfile.TemporaryDirectory(prefix="protoc-gen-fory-") as tmp:
        tmp_root = Path(tmp).resolve()
        src = tmp_root / "src"
        out = tmp_root / "out"
        out.mkdir()

        asts: dict[Path, ProtoSchema] = {}
        for fd in adapted_files:
            path = src / fd.name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("")
            asts[path] = adapt_file(fd, index, str(path))

        go_mod = out / "go.mod"
        if params.go_module:
            go_mod.write_text(f"module {params.go_module}\n")

        def resolve(file_path: Path | str) -> Any:
            path = Path(file_path).resolve()
            ast = asts.get(path)
            if ast is None:
                raise ValueError(f"{path}: not part of the CodeGeneratorRequest")
            translator = ProtoTranslator(copy.deepcopy(ast))
            schema = translator.translate()
            for warning in translator.warnings:
                print(f"Warning: {warning}", file=sys.stderr)
            return schema

        targets = [src / name for name in files_to_generate if is_adapted(name)]
        already_generated = set(asts) - set(targets)

        log = io.StringIO()
        ok = True
        writers: dict[Path, str] = {}
        with _patched_fory(resolve, src, writers), contextlib.redirect_stdout(
            log
        ), contextlib.redirect_stderr(log):
            resolve_cache: dict[Path, Any] = {}
            generated_outputs: dict[Path, Path] = {}
            cpp_namespaces: dict[str, Any] = {}
            for target in targets:
                try:
                    ok = fory_cli.compile_file_recursive(
                        target,
                        {params.lang: out},
                        [src],
                        params.go_nested_type_style,
                        None,  # swift_namespace_style
                        False,  # emit_fdl
                        None,  # emit_fdl_path
                        already_generated,
                        set(),
                        resolve_cache,
                        None,  # go_module_root
                        generated_outputs,
                        cpp_namespaces,
                    )
                except fory_cli.ImportError as exc:
                    print(f"Import error: {exc}", file=sys.stderr)
                    ok = False
                if not ok:
                    break

        messages = log.getvalue().replace(f"{src}/", "").replace(f"{tmp_root}/", "")
        if not ok:
            errors = [
                line
                for line in messages.splitlines()
                if line.strip() and not line.startswith(("Compiling ", "  Generated: ", "  Resolved "))
            ]
            raise GenerationError("\n".join(errors) or "foryc failed without a message")
        for line in messages.splitlines():
            if line.startswith(("Warning", "Error")):
                print(f"protoc-gen-fory: {line}", file=sys.stderr)

        files = []
        for path in sorted(out.rglob("*")):
            if path.is_file() and path != go_mod:
                files.append((path.relative_to(out).as_posix(), path.read_text()))
        return files


def fory_compiler_version() -> str:
    return getattr(fory_compiler, "__version__", "unknown")
