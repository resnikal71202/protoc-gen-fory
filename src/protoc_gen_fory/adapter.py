"""Build foryc's proto AST (``ProtoSchema``) from ``FileDescriptorProto``s.

This replaces foryc's lexer and parser. Everything after the AST (translator,
validator, generators) is foryc's own code.

The AST mirrors what foryc's parser yields for the same source:

* google/protobuf/* imports are dropped (the parser does that too), and so is
  fory/options.proto, which only declares options.
* map fields become ``map<K, V>`` types; their synthetic entry messages vanish.
* proto3 ``optional`` becomes ``label="optional"``; its synthetic oneof vanishes.
* Type references are written the way a person would write them for foryc
  (see :class:`TypeNamer`), because foryc resolves names in its own way.
* Positions come from SourceCodeInfo, 1-based like foryc's lexer.
"""

from __future__ import annotations

import sys
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from fory_compiler.frontend.proto.ast import (
    ProtoEnum,
    ProtoEnumValue,
    ProtoField,
    ProtoMessage,
    ProtoOneof,
    ProtoSchema,
    ProtoType,
)
from google.protobuf import descriptor_pb2

from protoc_gen_fory import options

FDP = descriptor_pb2.FieldDescriptorProto

OPTIONS_PROTO = "fory/options.proto"

SCALAR_NAMES: dict[int, str] = {
    FDP.TYPE_DOUBLE: "double",
    FDP.TYPE_FLOAT: "float",
    FDP.TYPE_INT64: "int64",
    FDP.TYPE_UINT64: "uint64",
    FDP.TYPE_INT32: "int32",
    FDP.TYPE_FIXED64: "fixed64",
    FDP.TYPE_FIXED32: "fixed32",
    FDP.TYPE_BOOL: "bool",
    FDP.TYPE_STRING: "string",
    FDP.TYPE_BYTES: "bytes",
    FDP.TYPE_UINT32: "uint32",
    FDP.TYPE_SFIXED32: "sfixed32",
    FDP.TYPE_SFIXED64: "sfixed64",
    FDP.TYPE_SINT32: "sint32",
    FDP.TYPE_SINT64: "sint64",
}

# FileDescriptorProto / DescriptorProto field numbers used in SourceCodeInfo paths.
_FILE_MESSAGE = 4
_FILE_ENUM = 5
_MSG_FIELD = 2
_MSG_NESTED = 3
_MSG_ENUM = 4
_MSG_ONEOF = 8
_ENUM_VALUE = 2


class AdapterError(Exception):
    """A .proto construct that Fory cannot represent (reported as a user error)."""

    def __init__(self, message: str, file: str, line: int = 0, column: int = 0):
        location = f"{file}:{line}:{column}" if line else file
        super().__init__(f"{location}: {message}")


def warn(message: str) -> None:
    print(f"protoc-gen-fory: warning: {message}", file=sys.stderr)


class TypeNameError(Exception):
    """A type reference that foryc cannot express; carries no location yet."""


@dataclass(frozen=True)
class TypeInfo:
    full_name: str  # without leading dot, e.g. "demo.Order.Line"
    package: str
    path: tuple[str, ...]  # message path inside the package, e.g. ("Order", "Line")
    file: str


