# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Tests for the best-effort credential redaction in agent_builder_sdk.util.redact."""

import json
from typing import Callable

import pytest

from agent_builder_sdk.util.redact import REDACTED, scrub


def test_access_key_ids_are_redacted() -> None:
    assert scrub("key AKIAIOSFODNN7EXAMPLE and ASIAIOSFODNN7EXAMPLE") == f"key {REDACTED} and {REDACTED}"


def test_json_secret_is_redacted() -> None:
    out = scrub('{"aws_secret_access_key": "abcdEFGH1234/xyz", "region": "us-east-1"}')
    assert "abcdEFGH1234" not in out
    assert '"region": "us-east-1"' in out


def test_env_session_token_is_redacted() -> None:
    out = scrub("AWS_REGION=us-east-1\nAWS_SESSION_TOKEN=IQoJb3JpZ2luX2VjEXAMPLE\n")
    assert "IQoJb3JpZ2lu" not in out
    assert "AWS_REGION=us-east-1" in out


def test_yaml_password_is_redacted() -> None:
    assert "hunter2hunter2" not in scrub("db:\n  password: hunter2hunter2\n")


def test_exact_secrets_are_redacted() -> None:
    assert scrub(
        "value=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY ok", ["wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY", "", "short"]
    ) == (f"value={REDACTED} ok")


def test_an_overlapping_exact_secret_is_redacted_whole() -> None:
    assert scrub("tok=abcdefgh12345678", ["abcdefgh", "abcdefgh12345678"]) == f"tok={REDACTED}"


@pytest.mark.parametrize("line", ["aws_secret_access_key = wJalrXUtnFEMI/K7MDENG", 'password = "s3cr3t value"'])
def test_an_ini_secret_with_spaces_around_the_equals_sign_is_redacted(line: str) -> None:
    out = scrub(f"[default]\naws_access_key_id = AKIAIOSFODNN7EXAMPLE\n{line}\n")
    assert "AKIAIOSFODNN7EXAMPLE" not in out and "wJalrXUtnFEMI" not in out and "s3cr3t" not in out
    assert out.startswith("[default]\n")


def test_an_exported_secret_is_redacted() -> None:
    assert "abcdefgh12345678" not in scrub("export AWS_SECRET_ACCESS_KEY=abcdefgh12345678\n")


@pytest.mark.parametrize("key", ["client_secret", "api_secret", "api_key"])
def test_client_and_api_secrets_are_redacted(key: str) -> None:
    assert "s3cr3t-value-1" not in scrub(f'{{"{key}": "s3cr3t-value-1"}}')


def test_an_exact_secret_of_the_minimum_length_is_redacted() -> None:
    assert scrub("key 8charsAB end", ["8charsAB"]) == f"key {REDACTED} end"


def test_every_copy_of_an_exact_secret_is_redacted() -> None:
    secret = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
    assert scrub(f"{secret}\n{secret}", [secret]) == f"{REDACTED}\n{REDACTED}"


@pytest.mark.parametrize("line", ["API_SECRET=supersecretvalue123", "password: hunter2hunter2hunter2"])
@pytest.mark.parametrize(
    "shape",
    [
        lambda text: str([{"type": "text", "text": text}]),
        lambda text: str([{"type": "resource", "resource": {"uri": "f", "text": text}}]),
        lambda text: '{"result": {"content": [{"text": "%s"}]}}' % text.replace("\n", "\\n"),
    ],
    ids=["text block repr", "resource block repr", "JSON"],
)
def test_a_secret_on_the_first_line_of_a_quoted_text_is_redacted(line: str, shape: Callable[[str], str]) -> None:
    out = scrub(shape(f"{line}\nnext"))
    assert "supersecretvalue123" not in out and "hunter2hunter2hunter2" not in out
    assert REDACTED in out and "next" in out


