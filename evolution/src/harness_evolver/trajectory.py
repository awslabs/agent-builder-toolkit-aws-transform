# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import dataclasses
import datetime as _dt
import json
from pathlib import Path
from typing import Any


def serialize_message(msg: Any) -> dict:
    """Best-effort JSON-serializable form of a claude_agent_sdk message."""
    if dataclasses.is_dataclass(msg):
        try:
            return {"type": type(msg).__name__, **dataclasses.asdict(msg)}
        except Exception:
            pass
    if isinstance(msg, dict):
        return {"type": msg.get("type", "dict"), **{k: _coerce(v) for k, v in msg.items()}}
    return {"type": type(msg).__name__, "repr": repr(msg)}


def _coerce(v: Any) -> Any:
    if dataclasses.is_dataclass(v):
        try:
            return dataclasses.asdict(v)
        except Exception:
            return repr(v)
    if isinstance(v, (list, tuple)):
        return [_coerce(x) for x in v]
    if isinstance(v, dict):
        return {k: _coerce(x) for k, x in v.items()}
    if isinstance(v, Path):
        return str(v)
    if isinstance(v, (str, int, float, bool)) or v is None:
        return v
    return repr(v)


class Trajectory:
    """Append-only JSONL log of evolver steps."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, **payload: Any) -> None:
        record = {
            "timestamp": _dt.datetime.now(_dt.timezone.utc).isoformat(),
            **{k: _coerce(v) for k, v in payload.items()},
        }
        with self.path.open("a") as f:
            f.write(json.dumps(record) + "\n")

    def recent(self, k: int = 5) -> list[dict]:
        if not self.path.exists():
            return []
        lines = self.path.read_text().splitlines()
        return [json.loads(ln) for ln in lines[-k:] if ln.strip()]

    def all(self) -> list[dict]:
        if not self.path.exists():
            return []
        return [json.loads(ln) for ln in self.path.read_text().splitlines() if ln.strip()]
