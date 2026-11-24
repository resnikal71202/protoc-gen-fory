"""Plugin parameters from ``CodeGeneratorRequest.parameter``.

buf passes ``opt:`` entries from buf.gen.yaml as a comma-separated list,
e.g. ``lang=go,go_module=example.com/app``.
"""

from __future__ import annotations

from dataclasses import dataclass

# Languages with golden, compile and roundtrip coverage in v1.
SUPPORTED_LANGUAGES = ("java", "python", "go", "rust", "javascript")

_GO_NESTED_TYPE_STYLES = ("underscore", "camelcase")


class ParameterError(ValueError):
    """Invalid plugin parameter (reported to buf as a user error)."""


@dataclass(frozen=True)
class Params:
    lang: str
    # Go: module path of the output root, like a go.mod next to foryc's --go_out.
    go_module: str | None = None
    # Go: same as `foryc --go_nested_type_style`.
    go_nested_type_style: str | None = None


def parse_params(raw: str) -> Params:
    values: dict[str, str] = {}
    for item in raw.split(","):
        item = item.strip()
        if not item:
            continue
        key, sep, value = item.partition("=")
        key = key.strip()
        if not sep or not value.strip():
            raise ParameterError(f"parameter {key!r} needs a value (expected {key}=...)")
        if key in values:
            raise ParameterError(f"parameter {key!r} given more than once")
        values[key] = value.strip()

    known = {"lang", "go_module", "go_nested_type_style"}
    unknown = sorted(set(values) - known)
    if unknown:
        raise ParameterError(
            f"unknown parameter(s): {', '.join(unknown)} "
            f"(known: {', '.join(sorted(known))})"
        )

    lang = values.get("lang")
    if lang is None:
        raise ParameterError(
            "missing required parameter 'lang' "
            f"(add `opt: lang=<{'|'.join(SUPPORTED_LANGUAGES)}>` in buf.gen.yaml)"
        )
    lang = lang.lower()
    if lang not in SUPPORTED_LANGUAGES:
        raise ParameterError(
            f"unsupported lang {lang!r} (supported: {', '.join(SUPPORTED_LANGUAGES)})"
        )

    go_module = values.get("go_module")
    go_style = values.get("go_nested_type_style")
    if lang != "go" and (go_module or go_style):
        raise ParameterError("go_module and go_nested_type_style require lang=go")
    if go_style is not None and go_style not in _GO_NESTED_TYPE_STYLES:
        raise ParameterError(
            f"go_nested_type_style must be one of {', '.join(_GO_NESTED_TYPE_STYLES)}"
        )

    return Params(lang=lang, go_module=go_module, go_nested_type_style=go_style)
