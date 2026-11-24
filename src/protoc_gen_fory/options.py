"""Read options from descriptors in the format foryc's proto parser produces.

foryc's parser stores options as a flat dict: ``option java_package = "x";``
becomes ``{"java_package": "x"}`` and ``(fory).ref = true`` becomes
``{"fory.ref": True}``. Enum-valued options appear as their identifier
(``optimize_for = SPEED`` -> ``"SPEED"``).

Under buf, Fory options are real extensions with one extension per level:
``(fory.file)``, ``(fory.message)``, ``(fory.field)``, ``(fory.enum)``. This
module flattens them back to ``"fory.<name>"`` so the Fory translator stays
unchanged.

Standard options are read from the descriptors, so buf managed mode
overrides (java_package, go_package, ...) are picked up as well.
"""

from __future__ import annotations

from typing import Any

from google.protobuf import descriptor as _descriptor
from google.protobuf import descriptor_pb2
from google.protobuf.message import Message

# Importing registers the extensions in the default pool. It must happen
# before the CodeGeneratorRequest is parsed, or the options stay unknown fields.
from protoc_gen_fory._gen.fory import options_pb2

OptionDict = dict[str, object]

# Standard options foryc's parser would never see from source, or that make
# no sense as Fory options.
_SKIP_STANDARD = {"map_entry", "features"}


def _scalar(field: _descriptor.FieldDescriptor, value: Any) -> object | None:
    if field.type == _descriptor.FieldDescriptor.TYPE_ENUM and field.enum_type is not None:
        enum_value = field.enum_type.values_by_number.get(value)
        return enum_value.name if enum_value is not None else int(value)
    if field.type in (
        _descriptor.FieldDescriptor.TYPE_MESSAGE,
        _descriptor.FieldDescriptor.TYPE_GROUP,
    ):
        return None
    if isinstance(value, (bool, int, float, str)):
        return value
    return None


def _is_repeated(field: _descriptor.FieldDescriptor) -> bool:
    # protobuf >= 6.31 has is_repeated; `label` was removed in 7.
    is_repeated = getattr(field, "is_repeated", None)
    if is_repeated is not None:
        return bool(is_repeated)
    label = getattr(field, "label", None)
    return bool(label == _descriptor.FieldDescriptor.LABEL_REPEATED)


def _standard_options(options: Message) -> OptionDict:
    result: OptionDict = {}
    for field, value in options.ListFields():
        if field.is_extension or field.name in _SKIP_STANDARD:
            continue
        if _is_repeated(field):
            continue
        converted = _scalar(field, value)
        if converted is not None:
            result[field.name] = converted
    return result


def _fory_options(options: Message, extension: Any) -> OptionDict:
    if not options.HasExtension(extension):
        return {}
    ext_value: Message = options.Extensions[extension]
    result: OptionDict = {}
    for field, value in ext_value.ListFields():
        converted = _scalar(field, value)
        if converted is not None:
            result[f"fory.{field.name}"] = converted
    return result


def file_options(fd: descriptor_pb2.FileDescriptorProto) -> OptionDict:
    if not fd.HasField("options"):
        return {}
    opts = _standard_options(fd.options)
    opts.update(_fory_options(fd.options, options_pb2.file))
    return opts


def message_options(msg: descriptor_pb2.DescriptorProto) -> OptionDict:
    if not msg.HasField("options"):
        return {}
    opts = _standard_options(msg.options)
    opts.update(_fory_options(msg.options, options_pb2.message))
    return opts


def enum_options(enum: descriptor_pb2.EnumDescriptorProto) -> OptionDict:
    if not enum.HasField("options"):
        return {}
    opts = _standard_options(enum.options)
    opts.update(_fory_options(enum.options, options_pb2.enum))
    return opts


def field_options(field: descriptor_pb2.FieldDescriptorProto) -> OptionDict:
    if not field.HasField("options"):
        return {}
    opts = _standard_options(field.options)
    opts.update(_fory_options(field.options, options_pb2.field))
    return opts
