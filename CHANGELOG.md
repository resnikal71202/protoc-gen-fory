# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/).

The version in `pyproject.toml` must have a section here (CI checks it).
Every push to `main` releases that version, so the section needs a date
instead of `Unreleased` by then; it becomes the GitHub release notes.

## [0.1.0a1] - 2026-11-24

First pre-release. The option syntax and the extension number (50846) are not
final yet; install with `--prerelease allow` (uv) or `--pre` (pip).

### Added

- `protoc-gen-fory`: buf / protoc plugin that generates Apache Fory code for
  Java, Python, Go, Rust and JavaScript/TypeScript from proto3 files, using
  fory-compiler 1.7.8 for translation and code generation. Output is
  byte-identical to `foryc` on the same schema.
- `fory/options.proto`: Fory options as protobuf extensions, one per level:
  `(fory.file)`, `(fory.message)`, `(fory.field)`, `(fory.enum)`.
- Plugin parameters `lang`, `go_module`, `go_nested_type_style`.
- Managed-mode overrides (`java_package`, `go_package`, …) apply to Fory code.
- Errors for type references foryc cannot express (ambiguous across imported
  packages, shadowed by nested types), with file:line:column.
- Imports that only provide custom options (protovalidate, google/api) are ignored.
- `protoc-gen-fory-migrate`: rewrites `(fory).x` to the new option syntax.
- `protoc-gen-fory --options-proto` prints the options file for vendoring.

[0.1.0a1]: https://github.com/resnikal71202/protoc-gen-fory/releases/tag/v0.1.0a1