@pytest.mark.parametrize(
    "line",
    [
        'API_SECRET="supersecretvalue123"',
        "API_SECRET='supersecretvalue123'",
        'export API_SECRET="supersecretvalue123"',
        "password: 'supersecretvalue123'",
        "password: supersecretvalue123 # prod",
        "password: supersecretvalue123\t# prod",
    ],
    ids=[
        "env double-quoted",
        "env single-quoted",
        "export quoted",
        "yaml quoted",
        "yaml #",
        "yaml tab #",
    ],
)
@pytest.mark.parametrize("before", ["", "PORT=8080\n"], ids=["first line", "later line"])
@pytest.mark.parametrize(
    "shape",
    [
        lambda text: text,
        lambda text: str([{"type": "text", "text": text}]),
        lambda text: str([{"type": "resource", "resource": {"uri": "f", "text": text}}]),
        lambda text: json.dumps({"result": {"content": [{"text": text}]}}),
    ],
    ids=["text", "text block repr", "resource block repr", "JSON"],
)
def test_a_quoted_secret_and_a_yaml_secret_before_a_comment_are_redacted(
    line: str, before: str, shape: Callable[[str], str]
) -> None:
    out = scrub(shape(f"{before}{line}\nnext"))
    assert "supersecretvalue123" not in out
    assert REDACTED in out and "next" in out


@pytest.mark.parametrize("line", ["API_SECRET=supersecretvalue123", "password: hunter2hunter2hunter2"])
@pytest.mark.parametrize(
    "shape",
    [
        lambda text: str([{"type": "text", "text": text}]),
        lambda text: str([{"type": "resource", "resource": {"uri": "f", "text": text}}]),
    ],
    ids=["text block repr", "resource block repr"],
)
def test_a_secret_on_the_first_line_of_a_double_quoted_repr_is_redacted(line: str, shape: Callable[[str], str]) -> None:
    # repr() quotes a text that holds a ' with ", so the first line follows ': " there.
    out = scrub(shape(f"{line}\n# it's the prod key\n"))
    assert "supersecretvalue123" not in out and "hunter2hunter2hunter2" not in out
    assert REDACTED in out and "prod key" in out


_ENV_FILE = "API_SECRET=supersecretvalue123\n"
_PRINTED_REPR = "=== app.env ===\n" + repr(_ENV_FILE) + "\n"


@pytest.mark.parametrize(
    "text",
    [
        _PRINTED_REPR,
        str([{"type": "text", "text": _PRINTED_REPR}]),
        repr(_ENV_FILE),
        "=== x ===\n" + repr("API_SECRET=supersecretvalue123 it's\n"),
    ],
    ids=["printed repr", "printed repr in a tool result", "repr at text start", "double-quoted repr"],
)
def test_a_secret_on_the_first_line_of_a_repr_that_starts_a_line_is_redacted(text: str) -> None:
    # print(repr(f.read())) puts the repr's opening quote right after a newline.
    out = scrub(text)
    assert "supersecretvalue123" not in out
    assert REDACTED in out


@pytest.mark.parametrize(
    "text",
    [
        repr(_ENV_FILE.encode()),
        str(["API_SECRET=supersecretvalue123\n", "ordinary\n"]),
        str(("ordinary\n", "API_SECRET=supersecretvalue123\n")),
        '"""API_SECRET=supersecretvalue123"""',
        "f'API_SECRET=supersecretvalue123\\n'",
        "rb'password: supersecretvalue123'",
        "=== app.env ===\n\\'API_SECRET=supersecretvalue123\\n\\'",
        str([{"type": "text", "text": repr(["password: supersecretvalue123\n"])}]),
        "API_SECRET={supersecretvalue123}",
    ],
    ids=[
        "bytes repr",
        "readlines() list",
        "tuple, second item",
        "triple-quoted",
        "f-string",
        "rb prefix, yaml",
        "escaped quote after a newline",
        "list in a tool result",
        "unquoted value in braces",
    ],
)
def test_a_secret_right_after_the_opening_quote_of_a_literal_is_redacted(text: str) -> None:
    out = scrub(text)
    assert "supersecretvalue123" not in out
    assert REDACTED in out


