# protoc-gen-fory

A [buf](https://buf.build) / protoc plugin that generates [Apache Fory](https://fory.apache.org)
serialization code from `.proto` files.

`.proto` files stay the single source of truth. buf handles them (format, lint,
breaking changes, dependencies, BSR) and `buf generate` produces Fory code next
to your other plugins:

- **One command:** Fory code comes out of `buf generate` together with everything else.
- **One parser:** buf compiles the files once and the plugin gets the finished descriptors.
- **Managed mode:** overrides such as `java_package` or `go_package` from `buf.gen.yaml` also apply to the Fory code.

The plugin uses Fory's own compiler (`fory-compiler`) as a library. It only
replaces foryc's lexer and parser with an adapter that builds the same AST from
the descriptors buf sends. Translator, validator and generators are foryc's
unchanged code. The test suite checks that the plugin output is **byte-identical**
to `foryc` on the same schema for all supported languages.

| | |
|---|---|
| Languages | Java, Python, Go, Rust, JavaScript/TypeScript |
| Input | proto3 (no proto2, no editions) |
| fory-compiler | 1.7.8 (exact pin) |
| Python | ≥ 3.10 |

## Installation

Add it per project, so the plugin and Fory versions are in the lockfile and every
developer and CI generates the same code.

With uv (recommended):

```bash
uv add --dev protoc-gen-fory
```

With Poetry:

```bash
poetry add --group dev protoc-gen-fory
```

`uv run` / `poetry run` put the venv's `bin/` on `PATH`, so buf finds
`local: protoc-gen-fory` without a path.

## Setup

A complete project is in [examples/](examples).

**1. The options file.** Fory options are declared in `fory/options.proto`. Until
the module is on the BSR, vendor it into your proto tree:

```bash
uv run protoc-gen-fory --options-proto > proto/fory/options.proto
```

Exclude it from lint and generation (see `examples/buf.yaml`). Once the BSR module
exists, replace the vendored file with `deps: [buf.build/<org>/fory-options]`.

**2. `buf.gen.yaml`:** one entry per target language:

```yaml
version: v2
inputs:
  - directory: proto
    exclude_paths: [proto/fory]
plugins:
  - local: protoc-gen-fory
    out: gen/java
    strategy: all
    opt: [lang=java]
  - local: protoc-gen-fory
    out: gen/go
    strategy: all
    opt: [lang=go, go_module=example.com/acme/gen/go]
```

**3. Generate:**

```bash
uv run buf generate
```

### Parameters (`opt:`)

| Parameter | Values | |
|---|---|---|
| `lang` | `java`, `python`, `go`, `rust`, `javascript` | required |
| `go_module` | Go module path of `out` | like a `go.mod` in foryc's `--go_out`: strips the module prefix from `go_package` paths |
| `go_nested_type_style` | `underscore` (default), `camelcase` | same as `foryc --go_nested_type_style` |

Use `strategy: all`. Rust and Python generate one file per *package*, and a single
request across all files gives the same output as one `foryc` run.

## Fory options

Options are written per level: `(fory.file)`, `(fory.message)`, `(fory.field)` and `(fory.enum)`:

```proto
import "fory/options.proto";

option (fory.file).evolving = true;

message Node {
  option (fory.message).id = 100;
  Node parent = 1 [(fory.field).weak_ref = true];
  repeated Node children = 2 [(fory.field).ref = true];
  int64 seq = 3 [(fory.field).type = "tagged int64"];
}
```

| Level | Options |
|---|---|
| `fory.file` | `evolving`, `enable_auto_type_id`, `polymorphism`, `use_record_for_java_message`, `go_nested_type_style`, `swift_namespace_style`, `rust_use_chrono_temporal_types`, `kotlin_package` |
| `fory.message` | `id`, `alias`, `evolving`, `use_record_for_java`, `deprecated`, `namespace` |
| `fory.field` | `ref`, `nullable`, `weak_ref`, `thread_safe_pointer`, `deprecated`, `type`, `java_array` |
| `fory.enum` | `id`, `alias`, `deprecated` |

Each option means the same as in the [Fory protobuf IDL docs](https://fory.apache.org/docs/compiler/protobuf-idl).
Standard options (`java_package`, `go_package`, …) are read from the descriptors,
including managed-mode overrides.

### Migrating from foryc syntax

foryc reads `(fory).ref` without a declaration. protoc and buf need one extension
per options type, and a single `fory` extension cannot exist at file, message and
field level at the same time. That is why the syntax differs. Rewrite existing files with:

```bash
uv run protoc-gen-fory-migrate proto/**/*.proto          # rewrite in place
uv run protoc-gen-fory-migrate --check proto/**/*.proto  # CI: exit 1 if needed
```

The tool maps `(fory).x` to `(fory.file|message|field|enum).x` by position and
adds the import. Comments and strings are left alone.

## Things to know

- **Type references follow foryc's rules.** foryc resolves types without packages:
  a field of type `demo.common.Money` becomes `Money`. Two cases cannot be expressed
  in foryc, so the plugin reports them as errors (with file:line:column):
  - the same top-level type name in two imported packages;
  - a reference to a top-level type that is shadowed by a nested type of the same name.
- **One `.proto` per package for Python and Rust.** Their generators write one file
  per package. foryc reports a collision for Rust and overwrites the file for Python
  (types from the earlier file are lost). The plugin behaves the same way but warns
  in the Python case. Java's `<Package>ForyModule.java` is affected in the same way.
- **Imports that only provide custom options are ignored.** That covers files that
  extend `google.protobuf.*Options` and whose types your fields don't use, such as
  protovalidate or `google/api/annotations.proto`. They may be proto2 or editions.
- **Not supported in v1:** services/gRPC (skipped with a warning), proto2, editions,
  `extend` blocks (ignored), groups. Well-known types: `Timestamp`, `Duration` and
  `Any` map to Fory types. Others (e.g. wrappers) are rejected by foryc as unknown types.
- **foryc-only scalars** (`int8`, `int16`, `uint8`, `uint16`, `float16`) are not
  protobuf types and do not compile under buf.
- `buf breaking` checks protobuf wire rules, not Fory's schema evolution. It is a
  useful lower bound, but not a Fory compatibility check.

## CI for your project

[examples/github-actions/fory-codegen.yml](examples/github-actions/fory-codegen.yml)
runs `buf format`, `lint`, `breaking`, `generate` and fails if checked-in generated code is stale.

## Development

```bash
uv sync                   # venv with dev dependencies
uv run pytest             # unit, adapter, golden tests (needs buf on PATH)
uv run mypy
buf generate              # after changing proto/fory/options.proto
scripts/ci/compile.sh python && scripts/ci/roundtrip.sh python python
```

Layout:

| Path | |
|---|---|
| `proto/fory/options.proto` | option declarations (buf module) |
| `src/protoc_gen_fory/plugin.py` | CodeGeneratorRequest → CodeGeneratorResponse |
| `src/protoc_gen_fory/adapter.py` | FileDescriptorProto → foryc's `ProtoSchema` |
| `src/protoc_gen_fory/options.py` | descriptor options → foryc's option dict |
| `src/protoc_gen_fory/generate.py` | runs foryc's compile pipeline on the adapted schemas |
| `src/protoc_gen_fory/migrate.py` | `(fory).x` → `(fory.<level>).x` |
| `tests/test_golden.py` | plugin output == foryc output, per fixture and language |
| `tests/e2e/` | generated code against the Fory runtimes (compile + roundtrip) |

CI, build versions and the release process are described in [.github/CI.md](.github/CI.md).
Changes are listed in [CHANGELOG.md](CHANGELOG.md).
