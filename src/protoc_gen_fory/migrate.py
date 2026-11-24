"""Rewrite foryc-style ``(fory).x`` options to the buf-compatible syntax.

    protoc-gen-fory-migrate [--check] FILE.proto...

* ``option (fory).x = ...;`` at file level   -> ``option (fory.file).x``
* ... inside a message                        -> ``option (fory.message).x``
* ... inside an enum                          -> ``option (fory.enum).x``
* ``[(fory).x = ...]`` on a field             -> ``[(fory.field).x = ...]``
* adds ``import "fory/options.proto";`` when needed.

Comments and string literals are left alone. Options in other places
(oneof, service, rpc, enum values) have no declaration yet; they are
reported and left unchanged.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

_TOKEN = re.compile(
    r"""
    (?P<comment>//[^\n]*|/\*.*?\*/)
  | (?P<string>"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*')
  | (?P<fory>\(\s*fory\s*\))
  | (?P<ident>[A-Za-z_][A-Za-z0-9_]*)
  | (?P<punct>[{}\[\];])
    """,
    re.VERBOSE | re.DOTALL,
)

_BLOCKS = {"message", "enum", "oneof", "service", "rpc", "extend"}
_LEVEL = {None: "file", "message": "message", "enum": "enum"}
_IMPORT_LINE = 'import "fory/options.proto";'


@dataclass
class Result:
    text: str
    changed: int = 0
    skipped: list[str] = field(default_factory=list)


def _line_of(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


def migrate_source(text: str, filename: str = "<input>") -> Result:
    stack: list[str | None] = []
    pending_block: str | None = None
    in_brackets = 0
    statement_start = True
    statement_is_option = False
    replacements: list[tuple[int, int, str]] = []
    skipped: list[str] = []
    has_import = False

    for match in _TOKEN.finditer(text):
        kind = match.lastgroup
        value = match.group()
        if kind == "comment":
            continue
        if kind == "string":
            if value.strip("\"'") == "fory/options.proto":
                has_import = True
            statement_start = False
            continue
        if kind == "ident":
            if statement_start:
                statement_is_option = value == "option"
                if value in _BLOCKS:
                    pending_block = value
            statement_start = False
            continue
        if kind == "fory":
            line = _line_of(text, match.start())
            if in_brackets:
                context = stack[-1] if stack else None
                if context == "enum":
                    skipped.append(f"{filename}:{line}: enum value option (fory) has no declaration")
                else:
                    replacements.append((match.start(), match.end(), "(fory.field)"))
            elif statement_is_option:
                context = stack[-1] if stack else None
                level = _LEVEL.get(context)
                if level is None:
                    skipped.append(f"{filename}:{line}: option (fory) inside {context} has no declaration")
                else:
                    replacements.append((match.start(), match.end(), f"(fory.{level})"))
            statement_start = False
            continue
        # punctuation
        if value == "[":
            in_brackets += 1
        elif value == "]":
            in_brackets = max(0, in_brackets - 1)
        elif value == "{":
            stack.append(pending_block)
            pending_block = None
            statement_start = True
        elif value == "}":
            if stack:
                stack.pop()
            statement_start = True
        elif value == ";":
            pending_block = None
            statement_start = True
            statement_is_option = False

    out = text
    for start, end, new in reversed(replacements):
        out = out[:start] + new + out[end:]
    if replacements and not has_import:
        out = _add_import(out)
    return Result(out, len(replacements), skipped)


def _add_import(text: str) -> str:
    lines = text.splitlines(keepends=True)
    last: dict[str, int] = {}
    for i, line in enumerate(lines):
        keyword = line.strip().split(" ", 1)[0]
        if keyword in ("import", "package", "syntax"):
            last[keyword] = i
    anchor = last.get("import", last.get("package", last.get("syntax")))
    if anchor is None:
        return f"{_IMPORT_LINE}\n{text}"
    lines.insert(anchor + 1, f"{_IMPORT_LINE}\n")
    return "".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="protoc-gen-fory-migrate",
        description="Rewrite (fory).x options to (fory.file|message|field|enum).x for buf.",
    )
    parser.add_argument("files", nargs="+", type=Path)
    parser.add_argument(
        "--check", action="store_true", help="only report files that need changes (exit 1 if any)"
    )
    args = parser.parse_args(argv)

    needs_change = False
    for path in args.files:
        result = migrate_source(path.read_text(), str(path))
        for message in result.skipped:
            print(f"warning: {message}", file=sys.stderr)
        if not result.changed:
            continue
        needs_change = True
        if args.check:
            print(f"{path}: {result.changed} option(s) to migrate")
        else:
            path.write_text(result.text)
            print(f"{path}: migrated {result.changed} option(s)")
    return 1 if args.check and needs_change else 0


if __name__ == "__main__":
    sys.exit(main())
