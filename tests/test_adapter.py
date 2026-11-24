"""Adapter: the AST built from descriptors equals foryc's parser output on the same source."""

from __future__ import annotations

import pytest
from google.protobuf import descriptor_pb2

import helpers
from protoc_gen_fory.adapter import (
    AdapterError,
    TypeIndex,
    TypeNameError,
    TypeNamer,
    adapt_file,
    is_adapted,
    select_files,
)

pytestmark = pytest.mark.needs_buf


def _cases() -> list[tuple[str, str]]:
    return [
        (fixture, path.relative_to(helpers.FIXTURES / fixture).as_posix())
        for fixture in helpers.FIXTURE_NAMES
        for path in helpers.proto_files(helpers.FIXTURES / fixture)
    ]


@pytest.fixture(scope="module")
def images(tmp_path_factory: pytest.TempPathFactory) -> dict[str, descriptor_pb2.FileDescriptorSet]:
    return {
        name: helpers.buf_image(helpers.FIXTURES / name, tmp_path_factory.mktemp(name))
        for name in helpers.FIXTURE_NAMES
    }


@pytest.mark.parametrize(("fixture", "name"), _cases())
def test_ast_matches_foryc_parser(
    images: dict[str, descriptor_pb2.FileDescriptorSet], fixture: str, name: str
) -> None:
    files = [fd for fd in images[fixture].file if is_adapted(fd.name)]
    fd = next(f for f in files if f.name == name)
    adapted = adapt_file(fd, TypeIndex(files), name)

    source = helpers.to_foryc_syntax(
        (helpers.FIXTURES / fixture / name).read_text(),
        helpers.fixture_packages(helpers.FIXTURES / fixture),
    )
    parsed = helpers.foryc_ast(source, name)

    # Positions included: error messages point to the same line and column.
    assert helpers.ast_to_data(adapted) == helpers.ast_to_data(parsed)


def _file(**kwargs: object) -> descriptor_pb2.FileDescriptorProto:
    return descriptor_pb2.FileDescriptorProto(name="t.proto", package="p", syntax="proto3", **kwargs)  # type: ignore[arg-type]


def test_proto2_is_rejected() -> None:
    fd = _file()
    fd.syntax = "proto2"
    with pytest.raises(AdapterError, match="only proto3 is supported"):
        adapt_file(fd, TypeIndex([fd]), "t.proto")


def test_editions_are_rejected() -> None:
    fd = _file()
    fd.syntax = "editions"
    with pytest.raises(AdapterError, match="editions are not supported"):
        adapt_file(fd, TypeIndex([fd]), "t.proto")


def test_services_are_skipped_with_warning(capsys: pytest.CaptureFixture[str]) -> None:
    fd = _file(service=[descriptor_pb2.ServiceDescriptorProto(name="Svc")])
    schema = adapt_file(fd, TypeIndex([fd]), "t.proto")
    assert schema.services == []
    assert "services are not supported" in capsys.readouterr().err


def test_options_import_and_well_known_imports_are_dropped() -> None:
    fd = _file(dependency=["fory/options.proto", "google/protobuf/timestamp.proto", "other/a.proto"])
    assert adapt_file(fd, TypeIndex([fd]), "t.proto").imports == ["other/a.proto"]
    assert not is_adapted("fory/options.proto")
    assert not is_adapted("google/protobuf/any.proto")