class TypeIndex:
    """All named types (messages, enums) of a CodeGeneratorRequest."""

    def __init__(
        self,
        files: list[descriptor_pb2.FileDescriptorProto],
        imports: dict[str, list[str]] | None = None,
    ):
        self.types: dict[str, TypeInfo] = {}
        self.map_entries: dict[str, descriptor_pb2.DescriptorProto] = {}
        # File -> imports foryc will see (option-only imports already dropped).
        self._deps: dict[str, list[str]] = {
            fd.name: list((imports or {}).get(fd.name, fd.dependency)) for fd in files
        }
        # File -> top-level type names it declares.
        self._top_level: dict[str, list[TypeInfo]] = {fd.name: [] for fd in files}
        for fd in files:
            for msg in fd.message_type:
                self._add_message(fd, (), msg)
            for enum in fd.enum_type:
                self._add(fd, (enum.name,))

    def _add(self, fd: descriptor_pb2.FileDescriptorProto, path: tuple[str, ...]) -> None:
        full = ".".join((fd.package, *path)) if fd.package else ".".join(path)
        info = TypeInfo(full, fd.package, path, fd.name)
        self.types[full] = info
        if len(path) == 1:
            self._top_level[fd.name].append(info)

    def _add_message(
        self,
        fd: descriptor_pb2.FileDescriptorProto,
        parent: tuple[str, ...],
        msg: descriptor_pb2.DescriptorProto,
    ) -> None:
        path = (*parent, msg.name)
        self._add(fd, path)
        if msg.options.map_entry:
            self.map_entries[".".join((fd.package, *path)).lstrip(".")] = msg
        for nested in msg.nested_type:
            self._add_message(fd, path, nested)
        for enum in msg.enum_type:
            self._add(fd, (*path, enum.name))

    def imports_of(self, file: str) -> list[str]:
        return self._deps.get(file, [])

    def visible_top_level(self, file: str) -> dict[str, set[str]]:
        """Top-level name -> packages, over the file and its transitive imports.

        That is the set of types foryc merges into the schema of ``file``.
        """
        seen: set[str] = set()
        stack = [file]
        names: dict[str, set[str]] = {}
        while stack:
            current = stack.pop()
            if current in seen or current not in self._deps:
                continue
            seen.add(current)
            for info in self._top_level[current]:
                names.setdefault(info.path[0], set()).add(info.package)
            stack.extend(self._deps[current])
        return names


class TypeNamer:
    """Turn a fully qualified reference into the name foryc expects.

    foryc merges the top-level types of all imported files into one schema
    and its generators resolve names against that, without packages: a
    package-qualified name such as ``demo.common.Money`` passes validation but
    produces broken code (``com.example.demo.common.demo.common.Money`` in Java).
    A reference is therefore written as:

    * the bare name for a top-level type, from any imported package,
    * the path from the top-level type for a nested one (``Outer.Inner``),
      even inside ``Outer`` (generators look names up from the top),
    * the full name for well-known types (``google.protobuf.Timestamp``),
      which foryc maps itself.

    Two cases cannot be expressed in foryc and raise :class:`TypeNameError`: a
    top-level name declared in more than one visible package, and a reference
    whose first name component is shadowed by a nested type of an enclosing
    message (``Item`` or ``Outer.Inner`` inside a message that has its own
    ``Item`` / ``Outer``).
    """

    def __init__(self, index: TypeIndex, file: str):
        self.index = index
        self.visible = index.visible_top_level(file)

    def name(self, type_name: str, scope: tuple[str, ...], scope_package: str) -> str:
        full = type_name.lstrip(".")
        info = self.index.types.get(full)
        if info is None:
            return full
        top = info.path[0]
        packages = self.visible.get(top, set())
        if len(packages) > 1:
            listed = ", ".join(sorted(p or "<no package>" for p in packages))
            raise TypeNameError(
                f"type name {top!r} is declared in several imported packages ({listed}); "
                "Fory resolves type names without packages, rename one of them"
            )
        if self._shadowed(top, scope, scope_package):
            # foryc resolves the name from the top level, but the generated code
            # (e.g. a Java member class) resolves it to the nested type.
            raise TypeNameError(
                f"reference to {full!r} is shadowed by a nested type {top!r} "
                "in an enclosing message; Fory cannot express it, rename one of them"
            )
        return ".".join(info.path)

    def _shadowed(self, simple: str, scope: tuple[str, ...], package: str) -> bool:
        # foryc checks the enclosing messages before the top-level types.
        for depth in range(len(scope), 0, -1):
            candidate = ".".join((package, *scope[:depth], simple)).lstrip(".")
            if candidate in self.index.types:
                return True
        return False


class SourceLocations:
    def __init__(self, fd: descriptor_pb2.FileDescriptorProto):
        self._spans: dict[tuple[int, ...], tuple[int, int]] = {}
        for loc in fd.source_code_info.location:
            if len(loc.span) >= 3:
                self._spans.setdefault(tuple(loc.path), (loc.span[0] + 1, loc.span[1] + 1))

    def get(self, path: tuple[int, ...]) -> tuple[int, int]:
        return self._spans.get(path, (0, 0))


