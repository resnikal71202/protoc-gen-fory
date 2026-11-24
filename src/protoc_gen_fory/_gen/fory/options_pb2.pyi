from google.protobuf import descriptor_pb2 as _descriptor_pb2
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Optional as _Optional

DESCRIPTOR: _descriptor.FileDescriptor
FILE_FIELD_NUMBER: _ClassVar[int]
file: _descriptor.FieldDescriptor
MESSAGE_FIELD_NUMBER: _ClassVar[int]
message: _descriptor.FieldDescriptor
FIELD_FIELD_NUMBER: _ClassVar[int]
field: _descriptor.FieldDescriptor
ENUM_FIELD_NUMBER: _ClassVar[int]
enum: _descriptor.FieldDescriptor

class FileOptions(_message.Message):
    __slots__ = ("evolving", "enable_auto_type_id", "polymorphism", "use_record_for_java_message", "go_nested_type_style", "swift_namespace_style", "rust_use_chrono_temporal_types", "kotlin_package")
    EVOLVING_FIELD_NUMBER: _ClassVar[int]
    ENABLE_AUTO_TYPE_ID_FIELD_NUMBER: _ClassVar[int]
    POLYMORPHISM_FIELD_NUMBER: _ClassVar[int]
    USE_RECORD_FOR_JAVA_MESSAGE_FIELD_NUMBER: _ClassVar[int]
    GO_NESTED_TYPE_STYLE_FIELD_NUMBER: _ClassVar[int]
    SWIFT_NAMESPACE_STYLE_FIELD_NUMBER: _ClassVar[int]
    RUST_USE_CHRONO_TEMPORAL_TYPES_FIELD_NUMBER: _ClassVar[int]
    KOTLIN_PACKAGE_FIELD_NUMBER: _ClassVar[int]
    evolving: bool
    enable_auto_type_id: bool
    polymorphism: bool
    use_record_for_java_message: bool
    go_nested_type_style: str
    swift_namespace_style: str
    rust_use_chrono_temporal_types: bool
    kotlin_package: str
    def __init__(self, evolving: bool = ..., enable_auto_type_id: bool = ..., polymorphism: bool = ..., use_record_for_java_message: bool = ..., go_nested_type_style: _Optional[str] = ..., swift_namespace_style: _Optional[str] = ..., rust_use_chrono_temporal_types: bool = ..., kotlin_package: _Optional[str] = ...) -> None: ...

class MessageOptions(_message.Message):
    __slots__ = ("id", "alias", "evolving", "use_record_for_java", "deprecated", "namespace")
    ID_FIELD_NUMBER: _ClassVar[int]
    ALIAS_FIELD_NUMBER: _ClassVar[int]
    EVOLVING_FIELD_NUMBER: _ClassVar[int]
    USE_RECORD_FOR_JAVA_FIELD_NUMBER: _ClassVar[int]
    DEPRECATED_FIELD_NUMBER: _ClassVar[int]
    NAMESPACE_FIELD_NUMBER: _ClassVar[int]
    id: int
    alias: str
    evolving: bool
    use_record_for_java: bool
    deprecated: bool
    namespace: str
    def __init__(self, id: _Optional[int] = ..., alias: _Optional[str] = ..., evolving: bool = ..., use_record_for_java: bool = ..., deprecated: bool = ..., namespace: _Optional[str] = ...) -> None: ...

class FieldOptions(_message.Message):
    __slots__ = ("ref", "nullable", "weak_ref", "thread_safe_pointer", "deprecated", "type", "java_array")
    REF_FIELD_NUMBER: _ClassVar[int]
    NULLABLE_FIELD_NUMBER: _ClassVar[int]
    WEAK_REF_FIELD_NUMBER: _ClassVar[int]
    THREAD_SAFE_POINTER_FIELD_NUMBER: _ClassVar[int]
    DEPRECATED_FIELD_NUMBER: _ClassVar[int]
    TYPE_FIELD_NUMBER: _ClassVar[int]
    JAVA_ARRAY_FIELD_NUMBER: _ClassVar[int]
    ref: bool
    nullable: bool
    weak_ref: bool
    thread_safe_pointer: bool
    deprecated: bool
    type: str
    java_array: bool
    def __init__(self, ref: bool = ..., nullable: bool = ..., weak_ref: bool = ..., thread_safe_pointer: bool = ..., deprecated: bool = ..., type: _Optional[str] = ..., java_array: bool = ...) -> None: ...

class EnumOptions(_message.Message):
    __slots__ = ("id", "alias", "deprecated")
    ID_FIELD_NUMBER: _ClassVar[int]
    ALIAS_FIELD_NUMBER: _ClassVar[int]
    DEPRECATED_FIELD_NUMBER: _ClassVar[int]
    id: int
    alias: str
    deprecated: bool
    def __init__(self, id: _Optional[int] = ..., alias: _Optional[str] = ..., deprecated: bool = ...) -> None: ...
