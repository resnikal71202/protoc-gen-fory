import pytest

from protoc_gen_fory.params import ParameterError, Params, parse_params


def test_lang_only() -> None:
    assert parse_params("lang=java") == Params(lang="java")


def test_lang_is_case_insensitive_and_whitespace_tolerant() -> None:
    assert parse_params(" lang = Rust , ") == Params(lang="rust")


def test_go_parameters() -> None:
    assert parse_params("lang=go,go_module=example.com/app,go_nested_type_style=camelcase") == Params(
        lang="go", go_module="example.com/app", go_nested_type_style="camelcase"
    )


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        ("", "missing required parameter 'lang'"),
        ("lang=cobol", "unsupported lang 'cobol'"),
        ("lang=cpp", "unsupported lang 'cpp'"),
        ("lang", "needs a value"),
        ("lang=java,lang=go", "more than once"),
        ("lang=java,foo=1", "unknown parameter(s): foo"),
        ("lang=java,go_module=x", "require lang=go"),
        ("lang=go,go_nested_type_style=snake", "go_nested_type_style must be one of"),
    ],
)
def test_errors(raw: str, message: str) -> None:
    with pytest.raises(ParameterError, match=message.replace("(", r"\(").replace(")", r"\)")):
        parse_params(raw)
