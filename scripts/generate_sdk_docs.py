#!/usr/bin/env python3
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Generate sdk_docs.json from the SDK source package.

Extracts public classes, methods, and functions with their signatures,
parameters, and docstrings using AST parsing. The output is consumed by
the MCP server's BM25 knowledge base for developer search.

Usage:
    python scripts/generate_sdk_docs.py [--sdk-path PATH] [--output PATH]

Defaults:
    --sdk-path: packages/sdk/src/agent_builder_sdk
    --output:   packages/mcp-server/src/agent_builder_mcp/knowledge/data/sdk_docs.json
"""

import ast
import json
import sys
from pathlib import Path
from typing import Optional

DEFAULT_SDK_PATH = Path("packages/sdk/src/agent_builder_sdk")
DEFAULT_OUTPUT_PATH = Path("packages/mcp-server/src/agent_builder_mcp/knowledge/data/sdk_docs.json")



def _get_annotation_str(node: Optional[ast.expr]) -> str:
    """Convert an AST annotation node to a readable string."""
    if node is None:
        return ""
    return ast.unparse(node)


def _get_default_str(node: Optional[ast.expr]) -> str:
    """Convert an AST default value node to a readable string."""
    if node is None:
        return ""
    return ast.unparse(node)


def _get_docstring(node: ast.AST) -> str:
    """Extract docstring from a class or function node."""
    return ast.get_docstring(node) or ""


def _format_signature(func: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    """Build a human-readable signature string from a function definition."""
    args = func.args
    parts: list[str] = []

    posonlyargs = getattr(args, "posonlyargs", [])
    all_positional = posonlyargs + args.args
    num_defaults = len(args.defaults)
    num_positional = len(all_positional)

    for i, arg in enumerate(all_positional):
        name = arg.arg
        if name in ("self", "cls"):
            continue
        ann = _get_annotation_str(arg.annotation)
        default_idx = i - (num_positional - num_defaults)
        if default_idx >= 0:
            default = _get_default_str(args.defaults[default_idx])
            if ann:
                parts.append(f"{name}: {ann} = {default}")
            else:
                parts.append(f"{name}={default}")
        else:
            if ann:
                parts.append(f"{name}: {ann}")
            else:
                parts.append(name)

    if posonlyargs:
        parts.insert(len(posonlyargs), "/")

    if args.vararg:
        ann = _get_annotation_str(args.vararg.annotation)
        parts.append(f"*{args.vararg.arg}: {ann}" if ann else f"*{args.vararg.arg}")
    elif args.kwonlyargs:
        parts.append("*")

    for i, arg in enumerate(args.kwonlyargs):
        name = arg.arg
        ann = _get_annotation_str(arg.annotation)
        default = (
            _get_default_str(args.kw_defaults[i])
            if i < len(args.kw_defaults) and args.kw_defaults[i]
            else ""
        )
        if default:
            if ann:
                parts.append(f"{name}: {ann} = {default}")
            else:
                parts.append(f"{name}={default}")
        else:
            if ann:
                parts.append(f"{name}: {ann}")
            else:
                parts.append(name)

    if args.kwarg:
        ann = _get_annotation_str(args.kwarg.annotation)
        parts.append(f"**{args.kwarg.arg}: {ann}" if ann else f"**{args.kwarg.arg}")

    ret = _get_annotation_str(func.returns)
    sig = f"({', '.join(parts)})"
    if ret:
        sig += f" -> {ret}"
    return sig


def _extract_parameters(func: ast.FunctionDef | ast.AsyncFunctionDef, docstring: str) -> list[dict]:
    """Extract parameter details with types, defaults, and descriptions from docstring."""
    args = func.args
    params: list[dict] = []

    # Parse docstring for parameter descriptions (Google-style Args: section)
    param_descs: dict[str, str] = {}
    if docstring:
        in_args = False
        current_param = ""
        for line in docstring.split("\n"):
            stripped = line.strip()
            if stripped.lower().startswith(("args:", "parameters:")):
                in_args = True
                continue
            if in_args:
                if stripped.lower().startswith(("returns:", "raises:", "yields:", "note:", "example")):
                    in_args = False
                    continue
                if ": " in stripped and not stripped.startswith(" "):
                    pname = stripped.split(":", 1)[0].strip().split("(")[0].strip()
                    pdesc = stripped.split(":", 1)[1].strip()
                    current_param = pname
                    param_descs[pname] = pdesc
                elif current_param and stripped:
                    param_descs[current_param] += " " + stripped

    all_positional = getattr(args, "posonlyargs", []) + args.args
    num_defaults = len(args.defaults)
    num_positional = len(all_positional)

    for i, arg in enumerate(all_positional):
        name = arg.arg
        if name in ("self", "cls"):
            continue
        ann = _get_annotation_str(arg.annotation)
        default_idx = i - (num_positional - num_defaults)
        default = _get_default_str(args.defaults[default_idx]) if default_idx >= 0 else None
        params.append({
            "name": name,
            "type": ann,
            "default": default,
            "required": default is None,
            "description": param_descs.get(name, ""),
        })

    for i, arg in enumerate(args.kwonlyargs):
        name = arg.arg
        ann = _get_annotation_str(arg.annotation)
        default = (
            _get_default_str(args.kw_defaults[i])
            if i < len(args.kw_defaults) and args.kw_defaults[i]
            else None
        )
        params.append({
            "name": name,
            "type": ann,
            "default": default,
            "required": default is None,
            "description": param_descs.get(name, ""),
        })

    return params


def _build_description_from_params(params: list[dict]) -> str:
    """Build a searchable description block from parameter details."""
    if not params:
        return ""
    lines = ["Parameters:"]
    for p in params:
        req = "required" if p["required"] else f"default={p['default']}"
        type_str = f": {p['type']}" if p["type"] else ""
        desc_str = f" - {p['description']}" if p["description"] else ""
        lines.append(f"  {p['name']}{type_str} ({req}){desc_str}")
    return "\n".join(lines)


def _extract_class_methods(cls_node: ast.ClassDef) -> list[dict]:
    """Extract public method signatures from a class."""
    methods: list[dict] = []
    for node in ast.iter_child_nodes(cls_node):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name.startswith("_") and node.name != "__init__":
                continue
            sig = _format_signature(node)
            prefix = "async " if isinstance(node, ast.AsyncFunctionDef) else ""
            methods.append({
                "name": node.name,
                "signature": f"{prefix}{node.name}{sig}",
                "docstring": _get_docstring(node),
            })
    return methods


def extract_file(filepath: Path, sdk_path: Path) -> list[dict]:
    """Extract all classes and top-level functions from a Python file."""
    try:
        source = filepath.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(filepath))
    except (SyntaxError, UnicodeDecodeError):
        return []

    rel_path = str(filepath.relative_to(sdk_path.parent))
    module = str(filepath.relative_to(sdk_path.parent)).replace("/", ".").removesuffix(".py").removesuffix(".__init__")
    entries: list[dict] = []

    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.ClassDef):
            if node.name.startswith("_"):
                continue
            docstring = _get_docstring(node)
            methods = _extract_class_methods(node)

            # Constructor signature
            init_sig = ""
            init_params: list[dict] = []
            for method in methods:
                if method["name"] == "__init__":
                    init_sig = method["signature"].replace("__init__", node.name)
                    for child in ast.iter_child_nodes(node):
                        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) and child.name == "__init__":
                            init_params = _extract_parameters(child, _get_docstring(child) or docstring)
                    break

            # Method summary
            method_sigs = [m["signature"] for m in methods if m["name"] != "__init__"]

            # Build rich description
            desc_parts: list[str] = []
            bases = [ast.unparse(base) for base in node.bases]
            if bases:
                desc_parts.append(f"Extends: {', '.join(bases)}")
            if init_params:
                desc_parts.append(_build_description_from_params(init_params))
            if method_sigs:
                desc_parts.append("Methods:\n" + "\n".join(f"  {s}" for s in method_sigs))

            entries.append({
                "name": node.name,
                "kind": "class",
                "file": rel_path,
                "module": module,
                "docstring": docstring,
                "signature": init_sig or f"{node.name}()",
                "description": "\n\n".join(desc_parts),
            })

            # Emit public methods as separate entries for searchability
            for m in methods:
                if m["name"] == "__init__":
                    continue
                entries.append({
                    "name": f"{node.name}.{m['name']}",
                    "kind": "method",
                    "file": rel_path,
                    "module": module,
                    "docstring": m["docstring"],
                    "signature": m["signature"],
                })

        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name.startswith("_"):
                continue
            docstring = _get_docstring(node)
            sig = _format_signature(node)
            params = _extract_parameters(node, docstring)
            prefix = "async " if isinstance(node, ast.AsyncFunctionDef) else ""

            entries.append({
                "name": node.name,
                "kind": "function",
                "file": rel_path,
                "module": module,
                "docstring": docstring,
                "signature": f"{prefix}{node.name}{sig}",
                "description": _build_description_from_params(params),
            })

    return entries


def extract_sdk(sdk_path: Path) -> list[dict]:
    """Walk the SDK package and extract documentation from all Python files."""
    all_entries: list[dict] = []
    for pyfile in sorted(sdk_path.rglob("*.py")):
        if pyfile.name == "__init__.py" and pyfile.stat().st_size < 50:
            continue
        entries = extract_file(pyfile, sdk_path)
        all_entries.extend(entries)
    return all_entries


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Generate sdk_docs.json from SDK source")
    parser.add_argument(
        "--sdk-path",
        type=Path,
        default=DEFAULT_SDK_PATH,
        help="Path to agent_builder_sdk package directory",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_PATH,
        help="Output JSON path",
    )
    args = parser.parse_args()

    if not args.sdk_path.is_dir():
        print(f"ERROR: SDK path does not exist: {args.sdk_path}", file=sys.stderr)
        return 1

    entries = extract_sdk(args.sdk_path)

    # Sort by file then name for stable, reviewable diffs
    entries.sort(key=lambda e: (e.get("file", ""), e.get("name", "")))

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(entries, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    # Summary
    kinds: dict[str, int] = {}
    for e in entries:
        k = e.get("kind", "unknown")
        kinds[k] = kinds.get(k, 0) + 1

    print(f"Generated {args.output}")
    print(f"  {len(entries)} entries: {', '.join(f'{k}={v}' for k, v in sorted(kinds.items()))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
