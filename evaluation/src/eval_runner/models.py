# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Core data models for the evaluation runner.

Two families of models live here:

- **Scoring models** (``ExecutionResult``, ``MetricResult``, ``EvaluationResult``):
  the result of running a test case and scoring it with metrics. These drive
  :class:`eval_runner.engine.EvaluationEngine`.
- **Execution models** (``TranscriptEntry``, ``EvalResult``, ``AssertionResult``,
  ``TokenUsage``, ``EvalGrade`` and their enums): the multi-turn ACP transcript
  and LLM-judge grade produced by :mod:`eval_runner.execution`. ``ACPAgent``
  flattens these into the scoring models above.

They were previously split across two packages; consolidated into one module.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

# ---------------------------------------------------------------------------
# Scoring models — run a test case, score it with metrics.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ExecutionResult:
    """Result of executing a single test case against an agent.

    ``turn_count`` is the number of conversation turns the run actually reached
    (``None`` when the backend does not track it). Compared against the test
    case's ``max_turns`` it tells whether a run ended on its own (completed)
    or was truncated by the turn budget — the signal the ``completeness``
    metric uses, since the ACP engine consumes its ``__DONE__`` sentinel before
    it ever lands in the transcript.
    """

    transcript: str
    output: str
    tool_calls: list[dict] = field(default_factory=list)
    duration_ms: int | None = None
    turn_count: int | None = None


@dataclass(frozen=True)
class MetricResult:
    """Result of evaluating a single metric on an execution."""

    metric_name: str
    score: float
    passed: bool
    details: dict = field(default_factory=dict)

    def __post_init__(self):
        if not (0.0 <= self.score <= 10.0):
            raise ValueError(f"score must be between 0 and 10, got {self.score}")


@dataclass
class EvaluationResult:
    """Aggregated result for one test case: execution + all metric scores."""

    test_case_id: str
    execution: ExecutionResult
    metric_results: list[MetricResult]

    @property
    def passed(self) -> bool:
        return all(m.passed for m in self.metric_results)


# ---------------------------------------------------------------------------
# Execution models — multi-turn ACP transcript + LLM-judge grade.
# Produced by eval_runner.execution (the ACP engine); flattened into the
# scoring models above by ACPAgent.
# ---------------------------------------------------------------------------


class TranscriptRole(str, Enum):
    """Role of a participant in the interaction transcript.

    Each entry in the transcript is tagged with a role indicating who or what
    produced the content.

    Values:
        AGENT: Text or content produced by the Agent agent.
        HUMAN: Text sent by the simulated human user.
        TOOL_CALL: A tool invocation initiated by the agent (ToolCallStart).
        TOOL_PROGRESS: Progress update on a running tool call (ToolCallProgress).
        PERMISSION: A tool permission request that was auto-approved.
        THOUGHT: Internal reasoning or chain-of-thought from the agent (AgentThoughtChunk).
    """

    AGENT = "agent"
    HUMAN = "human"
    TOOL_CALL = "tool_call"
    TOOL_PROGRESS = "tool_progress"
    PERMISSION = "permission"
    THOUGHT = "thought"


@dataclass
class TranscriptEntry:
    """A single entry in the multi-turn interaction transcript.

    Attributes:
        role: Who produced this entry (agent, human, tool, etc.).
        content: Human-readable text content of the entry. For tool calls, this is
            a formatted string like "tool_call: get_status (id=tc-123)".
        turn: The turn number (1-indexed) when this entry was produced. Turn 1 is
            the initial prompt, turn 2+ are subsequent interactions.
        timestamp: Unix timestamp when this entry was recorded. Defaults to
            current time at creation.
        raw: The original ACP SDK object (e.g., AgentMessageChunk, ToolCallStart)
            for detailed inspection during grading. None for human-generated entries.
    """

    role: TranscriptRole
    content: str
    turn: int = 0
    timestamp: float = field(default_factory=time.time)
    raw: Any = None


@dataclass
class TokenUsage:
    """Usage metrics for a scenario run.

    Note on sources: the kiro-cli ACP driver does **not** report token usage over
    the wire (the prompt result carries only ``stopReason``). The real usage
    signals are persisted in the agent's session file and are surfaced here:

    - ``credits`` — billed metering credits (the actual cost unit).
    - ``context_usage_percentage`` — peak context-window utilisation.
    - ``context_window_tokens`` — the model's context window size.

    The raw ``*_tokens`` fields are retained for forward-compatibility: a driver
    that does emit token counts (e.g. agent-cli, or a future kiro-cli) will
    populate them, and :meth:`add` still accumulates ACP-style usage dicts.

    Attributes:
        input_tokens: Total input tokens consumed (0 if the driver omits them).
        output_tokens: Total output tokens generated (0 if omitted).
        total_tokens: Total tokens (input + output).
        cached_read_tokens: Tokens served from cache (prompt caching).
        credits: Total billed metering credits across the run.
        context_usage_percentage: Peak context-window utilisation (0-100).
        context_window_tokens: Model context window size.
    """

    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    cached_read_tokens: int = 0
    credits: float = 0.0
    context_usage_percentage: float = 0.0
    context_window_tokens: int = 0

    def add(self, usage: dict[str, Any] | None) -> None:
        """Accumulate token counts from a bridge response usage dict.

        Args:
            usage: Raw usage dict from the bridge (camelCase keys from ACP).
                None values are safely ignored.
        """
        if not usage:
            return
        self.input_tokens += usage.get("inputTokens", 0) or 0
        self.output_tokens += usage.get("outputTokens", 0) or 0
        self.total_tokens += usage.get("totalTokens", 0) or 0
        self.cached_read_tokens += usage.get("cachedReadTokens", 0) or 0


