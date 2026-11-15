# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Best-effort redaction of credentials from text that reaches the model or the logs.

The patterns catch AWS access-key ids and literal values of secret-named keys (``password``,
``api_key``, ``client_secret``, ``session_token`` and similar) in JSON, env-file and YAML text.
A secret under any other name, or in any other shape, passes unless the caller hands its exact
value to :func:`scrub`. Matching runs in time linear in the text length, and this module never
logs.
"""

import re
from typing import Iterable, Optional

# The key names whose literal value is a secret; a prefix such as ``aws_`` or ``db_`` may precede them.
_SECRET_KEY = (
    r"[a-z_]*?(?:client[_-]?secret|api[_-]?secret|api[_-]?key|secret[_-]?access[_-]?key"
    r"|session[_-]?token|password)"
)
# A line starts at a newline, at a literal \n (a tool result that is the repr of its content), or
# right after a quote: the opening quote of a repr, a bytes, f- or triple-quoted literal, a list of
# lines (readlines()) or a JSON string value, escaped or not, starts the first line it holds. Any
# quote counts, so a quoted example or placeholder (print('password: not-a-secret'),
# 'API_SECRET=replace-me', f'API_SECRET={secret}') is redacted too: the safe direction. A YAML
# value in braces or brackets (password: {secret}) is structure, not a value, so it is kept.
_LINE_START = r"(?:^|(?<=\\n)|(?<=[\"']))"
# A value may be quoted, and a repr or JSON escapes a quote inside a quoted text.
_QUOTE = r"\\?[\"']?"


def _quoted(group: str) -> str:
    """A quoted value read whole, so a # or an escaped quote inside it ends nothing: the opening quote
    (escaped by any backslashes in a repr or JSON), at least 8 characters or escapes but no line
    break, and the same closing quote."""
    # Linear, not exponential, on a long unclosed value: each step has one way to match.
    # 1. The first closing quote that no backslash escapes. Escaped backslashes count as pairs, as
    #    many characters as the value can have, and a quote checks only after a non-backslash.
    # 2. Else the last closing quote after two or more backslashes (a value that ends with an
    #    escaped backslash); a run of backslashes and the character after it is read whole there.
    return (
        rf"(?P<{group}>\\*[\"'])(?:"
        rf"(?:(?:(?<!\\)(?!\\n|(?P={group}))|(?<=\\))(?:\\\\|\\[^\\\n]|[^\\\n])){{8,}}?"
        rf"(?<!\\)(?P={group})"
        rf"|(?:(?!\\n|(?P={group}))(?=(?P<{group}_u>\\+[^\n]|[^\\\n]))(?P={group}_u))*"
        rf"\\\\+(?P={group}))"
    )


CREDENTIAL_RE = re.compile(
    r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"
    + r"|[\"']"
    + _SECRET_KEY
    + r"[\"']\s*:\s*(?:"
    + _quoted("json")
    + r"|[\"'][^\"'\s]{8,}[\"'])"
    # env file: unindented, so an indented keyword argument (password=payload.get(...)) is not one.
    + r"|"
    + _LINE_START
    + r"(?:export[ \t]+)?"
    + _SECRET_KEY
    + r"=(?:"
    + _quoted("env")
    + r"|"
    + _QUOTE
    + r"(?:(?!\\n)[^\s$`\"'(]){8,}"
    + _QUOTE
    + r")"
    # YAML: an unquoted value ends at the line's end, at a comment, or at the closing quote of the
    # repr or JSON string that holds the text (its last line has no newline). Limit: a value whose
    # opening quote is never closed falls back to this match, which ends at a # or a quote, so the
    # rest of it shows; read it to the line's end if such values turn up.
    + r"|"
    + _LINE_START
    + r"[ \t]*"
    + _SECRET_KEY
    + r":[ \t]+(?:"
    + _quoted("yaml")
    + r"|"
    + _QUOTE
    + r"(?:(?!\\n)[^\s$#\"'{}\[\]]){8,}"
    + _QUOTE
    + r"[ \t]*(?=$|\\n|#|[\"']))",
    re.IGNORECASE | re.MULTILINE,
)

REDACTED = "<redacted>"

# Shorter values are too likely to be ordinary text.
_MIN_SECRET_LEN = 8


def scrub(text: str, secrets: Optional[Iterable[str]] = None) -> str:
    """``text`` with every credential match and every exact ``secrets`` value replaced by
    <redacted>. A ``secrets`` value shorter than 8 characters is left in place."""
    for secret in secrets or ():
        if secret and len(secret) >= _MIN_SECRET_LEN:
            text = text.replace(secret, REDACTED)
    return CREDENTIAL_RE.sub(REDACTED, text)


# A presigned URL is a bearer credential, and S3 echoes the signing details (SignatureDoesNotMatch)
# or the session token itself (ExpiredToken) in an error reply.
_URL_RE = re.compile(r"https?://[^\s\"'<>]+")
_AMZ_PARAM_RE = re.compile(r"(X-Amz-[A-Za-z-]+)=[^&\s\"'<>]*", re.IGNORECASE)
# What follows is a reply raise_for_s3_error_response could not classify, kept raw.
_RAW_S3_REPLY_RE = re.compile(r"(S3 error: ).*", re.DOTALL)


def scrub_transfer_error(text: str) -> str:
    """``text`` of a failed artifact transfer, scrubbed, with no URL, X-Amz-* parameter value or raw
    S3 reply left in it."""
    text = _RAW_S3_REPLY_RE.sub(r"\1(reply removed)", text)
    text = _URL_RE.sub("(url removed)", text)
    return scrub(_AMZ_PARAM_RE.sub(r"\1=(removed)", text))