class FileAdapter:
    def __init__(
        self,
        fd: descriptor_pb2.FileDescriptorProto,
        index: TypeIndex,
        source_file: str,
    ):
        self.fd = fd
        self.index = index
        self.source_file = source_file
        self.namer = TypeNamer(index, fd.name)
        self.locations = SourceLocations(fd)

    def error(self, message: str, path: tuple[int, ...] = ()) -> AdapterError:
        line, column = self.locations.get(path)
        return AdapterError(message, self.fd.name, line, column)

    def adapt(self) -> ProtoSchema:
        fd = self.fd
        syntax = fd.syntax or "proto2"
        if syntax == "editions":
            raise self.error("protobuf editions are not supported (proto3 only)")
        if syntax != "proto3":
            raise self.error(f"unsupported syntax {syntax!r}, only proto3 is supported")
        if fd.service:
            warn(f"{fd.name}: services are not supported in v1 and are skipped")
        if fd.extension:
            warn(f"{fd.name}: extension declarations are ignored")

        return ProtoSchema(
            syntax="proto3",
            package=fd.package or None,
            imports=[dep for dep in self.index.imports_of(fd.name) if is_adapted(dep)],
            enums=[
                self._enum(enum, (_FILE_ENUM, i)) for i, enum in enumerate(fd.enum_type)
            ],
            messages=[
                self._message(msg, (), (_FILE_MESSAGE, i))
                for i, msg in enumerate(fd.message_type)
            ],
            services=[],
            options=options.file_options(fd),
            source_file=self.source_file,
        )

    def _enum(self, enum: descriptor_pb2.EnumDescriptorProto, path: tuple[int, ...]) -> ProtoEnum:
        line, column = self.locations.get(path)
        values = []
        for i, value in enumerate(enum.value):
            vline, vcolumn = self.locations.get((*path, _ENUM_VALUE, i))
            values.append(ProtoEnumValue(value.name, value.number, vline, vcolumn))
        return ProtoEnum(
            name=enum.name,
            values=values,
            options=options.enum_options(enum),
            line=line,
            column=column,
        )

    def _message(
        self,
        msg: descriptor_pb2.DescriptorProto,
        parent: tuple[str, ...],
        path: tuple[int, ...],
    ) -> ProtoMessage:
        scope = (*parent, msg.name)
        line, column = self.locations.get(path)
        if msg.extension:
            warn(f"{self.fd.name}: extension declarations in {'.'.join(scope)} are ignored")

        real_oneofs = {
            field.oneof_index
            for field in msg.field
            if field.HasField("oneof_index") and not field.proto3_optional
        }
        oneofs: dict[int, ProtoOneof] = {}
        for i, decl in enumerate(msg.oneof_decl):
            if i in real_oneofs:
                oline, ocolumn = self.locations.get((*path, _MSG_ONEOF, i))
                oneofs[i] = ProtoOneof(decl.name, [], oline, ocolumn)

        fields: list[ProtoField] = []
        for i, field in enumerate(msg.field):
            adapted = self._field(field, scope, (*path, _MSG_FIELD, i))
            if field.HasField("oneof_index") and field.oneof_index in oneofs:
                adapted.label = None
                oneofs[field.oneof_index].fields.append(adapted)
            else:
                fields.append(adapted)

        nested_messages = [
            self._message(nested, scope, (*path, _MSG_NESTED, i))
            for i, nested in enumerate(msg.nested_type)
            if not nested.options.map_entry
        ]
        nested_enums = [
            self._enum(enum, (*path, _MSG_ENUM, i)) for i, enum in enumerate(msg.enum_type)
        ]
        return ProtoMessage(
            name=msg.name,
            fields=fields,
            nested_messages=nested_messages,
            nested_enums=nested_enums,
            oneofs=[oneofs[i] for i in sorted(oneofs)],
            options=options.message_options(msg),
            line=line,
            column=column,
        )

    def _type_name(
        self,
        field: descriptor_pb2.FieldDescriptorProto,
        scope: tuple[str, ...],
        path: tuple[int, ...],
    ) -> str:
        if field.type in (FDP.TYPE_MESSAGE, FDP.TYPE_ENUM):
            try:
                return self.namer.name(field.type_name, scope, self.fd.package)
            except TypeNameError as exc:
                raise self.error(f"field {field.name!r}: {exc}", path) from None
        return SCALAR_NAMES[field.type]

    def _field(
        self,
        field: descriptor_pb2.FieldDescriptorProto,
        scope: tuple[str, ...],
        path: tuple[int, ...],
    ) -> ProtoField:
        line, column = self.locations.get(path)
        if field.type == FDP.TYPE_GROUP:
            raise self.error(f"group field {field.name!r} is not supported", path)

        label: str | None = None
        entry = None
        if field.type == FDP.TYPE_MESSAGE:
            entry = self.index.map_entries.get(field.type_name.lstrip("."))
        if entry is not None:
            key = next(f for f in entry.field if f.number == 1)
            value = next(f for f in entry.field if f.number == 2)
            field_type = ProtoType(
                name="map",
                is_map=True,
                map_key_type=self._type_name(key, scope, path),
                map_value_type=self._type_name(value, scope, path),
                line=line,
                column=column,
            )
        else:
            field_type = ProtoType(self._type_name(field, scope, path), line=line, column=column)
            if field.label == FDP.LABEL_REPEATED:
                label = "repeated"
            elif field.proto3_optional:
                label = "optional"

        return ProtoField(
            name=field.name,
            field_type=field_type,
            number=field.number,
            label=label,
            options=options.field_options(field),
            line=line,
            column=column,
        )