@dataclass
class EvalResult:
    """Result of running a single eval scenario through the ACP pipeline.

    Produced by ``EvalOrchestrator.run_scenario()`` after the multi-turn interaction
    completes (execution only — no grading). Contains the full transcript for
    subsequent grading by the scoring engine, plus the runtime bookkeeping the
    orchestrator needs to assemble a final :class:`EvalGrade`.

    Attributes:
        eval_id: Unique identifier of the eval scenario (e.g., "full-dotnet-journey").
        transcript: Ordered list of all interaction entries (agent messages, human
            responses, tool calls, permissions, thoughts).
        turn_count: Total number of turns completed before the scenario ended.
        duration_seconds: Wall-clock time for the scenario execution phase.
        exit_code: 0 for success, non-zero for errors (timeout, subprocess failure).
        error: Human-readable error message if the scenario failed. None on success.
        token_usage: Aggregated token usage for the agent across all turns.
        work_dir: Path to the per-scenario work directory (bridge cwd for grading).
        log_paths: Bridge log paths keyed by agent role ("power", "scenario",
            "eval"). Mutated by ``grade()`` to record the judge's log.
        session_ids: ACP session IDs keyed by agent role, for log collection.
        run_timestamp: Timestamp string identifying this run (for result/log naming).
    """

    eval_id: str
    transcript: list[TranscriptEntry]
    turn_count: int
    duration_seconds: float
    exit_code: int = 0
    error: str | None = None
    token_usage: TokenUsage = field(default_factory=TokenUsage)
    work_dir: str | None = None
    log_paths: dict[str, str | None] = field(default_factory=dict)
    session_ids: dict[str, str | None] = field(default_factory=dict)
    run_timestamp: str = ""


class AssertionResultStatus(str, Enum):
    """Status of an individual assertion check.

    Values:
        PASS: The assertion was satisfied.
        FAIL: The assertion was not satisfied.
        NEEDS_REVIEW: The assertion could not be auto-graded (e.g., Bedrock call
            failed) and requires manual review.
    """

    PASS = "pass"
    FAIL = "fail"
    NEEDS_REVIEW = "needs_review"


@dataclass
class AssertionResult:
    """Result of evaluating a single assertion against a transcript.

    Produced by scorers (deterministic or LLM-as-judge) for each assertion
    defined in an eval scenario.

    Attributes:
        name: The assertion's unique name (e.g., "checks_auth", "no_auto_handle").
        result: Whether the assertion passed, failed, or needs manual review.
        evidence: Explanation of why the assertion passed or failed. For deterministic
            scorers, this includes what was found/not found. For LLM judge, this
            includes the model's reasoning.
        turn_number: The turn in which the relevant evidence was found, if applicable.
            None if the assertion evaluates the entire transcript.
    """

    name: str
    result: AssertionResultStatus
    evidence: str
    turn_number: int | None = None


@dataclass
class EvalGrade:
    """Graded result for a single eval scenario.

    Aggregates all assertion results for a scenario and provides an overall
    pass/fail verdict.

    Attributes:
        eval_id: Unique identifier of the eval scenario.
        passed: True only if every assertion has PASS status. Both FAIL and
            NEEDS_REVIEW count as failure.
        assertions: List of individual assertion results.
        duration_seconds: Wall-clock time for the entire scenario (from EvalResult).
        turn_count: Total number of turns completed (from EvalResult).
        token_usage: Aggregated token usage for the agent across all turns.
        work_dir: Path to the per-scenario work directory.
        tools_available: Tools listed by /tools command, or None if unavailable.
        log_files: List of collected log file paths.
    """

    eval_id: str
    passed: bool
    assertions: list[AssertionResult]
    duration_seconds: float
    turn_count: int
    token_usage: TokenUsage = field(default_factory=TokenUsage)
    transcript: list[TranscriptEntry] = field(default_factory=list)
    work_dir: str | None = None
    tools_available: str | None = None
    log_files: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dict."""
        return {
            "eval_id": self.eval_id,
            "passed": self.passed,
            "assertions": [
                {
                    "name": a.name,
                    "result": a.result.value,
                    "evidence": a.evidence,
                    "turn_number": a.turn_number,
                }
                for a in self.assertions
            ],
            "duration_seconds": self.duration_seconds,
            "turn_count": self.turn_count,
            "token_usage": {
                "input_tokens": self.token_usage.input_tokens,
                "output_tokens": self.token_usage.output_tokens,
                "total_tokens": self.token_usage.total_tokens,
                "cached_read_tokens": self.token_usage.cached_read_tokens,
                "credits": self.token_usage.credits,
                "context_usage_percentage": self.token_usage.context_usage_percentage,
                "context_window_tokens": self.token_usage.context_window_tokens,
            },
            "transcript": [
                {
                    "role": e.role.value,
                    "content": e.content,
                    "turn": e.turn,
                }
                for e in self.transcript
            ],
            "work_dir": self.work_dir,
            "tools_available": self.tools_available,
            "log_files": self.log_files,
        }