class TestTypeNamer:
    @staticmethod
    def msg(name: str, *nested: descriptor_pb2.DescriptorProto) -> descriptor_pb2.DescriptorProto:
        return descriptor_pb2.DescriptorProto(name=name, nested_type=list(nested))

    @staticmethod
    def pkg(name: str, package: str, *messages: descriptor_pb2.DescriptorProto, deps: tuple[str, ...] = ()) -> descriptor_pb2.FileDescriptorProto:
        return descriptor_pb2.FileDescriptorProto(
            name=name, package=package, syntax="proto3", message_type=list(messages), dependency=list(deps)
        )

    def test_top_level_is_bare_even_from_another_package(self) -> None:
        a = self.pkg("a.proto", "p", self.msg("A"), self.msg("B"))
        b = self.pkg("b.proto", "q", self.msg("C"), deps=("a.proto",))
        index = TypeIndex([a, b])
        assert TypeNamer(index, "a.proto").name(".p.A", ("B",), "p") == "A"
        assert TypeNamer(index, "b.proto").name(".p.A", ("C",), "q") == "A"

    def test_nested_uses_the_path_from_the_top(self) -> None:
        fd = self.pkg("a.proto", "p", self.msg("Outer", self.msg("Inner", self.msg("Leaf"))))
        n = TypeNamer(TypeIndex([fd]), "a.proto")
        # Even from inside Outer: foryc's generators look names up from the top.
        assert n.name(".p.Outer.Inner", ("Outer",), "p") == "Outer.Inner"
        assert n.name(".p.Outer.Inner.Leaf", ("Outer", "Inner"), "p") == "Outer.Inner.Leaf"

    def test_well_known_types_stay_qualified(self) -> None:
        fd = self.pkg("a.proto", "p", self.msg("A"))
        n = TypeNamer(TypeIndex([fd]), "a.proto")
        assert n.name(".google.protobuf.Timestamp", ("A",), "p") == "google.protobuf.Timestamp"

    def test_shadowed_top_level_is_an_error(self) -> None:
        fd = self.pkg("a.proto", "p", self.msg("Item"), self.msg("Catalog", self.msg("Item")), self.msg("Shelf"))
        n = TypeNamer(TypeIndex([fd]), "a.proto")
        assert n.name(".p.Item", ("Shelf",), "p") == "Item"
        with pytest.raises(TypeNameError, match="shadowed by a nested type 'Item'"):
            n.name(".p.Item", ("Catalog",), "p")

    def test_shadowed_first_component_of_a_nested_path_is_an_error(self) -> None:
        fd = self.pkg(
            "a.proto",
            "p",
            self.msg("Outer", self.msg("Inner")),
            self.msg("Box", self.msg("Outer")),
            self.msg("Other"),
        )
        n = TypeNamer(TypeIndex([fd]), "a.proto")
        assert n.name(".p.Outer.Inner", ("Other",), "p") == "Outer.Inner"
        # Inside Box, Java would resolve Outer.Inner to Box.Outer.Inner.
        with pytest.raises(TypeNameError, match="shadowed by a nested type 'Outer'"):
            n.name(".p.Outer.Inner", ("Box",), "p")
        # Referencing the own nested path from inside is fine.
        assert n.name(".p.Box.Outer", ("Box",), "p") == "Box.Outer"

    def test_same_top_level_name_in_two_visible_packages_is_an_error(self) -> None:
        a = self.pkg("a.proto", "p", self.msg("Money"))
        b = self.pkg("b.proto", "q", self.msg("Money"))
        c = self.pkg("c.proto", "r", self.msg("Order"), deps=("a.proto", "b.proto"))
        d = self.pkg("d.proto", "s", self.msg("Invoice"), deps=("a.proto",))
        index = TypeIndex([a, b, c, d])
        with pytest.raises(TypeNameError, match=r"declared in several imported packages \(p, q\)"):
            TypeNamer(index, "c.proto").name(".p.Money", ("Order",), "r")
        # Not visible from d.proto: no conflict there.
        assert TypeNamer(index, "d.proto").name(".p.Money", ("Invoice",), "s") == "Money"

    def test_transitive_imports_are_visible(self) -> None:
        a = self.pkg("a.proto", "p", self.msg("Money"))
        b = self.pkg("b.proto", "q", self.msg("Wallet"), deps=("a.proto",))
        c = self.pkg("c.proto", "r", self.msg("Money"), deps=("b.proto",))
        with pytest.raises(TypeNameError):
            TypeNamer(TypeIndex([a, b, c]), "c.proto").name(".r.Money", (), "r")


class TestSelectFiles:
    @staticmethod
    def fd(name: str, *deps: str, **kwargs: object) -> descriptor_pb2.FileDescriptorProto:
        return descriptor_pb2.FileDescriptorProto(
            name=name, syntax="proto3", dependency=list(deps), **kwargs  # type: ignore[arg-type]
        )

    def test_only_reachable_files_are_selected(self) -> None:
        a = self.fd("a.proto", "b.proto", package="a")
        b = self.fd("b.proto", package="b")
        stray = self.fd("stray.proto", package="s")
        stray.syntax = "proto2"
        files, imports = select_files([b, a, stray], ["a.proto"])
        assert [f.name for f in files] == ["b.proto", "a.proto"]
        assert imports == {"a.proto": ["b.proto"], "b.proto": []}

    def test_option_only_import_is_dropped_unless_its_types_are_used(self) -> None:
        opts = self.fd(
            "opts.proto",
            "google/protobuf/descriptor.proto",
            package="opts",
            message_type=[descriptor_pb2.DescriptorProto(name="Rule")],
            extension=[
                descriptor_pb2.FieldDescriptorProto(
                    name="rule", extendee=".google.protobuf.FieldOptions", type_name=".opts.Rule"
                )
            ],
        )
        uses_option = self.fd("a.proto", "opts.proto", "fory/options.proto", package="a")
        uses_type = self.fd(
            "b.proto",
            "opts.proto",
            package="b",
            message_type=[
                descriptor_pb2.DescriptorProto(
                    name="B",
                    field=[descriptor_pb2.FieldDescriptorProto(name="r", type_name=".opts.Rule")],
                )
            ],
        )
        files, imports = select_files([opts, uses_option, uses_type], ["a.proto", "b.proto"])
        assert imports["a.proto"] == []
        assert imports["b.proto"] == ["opts.proto"]
        assert "opts.proto" in [f.name for f in files]
