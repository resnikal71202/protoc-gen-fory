"""Options decoder: descriptor options -> the dict foryc's parser builds."""

from google.protobuf import descriptor_pb2

from protoc_gen_fory import options
from protoc_gen_fory._gen.fory import options_pb2


def test_file_options_standard_and_fory() -> None:
    fd = descriptor_pb2.FileDescriptorProto(name="a.proto", syntax="proto3")
    fd.options.java_package = "com.example"
    fd.options.go_package = "example.com/a;a"
    fd.options.java_multiple_files = True
    fd.options.optimize_for = descriptor_pb2.FileOptions.SPEED
    ext = fd.options.Extensions[options_pb2.file]
    ext.evolving = False
    ext.go_nested_type_style = "camelcase"
    assert options.file_options(fd) == {
        "java_package": "com.example",
        "go_package": "example.com/a;a",
        "java_multiple_files": True,
        # Enum-valued options appear as their identifier, like in foryc's parser.
        "optimize_for": "SPEED",
        "fory.evolving": False,
        "fory.go_nested_type_style": "camelcase",
    }


def test_unset_options_are_absent() -> None:
    fd = descriptor_pb2.FileDescriptorProto(name="a.proto")
    assert options.file_options(fd) == {}
    msg = descriptor_pb2.DescriptorProto(name="M")
    msg.options.deprecated = False  # explicitly set -> present
    assert options.message_options(msg) == {"deprecated": False}


def test_message_options() -> None:
    msg = descriptor_pb2.DescriptorProto(name="M")
    ext = msg.options.Extensions[options_pb2.message]
    ext.id = 101
    ext.alias = "m"
    ext.evolving = True
    ext.use_record_for_java = True
    ext.namespace = "ns"
    ext.deprecated = True
    assert options.message_options(msg) == {
        "fory.id": 101,
        "fory.alias": "m",
        "fory.evolving": True,
        "fory.use_record_for_java": True,
        "fory.deprecated": True,
        "fory.namespace": "ns",
    }


def test_map_entry_is_not_an_option() -> None:
    msg = descriptor_pb2.DescriptorProto(name="TotalsEntry")
    msg.options.map_entry = True
    assert options.message_options(msg) == {}


def test_enum_options() -> None:
    enum = descriptor_pb2.EnumDescriptorProto(name="E")
    enum.options.Extensions[options_pb2.enum].id = 7
    assert options.enum_options(enum) == {"fory.id": 7}


def test_field_options_keep_explicit_false() -> None:
    field = descriptor_pb2.FieldDescriptorProto(name="f")
    ext = field.options.Extensions[options_pb2.field]
    ext.ref = True
    ext.weak_ref = True
    # Explicit false matters: it switches Rust from Arc to Rc.
    ext.thread_safe_pointer = False
    ext.nullable = True
    ext.type = "tagged int64"
    ext.java_array = True
    field.options.deprecated = True
    assert options.field_options(field) == {
        "deprecated": True,
        "fory.ref": True,
        "fory.nullable": True,
        "fory.weak_ref": True,
        "fory.thread_safe_pointer": False,
        "fory.type": "tagged int64",
        "fory.java_array": True,
    }


def test_every_declared_option_is_readable() -> None:
    """Each field of the four option messages maps to fory.<field name>."""
    for message_cls, getter, carrier, extension in [
        (options_pb2.FileOptions, options.file_options, descriptor_pb2.FileDescriptorProto, options_pb2.file),
        (options_pb2.MessageOptions, options.message_options, descriptor_pb2.DescriptorProto, options_pb2.message),
        (options_pb2.FieldOptions, options.field_options, descriptor_pb2.FieldDescriptorProto, options_pb2.field),
        (options_pb2.EnumOptions, options.enum_options, descriptor_pb2.EnumDescriptorProto, options_pb2.enum),
    ]:
        for field in message_cls.DESCRIPTOR.fields:
            node = carrier(name="x")
            ext = node.options.Extensions[extension]
            value = {"bool": True, "string": "v", "uint32": 5}[
                {8: "bool", 9: "string", 13: "uint32"}[field.type]
            ]
            setattr(ext, field.name, value)
            assert getter(node) == {f"fory.{field.name}": value}, field.full_name
