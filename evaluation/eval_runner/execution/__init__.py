# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""ACP execution engine for eval_runner.

Drives an agent or skill under test through a multi-turn conversation via the
ACP protocol and grades the transcript with an LLM judge. Configured by
:class:`eval_runner.config.ExecutionConfig`; produces the transcript/grade
models defined in :mod:`eval_runner.models`.

(Was previously the standalone ``agent_eval_framework`` package; folded in as a
subpackage on consolidation.)
"""

from .bridge_runner import BridgeResponse, BridgeResponseStatus, BridgeRunner
from .runner import EvalCase, EvalOrchestrator

__all__ = [
    "BridgeResponse",
    "BridgeResponseStatus",
    "BridgeRunner",
    "EvalCase",
    "EvalOrchestrator",
]