def _declared_types(fd: descriptor_pb2.FileDescriptorProto) -> set[str]:
    names: set[str] = set()

    def walk(prefix: str, msgs: Any, enums: Any) -> None:
        for enum in enums:
            names.add(f"{prefix}{enum.name}")
        for msg in msgs:
            names.add(f"{prefix}{msg.name}")
            walk(f"{prefix}{msg.name}.", msg.nested_type, msg.enum_type)

    walk(f".{fd.package}." if fd.package else ".", fd.message_type, fd.enum_type)
    return names


def _referenced_types(fd: descriptor_pb2.FileDescriptorProto) -> set[str]:
    names: set[str] = set()

    def walk(msgs: Any) -> None:
        for msg in msgs:
            names.update(f.type_name for f in msg.field if f.type_name)
            walk(msg.nested_type)

    walk(fd.message_type)
    return names


def _declares_options(fd: descriptor_pb2.FileDescriptorProto) -> bool:
    """The file extends google.protobuf.*Options (e.g. protovalidate, google.api)."""

    def extendees(msgs: Any) -> list[str]:
        found = []
        for msg in msgs:
            found += [ext.extendee for ext in msg.extension]
            found += extendees(msg.nested_type)
        return found

    all_extendees = [ext.extendee for ext in fd.extension] + extendees(fd.message_type)
    return any(
        e.startswith(".google.protobuf.") and e.endswith("Options") for e in all_extendees
    )


def select_files(
    proto_files: Sequence[descriptor_pb2.FileDescriptorProto],
    files_to_generate: Sequence[str],
) -> tuple[list[descriptor_pb2.FileDescriptorProto], dict[str, list[str]]]:
    """Files to adapt, and the imports foryc should see for each of them.

    Only files reachable from ``files_to_generate`` are adapted. An import is
    dropped when it only provides custom options for the importer: the
    imported file extends ``google.protobuf.*Options`` and the importer uses
    none of its types in fields (protovalidate, google/api/annotations.proto).
    Such files may be proto2 or editions, and Fory has nothing to generate
    from them.
    """
    by_name = {fd.name: fd for fd in proto_files}
    declared = {fd.name: _declared_types(fd) for fd in proto_files}
    selected: dict[str, descriptor_pb2.FileDescriptorProto] = {}
    imports: dict[str, list[str]] = {}
    stack = [name for name in files_to_generate if is_adapted(name)]
    while stack:
        name = stack.pop()
        fd = by_name.get(name)
        if fd is None or name in selected:
            continue
        selected[name] = fd
        used = _referenced_types(fd)
        kept = []
        for dep in fd.dependency:
            dep_fd = by_name.get(dep)
            if not is_adapted(dep) or dep_fd is None:
                continue
            if _declares_options(dep_fd) and not (declared[dep] & used):
                continue
            kept.append(dep)
            stack.append(dep)
        imports[name] = kept
    ordered = [fd for fd in proto_files if fd.name in selected]
    return ordered, imports


def adapt_file(
    fd: descriptor_pb2.FileDescriptorProto, index: TypeIndex, source_file: str
) -> ProtoSchema:
    return FileAdapter(fd, index, source_file).adapt()


def is_adapted(name: str) -> bool:
    """Files that become Fory schemas (not well-known types or option declarations)."""
    return not name.startswith("google/protobuf/") and name != OPTIONS_PROTO