@pytest.mark.parametrize(
    "text",
    [
        'print(f"password: {password}")',
        "keys = ['api_key', 'password', 'session_token']",
        "input('password: ')",
        "Use 'API_SECRET=<your secret>' in .env",
        "=== list ===\n'api_key=short'",
    ],
)
def test_ordinary_text_inside_quotes_is_untouched(text: str) -> None:
    assert scrub(text) == text


@pytest.mark.parametrize(
    "text",
    [
        "print(f'API_SECRET={secret}')",
        "print('password: not-a-secret')",
        "'API_SECRET=replace-me'",
    ],
)
def test_a_quoted_example_or_placeholder_is_redacted_too(text: str) -> None:
    # Any quote starts a line, so these are redacted as well: the safe direction.
    assert REDACTED in scrub(text)


# Named values whose quoted secret holds a # or an escaped quote: the whole value must go.
_DELIMITED_LINES = [
    'password: "abc12345#tail-secret-end"',
    'password: "abc12345\\"tail-secret-end"',
    'API_SECRET="abc12345#tail-secret-end"',
    'API_SECRET="abc12345\\"tail-secret-end"',
    json.dumps({"api_key": "abc12345#tail-secret-end"}),
    json.dumps({"api_key": 'abc12345"tail-secret-end'}),
]


@pytest.mark.parametrize(
    "line",
    _DELIMITED_LINES,
    ids=[
        "yaml #",
        "yaml escaped quote",
        "env #",
        "env escaped quote",
        "json #",
        "json escaped quote",
    ],
)
@pytest.mark.parametrize(
    "shape",
    [
        lambda text: text,
        lambda text: str([{"type": "text", "text": text}]),
        lambda text: str([{"type": "resource", "resource": {"uri": "f", "text": text}}]),
    ],
    ids=["text", "text block repr", "resource block repr"],
)
def test_a_quoted_secret_holding_a_hash_or_an_escaped_quote_is_redacted_whole(
    line: str, shape: Callable[[str], str]
) -> None:
    out = scrub(shape(f"{line}\nnext"))
    suffixes = ["tail-secret-end"[i:] for i in range(len("tail-secret-end") - 4)]
    assert not [suffix for suffix in suffixes if suffix in out], out
    assert REDACTED in out and "next" in out


@pytest.mark.parametrize(
    "shape",
    [lambda text: str([{"type": "text", "text": text}]), lambda text: json.dumps({"text": text})],
    ids=["repr", "JSON"],
)
@pytest.mark.parametrize("text", ["ok\npassword: hunter2hunter2hunter2", "password: hunter2hunter2hunter2"])
def test_a_yaml_secret_on_the_last_line_of_a_quoted_text_is_redacted(text: str, shape: Callable[[str], str]) -> None:
    # A file with no trailing newline: its last line ends at the closing quote, not at \n.
    assert "hunter2hunter2hunter2" not in scrub(shape(text))


@pytest.mark.parametrize(
    "text",
    [r'password: "abc def gh\\"', r'API_SECRET="abc def gh\\"', r'{"password": "abc def gh\\"}'],
    ids=["yaml", "env", "json"],
)
def test_a_quoted_secret_that_ends_with_an_escaped_backslash_is_redacted(text: str) -> None:
    # _quoted's second branch: the closing quote follows an escaped backslash.
    assert "abc def" not in scrub(text)


def test_ordinary_output_is_untouched() -> None:
    text = (
        "sha256 9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08\n"
        "job 5369a1b2-3c4d-4e5f-8a9b-0c1d2e3f4a5b\n"
        '{"name": "report.pbix", "size": 1234}\n'
        "    password=payload.get('password')\n"
        "    api_key=config.get('api_key')\n"
        "set the api_key in the console\n"
        "short secret kept"
    )
    assert scrub(text, ["short"]) == text
