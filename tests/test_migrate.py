import textwrap
from pathlib import Path

import helpers
from protoc_gen_fory.migrate import main, migrate_source

OLD = textwrap.dedent(
    """\
    syntax = "proto3";
    package demo;

    import "other.proto";

    option (fory).evolving = true;
    option java_package = "com.example"; // (fory).ref in a comment stays

    enum Kind {
      option (fory).id = 5;
      KIND_UNKNOWN = 0;
    }

    message Node {
      option (fory).id = 10;
      string label = 1 [(fory).nullable = true, deprecated = true];
      Node parent = 2 [ ( fory ).weak_ref = true ];
      oneof v {
        Node child = 3 [(fory).ref = true];
      }
      string note = 4; /* (fory).x */
      string text = 5 [json_name = "(fory).ref"];
    }
    """
)


def test_rewrites_each_level() -> None:
    result = migrate_source(OLD)
    assert result.changed == 6
    assert result.skipped == []
    text = result.text
    assert 'import "other.proto";\nimport "fory/options.proto";\n' in text
    assert "option (fory.file).evolving = true;" in text
    assert "option (fory.enum).id = 5;" in text
    assert "option (fory.message).id = 10;" in text
    assert "[(fory.field).nullable = true, deprecated = true]" in text
    assert "[ (fory.field).weak_ref = true ]" in text
    assert "Node child = 3 [(fory.field).ref = true];" in text
    # Comments and strings are untouched.
    assert "// (fory).ref in a comment stays" in text
    assert "/* (fory).x */" in text
    assert 'json_name = "(fory).ref"' in text


def test_is_idempotent_and_the_inverse_of_the_test_converter() -> None:
    once = migrate_source(OLD).text
    assert migrate_source(once).changed == 0
    # Back to foryc syntax gives the original, except for the added import
    # line and normalized whitespace inside "( fory )".
    expected = OLD.replace('import "other.proto";\n', 'import "other.proto";\n\n')
    assert helpers.to_foryc_syntax(once) == expected.replace("( fory )", "(fory)")


def test_options_without_declaration_are_reported() -> None:
    source = 'syntax = "proto3";\nservice S {\n  option (fory).x = 1;\n}\nenum E { A = 0 [(fory).y = 1]; }\n'
    result = migrate_source(source, "s.proto")
    assert result.changed == 0
    assert result.text == source
    assert result.skipped == [
        "s.proto:3: option (fory) inside service has no declaration",
        "s.proto:5: enum value option (fory) has no declaration",
    ]


def test_import_goes_after_package_without_imports() -> None:
    text = migrate_source('syntax = "proto3";\npackage p;\noption (fory).evolving = false;\n').text
    assert text.splitlines()[:3] == ['syntax = "proto3";', "package p;", 'import "fory/options.proto";']


def test_cli_check_and_write(tmp_path: Path) -> None:
    path = tmp_path / "a.proto"
    path.write_text(OLD)
    assert main(["--check", str(path)]) == 1
    assert path.read_text() == OLD
    assert main([str(path)]) == 0
    assert main(["--check", str(path)]) == 0
