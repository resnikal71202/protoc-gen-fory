"""protoc / buf plugin protocol: CodeGeneratorRequest in, CodeGeneratorResponse out."""

from __future__ import annotations

# Imported first: registers the fory extensions before the request is parsed.
from protoc_gen_fory import options as _options  # noqa: F401  # isort: skip

from google.protobuf.compiler import plugin_pb2

from protoc_gen_fory.adapter import AdapterError
from protoc_gen_fory.generate import GenerationError, generate
from protoc_gen_fory.params import ParameterError, parse_params


def run(request_bytes: bytes) -> bytes:
    request = plugin_pb2.CodeGeneratorRequest.FromString(request_bytes)
    response = process(request)
    return response.SerializeToString()


def process(request: plugin_pb2.CodeGeneratorRequest) -> plugin_pb2.CodeGeneratorResponse:
    response = plugin_pb2.CodeGeneratorResponse(
        # Editions are deliberately not declared: buf then rejects them with a clear message.
        supported_features=plugin_pb2.CodeGeneratorResponse.FEATURE_PROTO3_OPTIONAL,
    )
    try:
        params = parse_params(request.parameter)
        files = generate(request.proto_file, request.file_to_generate, params)
    except (ParameterError, AdapterError, GenerationError) as exc:
        # User errors go into the response; buf prints them and fails.
        response.error = f"protoc-gen-fory: {exc}"
        return response
    for name, content in files:
        response.file.add(name=name, content=content)
    return response
