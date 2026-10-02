#!/usr/bin/env python3
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Generate type stubs for the TransformAgenticService from its service-2.json model.

Usage:
    python scripts/generate_stubs.py [--model PATH_TO_SERVICE_2_JSON] [--validate]

Requirements:
    pip install mypy-boto3-builder

What it does:
    1. Injects the service model into botocore's data dir (temporarily)
    2. Runs mypy-boto3-builder to generate type stubs
    3. Copies generated stubs into src/agent_builder_types/
    4. Cleans up the injected model and temp output dir

Flags:
    --model     Path to service-2.json (default: ~/.aws/models/transformagenticservice/2018-05-10/service-2.json)
    --validate  Only validate that current stubs match what would be generated (exit 1 if different)
"""

import argparse
import difflib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SERVICE_NAME = "transformagenticservice"
API_VERSION = "2018-05-10"
PACKAGE_MODULE = "agent_builder_types"
DEFAULT_MODEL = os.path.join(
    os.path.dirname(__file__), "..", "..", "sdk", "src", "agent_builder_sdk",
    "botocore_models", SERVICE_NAME, API_VERSION, "service-2.json"
)

# Files to copy from generated output to our package
STUB_FILES = [
    "__init__.py",
    "__init__.pyi",
    "client.py",
    "client.pyi",
    "literals.py",
    "literals.pyi",
    "paginator.py",
    "paginator.pyi",
    "type_defs.py",
    "type_defs.pyi",
]


def get_botocore_data_dir() -> Path:
    import botocore

    return Path(botocore.__file__).parent / "data"


def inject_model(model_path: Path, botocore_data: Path) -> Path:
    """Copy service model into botocore data dir. Returns the created dir."""
    target = botocore_data / SERVICE_NAME / API_VERSION
    target.mkdir(parents=True, exist_ok=True)
    shutil.copy2(model_path, target / "service-2.json")

    # Also copy paginators-1.json if it exists alongside the service model
    paginators = model_path.parent / "paginators-1.json"
    if paginators.exists():
        shutil.copy2(paginators, target / "paginators-1.json")

    return target.parent


def remove_model(botocore_data: Path) -> None:
    """Remove injected service model from botocore data dir."""
    target = botocore_data / SERVICE_NAME
    if target.exists():
        shutil.rmtree(target)


def generate(model_path: Path) -> Path:
    """Run mypy-boto3-builder and return path to generated module dir."""
    botocore_data = get_botocore_data_dir()
    injected = False

    # Check if model already exists in botocore data
    existing = botocore_data / SERVICE_NAME / API_VERSION / "service-2.json"
    if not existing.exists():
        inject_model(model_path, botocore_data)
        injected = True

    try:
        output_dir = Path(tempfile.mkdtemp(prefix="types-gen-"))

        # Find mypy_boto3_builder — prefer the installed command, fall back to python -m
        builder_cmd = shutil.which("mypy_boto3_builder")
        if builder_cmd:
            cmd = [builder_cmd]
        else:
            cmd = [sys.executable, "-m", "mypy_boto3_builder"]

        result = subprocess.run(
            cmd + [
                str(output_dir),
                "--product",
                "boto3-services",
                "-s",
                SERVICE_NAME,
                "--no-smart-version",
                "-b",
                "1.0.0",
            ],
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            print(f"mypy-boto3-builder failed:\n{result.stderr}", file=sys.stderr)
            sys.exit(1)

        generated_module = (
            output_dir
            / f"mypy_boto3_{SERVICE_NAME}_package"
            / f"mypy_boto3_{SERVICE_NAME}"
        )

        if not generated_module.exists():
            print(
                f"Expected output not found: {generated_module}", file=sys.stderr
            )
            sys.exit(1)

        return generated_module

    finally:
        if injected:
            remove_model(botocore_data)


COPYRIGHT_HEADER = """\
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""


def rewrite_imports(content: str) -> str:
    """Rewrite generated import paths to match our package structure."""
    content = content.replace(
        f"mypy_boto3_{SERVICE_NAME}", PACKAGE_MODULE
    )
    # Add copyright header if not present
    if not content.startswith("# Copyright"):
        content = COPYRIGHT_HEADER + content
    return content


def copy_stubs(generated_module: Path, target_dir: Path) -> None:
    """Copy and rewrite generated stubs into the package source."""
    for filename in STUB_FILES:
        src = generated_module / filename
        dst = target_dir / filename
        if src.exists():
            content = src.read_text()
            content = rewrite_imports(content)
            dst.write_text(content)
            print(f"  Updated: {filename}")
        else:
            print(f"  Skipped (not generated): {filename}")


def validate_stubs(generated_module: Path, target_dir: Path) -> bool:
    """Compare generated stubs against current stubs. Returns True if matching."""
    all_match = True
    for filename in STUB_FILES:
        src = generated_module / filename
        dst = target_dir / filename
        if not src.exists():
            continue
        if not dst.exists():
            print(f"  MISSING: {filename}")
            all_match = False
            continue

        generated_content = rewrite_imports(src.read_text())
        current_content = dst.read_text()

        if generated_content != current_content:
            print(f"  DIFFERS: {filename}")
            diff = difflib.unified_diff(
                current_content.splitlines(keepends=True),
                generated_content.splitlines(keepends=True),
                fromfile=f"current/{filename}",
                tofile=f"generated/{filename}",
                n=3,
            )
            # Show first 30 lines of diff
            for i, line in enumerate(diff):
                if i >= 30:
                    print("    ... (truncated)")
                    break
                print(f"    {line}", end="")
            all_match = False
        else:
            print(f"  OK: {filename}")

    return all_match


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--model",
        type=Path,
        default=Path(DEFAULT_MODEL),
        help=f"Path to service-2.json (default: {DEFAULT_MODEL})",
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        help="Only validate current stubs match generated output",
    )
    args = parser.parse_args()

    if not args.model.exists():
        print(f"Service model not found: {args.model}", file=sys.stderr)
        print(
            "Register it with: aws configure add-model --service-name "
            f"{SERVICE_NAME} --service-model file://{args.model}",
            file=sys.stderr,
        )
        sys.exit(1)

    # Verify service name in model
    with open(args.model) as f:
        model = json.load(f)
    endpoint_prefix = model["metadata"].get("endpointPrefix", "")
    if endpoint_prefix != SERVICE_NAME:
        print(
            f"Warning: model endpointPrefix is '{endpoint_prefix}', "
            f"expected '{SERVICE_NAME}'",
            file=sys.stderr,
        )

    print(f"Service: {model['metadata']['serviceFullName']}")
    print(f"Operations: {len(model['operations'])}, Shapes: {len(model['shapes'])}")
    print()

    # Generate
    print("Generating stubs...")
    generated_module = generate(args.model)

    # Target directory
    package_root = Path(__file__).parent.parent
    target_dir = package_root / "src" / PACKAGE_MODULE

    if args.validate:
        print("\nValidating against current stubs:")
        if validate_stubs(generated_module, target_dir):
            print("\nAll stubs match.")
            sys.exit(0)
        else:
            print("\nStubs are out of date. Run without --validate to regenerate.")
            sys.exit(1)
    else:
        print(f"\nCopying stubs to {target_dir}:")
        copy_stubs(generated_module, target_dir)
        print("\nDone. Review changes with: git diff")

    # Cleanup temp dir
    shutil.rmtree(generated_module.parent.parent, ignore_errors=True)


if __name__ == "__main__":
    main()
