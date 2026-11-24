"""Plugin behavior through buf: errors, managed mode, Go layout, warnings."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest
from google.protobuf.compiler import plugin_pb2

import helpers
from protoc_gen_fory.plugin import process

FIXTURE = helpers.FIXTURES / "multi"


def _write(root: Path, files: dict[str, str]) -> Path:
    for name, content in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(textwrap.dedent(content))
    return root


def test_missing_lang_is_a_user_error() -> None:
    response = process(plugin_pb2.CodeGeneratorRequest(parameter=""))
    assert response.error.startswith("protoc-gen-fory: missing required parameter 'lang'")
    assert response.supported_features == plugin_pb2.CodeGeneratorResponse.FEATURE_PROTO3_OPTIONAL


def test_empty_request_generates_nothing() -> None:
    response = process(plugin_pb2.CodeGeneratorRequest(parameter="lang=java"))
    assert not response.error
    assert len(response.file) == 0


@pytest.mark.needs_buf
class TestThroughBuf:
    def test_parameter_error_is_reported_by_buf(self, tmp_path: Path) -> None:
        proc = helpers.run_buf(FIXTURE, "cobol", tmp_path, check=False)
        assert proc.returncode != 0
        assert "unsupported lang 'cobol'" in proc.stderr

    def test_proto2_file_is_rejected(self, tmp_path: Path) -> None:
        fixture = _write(
            tmp_path / "fx",
            {"p2.proto": 'syntax = "proto2";\npackage p2;\nmessage M { optional int32 a = 1; }\n'},
        )
        proc = helpers.run_buf(fixture, "java", tmp_path / "w", check=False)
        assert proc.returncode != 0
        assert "p2.proto" in proc.stderr and "only proto3 is supported" in proc.stderr

    def test_fory_errors_carry_the_proto_path(self, tmp_path: Path) -> None:
        fixture = _write(
            tmp_path / "fx",
            {
                "bad/bad.proto": """\
                syntax = "proto3";
                package bad;
                import "fory/options.proto";
                message M {
                  int32 s = 1 [(fory.field).type = "tagged int32"];
                }
                """
            },
        )
        proc = helpers.run_buf(fixture, "java", tmp_path / "w", check=False)
        assert proc.returncode != 0
        assert "protoc-gen-fory: Error: Unsupported fory.type override 'tagged int32'" in proc.stderr
        # Temp directories of the plugin must not leak into messages.
        assert "protoc-gen-fory-" not in proc.stderr

    def test_unknown_type_points_to_file_line_column(self, tmp_path: Path) -> None:
        fixture = _write(
            tmp_path / "fx",
            {
                "w/wrappers.proto": """\
                syntax = "proto3";
                package w;
                import "google/protobuf/wrappers.proto";
                message M {
                  google.protobuf.StringValue s = 1;
                }
                """
            },
        )
        proc = helpers.run_buf(fixture, "java", tmp_path / "w", check=False)
        assert proc.returncode != 0
        assert "w/wrappers.proto:5:3: Unknown type 'google.protobuf.StringValue'" in proc.stderr

    def test_managed_mode_overrides_reach_the_generated_code(self, tmp_path: Path) -> None:
        managed = textwrap.dedent(
            """\
            managed:
              enabled: true
              override:
                - file_option: java_package_prefix
                  value: org.managed
            """
        )
        tree = helpers.run_buf(FIXTURE, "java", tmp_path, managed=managed)
        assert any(path.startswith("org/managed/") for path in tree), sorted(tree)
        order = next(content for path, content in tree.items() if path.endswith("/Order.java"))
        assert "package org.managed." in order

    def test_go_module_strips_the_module_prefix(self, tmp_path: Path) -> None:
        default = helpers.run_buf(FIXTURE, "go", tmp_path / "default")
        with_module = helpers.run_buf(FIXTURE, "go", tmp_path / "module", opts=["go_module=example.com/demo"])
        assert sorted(default) == ["common/demo_common.go", "order/demo_order.go", "status/demo_status.go"]
        assert sorted(with_module) == sorted(default)
        nested = helpers.run_buf(FIXTURE, "go", tmp_path / "nested", opts=["go_module=example.com"])
        assert sorted(nested) == [
            "demo/common/demo_common.go",
            "demo/order/demo_order.go",
            "demo/status/demo_status.go",
        ]

    def test_same_package_in_two_files_warns(self, tmp_path: Path) -> None:
        fixture = _write(
            tmp_path / "fx",
            {
                "p/a.proto": 'syntax = "proto3";\npackage p;\nmessage A { int32 x = 1; }\n',
                "p/b.proto": 'syntax = "proto3";\npackage p;\nmessage B { int32 y = 1; }\n',
            },
        )
        proc = helpers.run_buf(fixture, "python", tmp_path / "w", check=False)
        assert proc.returncode == 0, proc.stderr
        assert "p.py is generated from both p/a.proto and p/b.proto" in proc.stderr

    def test_same_package_in_two_files_fails_for_rust_like_foryc(self, tmp_path: Path) -> None:
        fixture = _write(
            tmp_path / "fx",
            {
                "p/a.proto": 'syntax = "proto3";\npackage p;\nmessage A { int32 x = 1; }\n',
                "p/b.proto": 'syntax = "proto3";\npackage p;\nmessage B { int32 y = 1; }\n',
            },
        )
        code, _ = helpers.run_foryc(fixture, "rust", tmp_path / "foryc", check=False)
        assert code != 0
        proc = helpers.run_buf(fixture, "rust", tmp_path / "w", check=False)
        assert proc.returncode != 0
        assert "Rust output path collision" in proc.stderr


@pytest.mark.needs_buf
def test_shadowed_reference_is_reported_with_location(tmp_path: Path) -> None:
    fixture = _write(
        tmp_path / "fx",
        {
            "s/shadow.proto": """\
            syntax = "proto3";
            package s;
            message Item { string name = 1; }
            message Catalog {
              message Item { string sku = 1; }
              s.Item legacy = 1;
            }
            """
        },
    )
    proc = helpers.run_buf(fixture, "java", tmp_path / "w", check=False)
    assert proc.returncode != 0
    assert "s/shadow.proto:6:3: field 'legacy': reference to 's.Item' is shadowed by a nested type 'Item'" in proc.stderr


def test_runtime_versions_match_expectation() -> None:
    """CI sets EXPECT_PROTOBUF in the lowest-version job: test and plugin process must use it."""
    import os
    import subprocess

    import google.protobuf

    expected = os.environ.get("EXPECT_PROTOBUF")
    if not expected:
        pytest.skip("EXPECT_PROTOBUF not set")
    assert google.protobuf.__version__ == expected
    out = subprocess.run(
        [helpers.plugin_command(), "--version"], capture_output=True, text=True, check=True
    ).stdout
    assert f"protobuf {expected})" in out, out


CUSTOM_OPTIONS_PROTO2 = """\
syntax = "proto2";
package opts;
import "google/protobuf/descriptor.proto";
message Rule { optional string pattern = 1; }
extend google.protobuf.FieldOptions { optional Rule rule = 50001; }
"""


@pytest.mark.needs_buf
class TestDependencies:
    def test_option_only_proto2_import_is_ignored(self, tmp_path: Path) -> None:
        """Like protovalidate: a proto2 file that only provides custom options."""
        fixture = _write(
            tmp_path / "fx",
            {
                "opts/opts.proto": CUSTOM_OPTIONS_PROTO2,
                "app/user.proto": """\
                syntax = "proto3";
                package app;
                import "opts/opts.proto";
                message User {
                  string email = 1 [(opts.rule).pattern = ".+@.+"];
                }
                """,
            },
        )
        # Generate only app/ (as a user would): opts/ is just an import.
        proc = helpers.run_buf(fixture, "python", tmp_path / "w2", check=False, inputs_exclude=["opts"])
        assert proc.returncode == 0, proc.stderr
        assert "extension declarations" not in proc.stderr
        generated = (tmp_path / "w2" / "buf-out" / "app.py").read_text()
        assert "opts" not in generated

    def test_proto2_import_whose_types_are_used_is_an_error(self, tmp_path: Path) -> None:
        fixture = _write(
            tmp_path / "fx",
            {
                "opts/opts.proto": CUSTOM_OPTIONS_PROTO2,
                "app/user.proto": """\
                syntax = "proto3";
                package app;
                import "opts/opts.proto";
                message User { opts.Rule rule = 1; }
                """,
            },
        )
        proc = helpers.run_buf(fixture, "python", tmp_path / "w", check=False, inputs_exclude=["opts"])
        assert proc.returncode != 0
        assert "opts/opts.proto" in proc.stderr and "only proto3 is supported" in proc.stderr

    def test_imports_resolve_from_the_module_root(self, tmp_path: Path) -> None:
        """`import "c.proto"` in a/b.proto means <root>/c.proto, even if a/c.proto exists."""
        fixture = _write(
            tmp_path / "fx",
            {
                "c.proto": 'syntax = "proto3";\npackage rootc;\nmessage C { int32 x = 1; }\n',
                "a/c.proto": 'syntax = "proto3";\npackage ac;\nmessage D { int32 y = 1; }\n',
                "a/b.proto": (
                    'syntax = "proto3";\npackage ab;\nimport "c.proto";\n'
                    "message B { rootc.C c = 1; }\n"
                ),
            },
        )
        tree = helpers.run_buf(fixture, "python", tmp_path / "w")
        assert "rootc.C" in tree["ab.py"]
