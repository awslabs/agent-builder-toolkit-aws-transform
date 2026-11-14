#!/usr/bin/env python3
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Fail when a tracked file holds a non-public reference or an AWS access key ID.

Usage:
    python scripts/check_public_refs.py              # scan every tracked file
    python scripts/check_public_refs.py --self-test  # run the rules over known samples

Exit status is 0 when clean and 1 on a hit or a failed sample. A git or read
error raises, so the check cannot pass on a scan that did not run.
"""

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Iterator, NamedTuple, Optional


class Rule(NamedTuple):
    name: str
    pattern: re.Pattern[str]
    # Searched in each match of `pattern`; a match it finds is not reported.
    allowed: Optional[re.Pattern[str]] = None


# The host and email patterns start with a lookbehind for the characters they
# then repeat, so a match can start only at the start of a run of them. That
# keeps the scan linear on files with very long runs (minified or encoded data).
RULES = (
    # Hosts under amazon.com, amazon.dev, aws.dev, a2z.com and a2z.org, except the public
    # aws.amazon.com sites and the product API endpoints. "}" and ">" catch a host whose
    # leading label is a template placeholder.
    Rule(
        "host",
        re.compile(
            r"(?<![a-z0-9.-])[a-z0-9.-]*[a-z0-9}>]"
            r"(?:[.-]amazon\.(?:com|dev)|\.aws\.dev|\.a2z\.(?:com|org))",
            re.IGNORECASE,
        ),
        re.compile(r"(?:^|\.)(?:[a-z0-9-]+\.)*(?:aws\.amazon\.com|elastic-gumby\.ai\.aws\.dev)$", re.IGNORECASE),
    ),
    # Addresses at amazon.com and amazon.dev, except the public code-of-conduct contact.
    Rule(
        "email",
        re.compile(r"(?<![a-z0-9._%+-])[a-z0-9._%+-]+@amazon\.(?:com|dev)", re.IGNORECASE),
        re.compile(r"^opensource-codeofconduct@amazon\.com$", re.IGNORECASE),
    ),
    Rule("chat link", re.compile(r"slack\.com/archives", re.IGNORECASE)),
    # Long-term (AKIA) and temporary (ASIA) key IDs, except the documented ...EXAMPLE placeholders.
    Rule("access key", re.compile(r"(?:AKIA|ASIA)[0-9A-Z]{16}"), re.compile(r"EXAMPLE$")),
)

# "|" splits each sample so that this file passes its own check.
FLAGGED_SAMPLES = tuple(
    sample.replace("|", "")
    for sample in (
        "https://made-up.ama|zon.com/page",
        "made-up-ama|zon.com",
        "made-up.ama|zon.dev",
        "made-up.aw|s.dev",
        "{stage}.aw|s.dev",
        "<host>.ama|zon.com",
        "made-up.a2|z.com",
        "made-up.a2|z.org",
        "first.last@ama|zon.com",
        "first.last+tag@ama|zon.dev",
        "sla|ck.com/archives/C0000000000",
        "AKI|A0123456789ABCDEF",
        "ASI|A0123456789ABCDEF",
    )
)
ALLOWED_SAMPLES = (
    "Copyright Amazon.com, Inc. or its affiliates.",
    "https://docs.aws.amazon.com/bedrock/",
    "{region}.console.aws.amazon.com",
    "iad.prod.agenticapi.elastic-gumby.ai.aws.dev",
    "opensource-codeofconduct@amazon.com",
    "first.last@example.com",
    "AKIAIOSFODNN7EXAMPLE",
)


def find_refs(text: str) -> Iterator[tuple[int, str, str]]:
    """Yield (1-based line number, rule name, matched text) for each match in `text` that its rule does not allow."""
    for rule in RULES:
        for match in rule.pattern.finditer(text):
            if not (rule.allowed and rule.allowed.search(match[0])):
                yield text.count("\n", 0, match.start()) + 1, rule.name, match[0]


def scan_tracked_files() -> list[str]:
    """Return one "path:line: rule: match" entry per hit in the tracked files of the current repository.

    Covers the whole repository from any directory in it. Binary files are scanned as text.
    """
    listing = subprocess.run(["git", "ls-files", "-z", ":/"], check=True, stdout=subprocess.PIPE).stdout
    hits: list[str] = []
    for name in filter(None, os.fsdecode(listing).split("\0")):
        path = Path(name)
        # A submodule, or a file deleted from the working tree, has no content here.
        if path.is_file():
            text = path.read_text(encoding="utf-8", errors="replace")
            hits += [f"{name}:{line}: {rule}: {ref}" for line, rule, ref in find_refs(text)]
    return hits


def failed_samples() -> list[str]:
    """Return one entry per sample that the rules judge wrongly."""
    return [f"not flagged: {sample}" for sample in FLAGGED_SAMPLES if not any(find_refs(sample))] + [
        f"flagged: {sample}" for sample in ALLOWED_SAMPLES if any(find_refs(sample))
    ]


def main(argv: Optional[list[str]] = None) -> int:
    """Run the scan, or the self-test, and return the process exit status."""
    parser = argparse.ArgumentParser(description="Fail when a tracked file holds a non-public reference.")
    parser.add_argument("--self-test", action="store_true", help="run the rules over known samples instead")
    self_test = parser.parse_args(argv).self_test
    problems = failed_samples() if self_test else scan_tracked_files()
    if problems:
        summary = (
            "The rules judge these samples wrongly"
            if self_test
            else "Non-public references or access keys found. Remove them before merging"
        )
        print(f"::error::{summary}:", *problems, sep="\n")
        return 1
    print("All samples are judged correctly." if self_test else "No non-public references or access keys found.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
