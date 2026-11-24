"""Entry point of the ``protoc-gen-fory`` executable."""

from __future__ import annotations

import sys


def options_proto() -> str:
    """fory/options.proto as shipped in the wheel (or from the source tree)."""
    from importlib import resources
    from pathlib import Path

    shipped = resources.files("protoc_gen_fory").joinpath("fory").joinpath("options.proto")
    if shipped.is_file():
        return shipped.read_text()
    return (Path(__file__).resolve().parents[2] / "proto" / "fory" / "options.proto").read_text()


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] == "--options-proto":
        sys.stdout.write(options_proto())
        return 0
    if len(sys.argv) > 1 and sys.argv[1] in ("--version", "-V"):
        import google.protobuf

        from protoc_gen_fory import __version__
        from protoc_gen_fory.generate import fory_compiler_version

        print(
            f"protoc-gen-fory {__version__} (fory-compiler {fory_compiler_version()}, "
            f"protobuf {google.protobuf.__version__})"
        )
        return 0
    if sys.stdin.isatty():
        print(
            "protoc-gen-fory is a protoc/buf plugin and reads a CodeGeneratorRequest "
            "from stdin. Use it via buf generate (see README).\n"
            "  --version        print versions\n"
            "  --options-proto  print fory/options.proto (to vendor it)",
            file=sys.stderr,
        )
        return 1

    from protoc_gen_fory.plugin import run

    sys.stdout.buffer.write(run(sys.stdin.buffer.read()))
    sys.stdout.buffer.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
