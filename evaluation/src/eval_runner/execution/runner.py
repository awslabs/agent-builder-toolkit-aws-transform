# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Python orchestrator coordinating scenario agent and evaluation agent.

This module is the glue between the two eval agents. For each eval scenario, it:

1. Starts a bridge session for the scenario agent
2. Sends the scenario instructions (goal + guidance + initial prompt) to the
   scenario agent via the bridge
3. Collects the interaction transcript
4. Starts a separate bridge session for the evaluation agent
5. Sends the transcript + assertions to the eval agent
6. Parses the structured grade output
7. Cleans up both sessions

Architecture::

    EvalOrchestrator
        │
        ├── Scenario Agent session (persistent, multi-turn with agent under test)
        │   └── BridgeRunner → acp_bridge → agent-cli acp → Agent
        │
        └── Eval Agent session (single-turn, grades transcript)
            └── BridgeRunner → acp_bridge → agent-cli acp → LLM Judge

Usage::

    orchestrator = EvalOrchestrator(cwd="/tmp")
    grade = orchestrator.run_eval(scenario, cwd="/path/to/workspace")
    print(grade.passed, grade.assertions)
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from .agent_setup import install_agents
from .bridge_runner import BridgeResponse, BridgeResponseStatus, BridgeRunner
from .usage import usage_from_session_file
from ..config import ExecutionConfig
from ..models import (
    AssertionResult,
    AssertionResultStatus,
    EvalGrade,
    EvalResult,
    TokenUsage,
    TranscriptEntry,
    TranscriptRole,
)

logger = logging.getLogger(__name__)

DEFAULT_SCENARIO_TIMEOUT = 300  # 5 min per scenario prompt
DEFAULT_EVAL_TIMEOUT = 120  # 2 min for grading


@dataclass
class EvalCase:
    """A single eval scenario loaded from JSON.

    Attributes:
        id: Unique identifier (e.g., "full-dotnet-journey").
        name: Human-readable name.
        prompt: Initial prompt to send to the agent under test.
        description: Scenario goal — guides the simulated human agent.
        assertions: List of assertions to check against the transcript.
        tags: Tags for filtering (e.g., ["journey", "foundation"]).
        targets: Runtime formats this scenario is compatible with (e.g., ["power", "plugin"]).
            Empty means compatible with both.
        max_turns: Maximum turns for the scenario agent. Defaults to 10.
        timeout_seconds: Per-prompt timeout. Defaults to 300.
        simulated_human_guidance: Extra behavioral instructions for the scenario agent.
        agent: Which agent profile the agent under test should use.
        workspace_setup: Description of required workspace state.
        workspace_dir: Path to a directory of fixture files to copy into the
            workspace. Resolved relative to the scenario JSON file.
        mocks: CLI and MCP mock definitions. When provided, the eval runner
            intercepts matching calls and returns canned responses.
    """

    id: str
    name: str
    prompt: str
    description: str
    assertions: list[dict[str, Any]]
    tags: list[str] = field(default_factory=list)
    targets: list[str] = field(default_factory=list)
    max_turns: int = 10
    timeout_seconds: int = DEFAULT_SCENARIO_TIMEOUT
    simulated_human_guidance: str | None = None
    agent: str | None = None  # Set from ExecutionConfig.agent_name at load time
    workspace_setup: str | None = None
    workspace_dir: str | None = None
    mocks: dict[str, Any] | None = None


def _build_scenario_prompt(scenario: EvalCase) -> str:
    """Build the prompt sent to the scenario agent.

    Packages the scenario goal, guidance, and initial prompt into a single
    structured prompt that the scenario-runner skill understands.

    Args:
        scenario: The eval case to build the prompt for.

    Returns:
        A formatted prompt string for the scenario agent.
    """
    parts = [
        f"SCENARIO GOAL: {scenario.description}",
    ]
    if scenario.simulated_human_guidance:
        parts.append(f"GUIDANCE: {scenario.simulated_human_guidance}")
    parts.append(f"MAX TURNS: {scenario.max_turns}")
    parts.append(f"INITIAL PROMPT TO SEND TO THE POWER: {scenario.prompt}")
    parts.append(
        "\nBegin the interaction now. Send the initial prompt to the power "
        "and respond to its questions following the goal and guidance above. "
        "Output __DONE__ when the scenario is complete."
    )
    return "\n\n".join(parts)


def _build_human_decision_prompt(
    scenario: EvalCase, transcript: list[TranscriptEntry], turn: int
) -> str:
    """Build the prompt sent to the scenario agent to decide the human's next response.

    Args:
        scenario: The eval case being run.
        transcript: The interaction transcript so far.
        turn: The current turn number.

    Returns:
        A formatted prompt for the scenario agent.
    """
    transcript_text = _format_transcript(transcript)
    parts = [
        f"SCENARIO GOAL: {scenario.description}",
    ]
    if scenario.simulated_human_guidance:
        parts.append(f"GUIDANCE: {scenario.simulated_human_guidance}")
    parts.append(f"CURRENT TURN: {turn}")
    parts.append(f"\nINTERACTION SO FAR:\n{transcript_text}")
    parts.append(
        "\nBased on the agent's last message, decide what the human user "
        "would say next. If the scenario has reached its natural conclusion, "
        "respond with exactly: __DONE__\n"
        "Otherwise, respond with ONLY the human's next message. No explanation."
    )
    return "\n\n".join(parts)


def _build_eval_prompt(transcript_text: str, assertions: list[dict[str, Any]]) -> str:
    """Build the prompt sent to the evaluation agent.

    Packages the transcript and assertions into a structured prompt that
    the eval-judge skill understands.

    Args:
        transcript_text: Formatted interaction transcript.
        assertions: List of assertion dicts from the eval JSON.

    Returns:
        A formatted prompt string for the eval agent.
    """
    return (
        f"TRANSCRIPT:\n{transcript_text}\n\n"
        f"ASSERTIONS:\n{json.dumps(assertions, indent=2)}\n\n"
        "Grade each assertion against the transcript. "
        "Respond with ONLY a JSON array of results."
    )


def _format_transcript(entries: list[TranscriptEntry]) -> str:
    """Format transcript entries for the eval agent.

    Args:
        entries: Ordered list of transcript entries.

    Returns:
        Formatted string with one line per entry.
    """
    lines = []
    for entry in entries:
        role_label = entry.role.value.upper()
        lines.append(f"[Turn {entry.turn}] {role_label}: {entry.content}")
    return "\n".join(lines)


def _parse_bridge_transcript(response: BridgeResponse, turn: int = 1) -> list[TranscriptEntry]:
    """Extract transcript entries from a bridge response.

    The bridge returns the agent's full text response. We parse it into
    transcript entries. The scenario agent's output contains the multi-turn
    interaction record.

    Args:
        response: The bridge response from the scenario agent.
        turn: Turn number for these entries.

    Returns:
        List of transcript entries extracted from the response.
    """
    entries = []
    if response.text:
        entries.append(
            TranscriptEntry(
                role=TranscriptRole.AGENT,
                content=response.text,
                turn=turn,
            )
        )
    return entries


def _tool_call_entries(response: BridgeResponse, turn: int) -> list[TranscriptEntry]:
    """Extract tool call transcript entries from a bridge response.

    Creates TOOL_CALL entries for each tool call event captured during
    the streaming response. These are important for assertions that check
    whether specific tools were called (e.g., create_job, get_status).

    Args:
        response: The bridge response with tool_calls list.
        turn: Turn number for these entries.

    Returns:
        List of TOOL_CALL transcript entries.
    """
    entries = []
    for tc in response.tool_calls:
        tool = tc.get("tool", "")
        kind = tc.get("kind", "")
        status = tc.get("status", "")
        entries.append(
            TranscriptEntry(
                role=TranscriptRole.TOOL_CALL,
                content=f"tool_call: {tool} (kind={kind}, status={status})",
                turn=turn,
            )
        )
    return entries


def _parse_eval_grades(response: BridgeResponse) -> list[AssertionResult]:
    """Parse the evaluation agent's JSON response into assertion results.

    The eval agent returns a JSON array of grade objects. Falls back to
    a single NEEDS_REVIEW result if parsing fails.

    Args:
        response: The bridge response from the eval agent.

    Returns:
        List of parsed assertion results.
    """
    if response.status != BridgeResponseStatus.SUCCESS or not response.text:
        return [
            AssertionResult(
                name="eval_agent_error",
                result=AssertionResultStatus.NEEDS_REVIEW,
                evidence=f"Eval agent returned: {response.status.value} - {response.error or response.text}",
            )
        ]

    # Try to extract JSON from the response (may have markdown fences or
    # multiple JSON arrays when the judge second-guesses itself).
    text = response.text.strip()
    if text.startswith("```"):
        # Strip markdown code fences
        lines = text.split("\n")
        text = "\n".join(line for line in lines if not line.strip().startswith("```"))

    # Find all JSON arrays in the response — use the last one (the judge's
    # final/corrected answer). Scan for top-level '[' and try parsing from
    # each one, keeping the last successful parse of assertion-shaped dicts.
    grades = None
    for i, ch in enumerate(text):
        if ch == "[":
            try:
                candidate = json.loads(text[i:])
            except json.JSONDecodeError:
                # The slice may have trailing text — try to find matching ']'
                depth = 0
                for j in range(i, len(text)):
                    if text[j] == "[":
                        depth += 1
                    elif text[j] == "]":
                        depth -= 1
                        if depth == 0:
                            try:
                                candidate = json.loads(text[i : j + 1])
                            except json.JSONDecodeError:
                                continue
                            break
                else:
                    continue
            if isinstance(candidate, list) and candidate and isinstance(candidate[0], dict):
                grades = candidate

    if grades is None:
        return [
            AssertionResult(
                name="eval_parse_error",
                result=AssertionResultStatus.NEEDS_REVIEW,
                evidence=f"Could not parse eval agent response as JSON: {text[:200]}",
            )
        ]

    if not isinstance(grades, list):
        return [
            AssertionResult(
                name="eval_parse_error",
                result=AssertionResultStatus.NEEDS_REVIEW,
                evidence=f"Expected JSON array from eval agent, got {type(grades).__name__}: {text[:200]}",
            )
        ]

    results = []
    for grade in grades:
        status_str = grade.get("result", "needs_review")
        try:
            status = AssertionResultStatus(status_str)
        except ValueError:
            status = AssertionResultStatus.NEEDS_REVIEW

        results.append(
            AssertionResult(
                name=grade.get("name", "unknown"),
                result=status,
                evidence=grade.get("evidence", ""),
                turn_number=grade.get("turn_number"),
            )
        )

    return results


class EvalOrchestrator:
    """Coordinates scenario agent and evaluation agent for each eval case.

    For each scenario:
    1. Starts a bridge session → invokes scenario agent (persistent, multi-turn)
    2. Collects the interaction transcript
    3. Starts a separate bridge session → invokes eval agent (single-turn)
    4. Collects structured grades
    5. Cleans up both sessions

    Attributes:
        cwd: Working directory for bridge sessions.
    """

    def __init__(
        self,
        config: ExecutionConfig,
        cwd: str = "/tmp",
        results_dir: str | None = None,
        verbose: bool = False,
    ) -> None:
        """Initialize the orchestrator.

        Args:
            config: Eval configuration (agent names, paths, etc.).
            cwd: Working directory for bridge daemon socket files.
            results_dir: Directory to store results and renamed log files.
                Defaults to ``./eval-results/`` in the current working directory.
            verbose: Enable debug logging for agent-cli (KIRO_LOG_LEVEL=debug).
        """
        self.config = config
        self.cwd = cwd
        self.results_dir = Path(results_dir) if results_dir else Path.cwd() / "eval-results"
        self.verbose = verbose

    def run_eval(self, scenario: EvalCase, workspace_cwd: str | None = None) -> EvalGrade:
        """Execute a single eval scenario end-to-end and grade it.

        This is the composition of the two public phases:

        1. :meth:`run_scenario` — drive the multi-turn conversation (execution).
        2. :meth:`grade` — score the resulting transcript with the LLM judge.

        It is kept as a convenience for the standalone CLI and callers that want
        the framework's native grading. Callers that want pluggable scoring
        (e.g. eval_runner's metric registry) can call :meth:`run_scenario`
        directly and score the transcript themselves.

        Args:
            scenario: The eval case to run.
            workspace_cwd: Working directory for the agent-cli acp session.
                Should point to a workspace with relevant project files.
                Defaults to ``self.cwd``.

        Returns:
            An ``EvalGrade`` with per-assertion results and overall pass/fail.
        """
        result = self.run_scenario(scenario, workspace_cwd=workspace_cwd)
        assertion_results = self.grade(result, scenario.assertions)
        return self.assemble_grade(result, assertion_results, scenario)

    def assemble_grade(
        self,
        result: EvalResult,
        assertion_results: list[AssertionResult],
        scenario: EvalCase,
    ) -> EvalGrade:
        """Assemble + persist an :class:`EvalGrade` from an execution + assertions.

        Collects/renames the bridge logs, computes overall pass/fail, builds the
        grade (carrying transcript / token usage / work dir from the execution),
        and saves ``result.json`` for the HTML report.

        Shared by :meth:`run_eval` (framework-native grading) and the
        engine-based CLI path (assertions come from scoring metrics). This is the
        single place that maps an execution + assertion verdicts onto the report's
        ``result.json`` shape.
        """
        collected_logs = self._collect_logs(
            scenario.id, result.run_timestamp, result.log_paths, result.session_ids
        )

        failed = any(a.result != AssertionResultStatus.PASS for a in assertion_results)

        grade = EvalGrade(
            eval_id=scenario.id,
            passed=not failed,
            assertions=assertion_results,
            duration_seconds=result.duration_seconds,
            turn_count=result.turn_count,
            token_usage=result.token_usage,
            transcript=result.transcript,
            work_dir=result.work_dir,
            tools_available=None,
            log_files=collected_logs,
        )

        # Save result.json alongside the log files
        self._save_result(grade, scenario, result.run_timestamp)

        return grade

    def run_scenario(
        self, scenario: EvalCase, workspace_cwd: str | None = None
    ) -> EvalResult:
        """Execute a single eval scenario (multi-turn conversation only, no grading).

        Flow:
        1. Start bridge session for the POWER agent (persistent, multi-turn)
        2. Send initial prompt from the eval case to the agent
        3. Get power's response → add to transcript
        4. Start bridge session for the SCENARIO agent (decides human responses)
        5. Loop:
           a. Send power's response + scenario context to scenario agent
           b. Scenario agent returns what the human says next (or __DONE__)
           c. Send human's response to agent
           d. Get power's response → add to transcript
        6. Return the collected transcript and runtime bookkeeping.

        The returned :class:`EvalResult` can be graded via :meth:`grade` (the
        framework's LLM judge) or by any external scorer that consumes the
        transcript.

        Args:
            scenario: The eval case to run.
            workspace_cwd: Working directory for the agent-cli acp session.
                Should point to a workspace with relevant project files.
                Defaults to ``self.cwd``.

        Returns:
            An ``EvalResult`` carrying the transcript, turn/token counts, work
            directory, and bridge log/session metadata.
        """
        start_time = time.time()
        run_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        transcript: list[TranscriptEntry] = []
        log_paths: dict[str, str | None] = {}  # agent_type → bridge log path
        session_ids: dict[str, str | None] = {}  # agent_type → agent-cli session ID
        token_usage = TokenUsage()  # accumulate agent token usage

        # Create an isolated work directory for this scenario run.
        # Named by scenario ID so it's easy to find and inspect after a run.
        # If a stale directory exists from a previous run, clean it up first.
        base_cwd = workspace_cwd or self.cwd
        if os.path.sep in scenario.id or ".." in scenario.id:
            raise ValueError(f"Invalid scenario ID (path traversal): {scenario.id}")
        scenario_work_dir = os.path.join(base_cwd, scenario.id)
        if os.path.exists(scenario_work_dir) and os.listdir(scenario_work_dir):
            logger.info(f"Cleaning up stale work directory: {scenario_work_dir}")
            shutil.rmtree(scenario_work_dir)
        os.makedirs(scenario_work_dir, exist_ok=True)
        logger.info(f"Scenario {scenario.id} work directory: {scenario_work_dir}")

        # Copy fixture directory into workspace if specified.
        if scenario.workspace_dir and os.path.isdir(scenario.workspace_dir):
            shutil.copytree(scenario.workspace_dir, scenario_work_dir, dirs_exist_ok=True)
            logger.info("Copied workspace_dir: %s", scenario.workspace_dir)

        # Set up mocks if configured.
        mock_manager = None
        mock_context = None
        if scenario.mocks:
            from .mocking import MockConfig, MockManager

            mock_manager = MockManager(Path(scenario_work_dir))
            mock_config = MockConfig(
                cli_mocks=scenario.mocks.get("cli", []),
                mcp_mocks=scenario.mocks.get("mcp", []),
            )
            if mock_config.has_mocks:
                try:
                    mock_context = mock_manager.setup(mock_config)
                except Exception:
                    mock_manager.teardown()
                    raise
                logger.info(
                    "Mocks active: CLI=%d rules, MCP=%d tools",
                    len(mock_config.cli_mocks),
                    len(mock_config.mcp_mocks),
                )

        # Install agents to ~/.kiro/agents/ (global). agent-cli ACP does not
        # discover workspace-local agents even with cwd set correctly.
        # Guarded so mock teardown runs if install_agents raises (prevents
        # PATH corruption from leftover CLI mocks).
        try:
            agents_dir = Path.home() / ".kiro" / "agents"
            installed = install_agents(
                config=self.config,
                agents_dir=agents_dir,
                mock_mcp_context=mock_context,
            )
            logger.info(f"Agents installed to {agents_dir}:")
            for agent_path in installed:
                logger.info(f"  - {agent_path.name}")
            if len(installed) < 3:  # power + scenario + judge
                raise RuntimeError(
                    f"Expected 3 agents but only installed {len(installed)}. "
                    f"Check framework build directory."
                )
            # --- Phase 1: Multi-turn interaction with the agent ---
            power_session = f"power-{scenario.id}"
            power_bridge = BridgeRunner(
                session_name=power_session,
                cwd=scenario_work_dir,
                verbose=self.verbose,
                has_mcp=self.config.mcp_server_name is not None,
                resource_logger=self.config.resource_logger,
                binary=self.config.acp_binary,
            )

            scenario_session = f"scenario-{scenario.id}"
            scenario_bridge = BridgeRunner(
                session_name=scenario_session,
                cwd=scenario_work_dir,
                verbose=self.verbose,
                binary=self.config.acp_binary,
            )
        except Exception:
            if mock_manager:
                mock_manager.teardown()
            raise

        try:
            power_bridge.start(agent=self.config.agent_name)
            scenario_bridge.start(agent=self.config.scenario_agent)
            session_ids["power"] = power_bridge.session_id
            session_ids["scenario"] = scenario_bridge.session_id

            # Turn 1: Send initial prompt to the POWER agent
            transcript.append(
                TranscriptEntry(
                    role=TranscriptRole.HUMAN,
                    content=scenario.prompt,
                    turn=1,
                )
            )

            logger.info(f"  human[prompt] >> {scenario.prompt}")

            power_response = power_bridge.prompt(
                agent=self.config.agent_name,
                text=scenario.prompt,
                timeout=scenario.timeout_seconds,
                auto_approve=True,
            )
            log_paths["power"] = power_response.log_path
            token_usage.add(power_response.usage)

            if power_response.status == BridgeResponseStatus.SUCCESS:
                logger.info(f"  agent[reply] >> {power_response.text}")
            else:
                logger.info(
                    f"  agent[reply] >> [ERROR: {power_response.status.value}] {power_response.error}"
                )

            # Add turn 1 response to transcript
            transcript.extend(_tool_call_entries(power_response, turn=1))
            transcript.append(
                TranscriptEntry(
                    role=TranscriptRole.AGENT,
                    content=power_response.text or f"ERROR: {power_response.error}",
                    turn=1,
                )
            )

            # Skip multi-turn if first prompt failed/timed out
            if power_response.status != BridgeResponseStatus.SUCCESS:
                logger.error(
                    f"Agent failed on turn 1: {power_response.status.value}"
                    f" - {power_response.error}"
                )
            else:
                # Turns 2..N: scenario agent decides human responses
                for turn in range(2, scenario.max_turns + 1):
                    # Ask scenario agent what the human should say next
                    human_decision_prompt = _build_human_decision_prompt(scenario, transcript, turn)
                    decision_response = scenario_bridge.prompt(
                        agent=self.config.scenario_agent,
                        text=human_decision_prompt,
                        timeout=60,
                        auto_approve=True,
                    )
                    if "scenario" not in log_paths:
                        log_paths["scenario"] = decision_response.log_path

                    if decision_response.status != BridgeResponseStatus.SUCCESS:
                        logger.error(
                            f"Scenario {scenario.id}: scenario agent failed at turn"
                            f" {turn}: {decision_response.error}"
                        )
                        break

                    human_message = decision_response.text.strip()
                    if human_message.startswith("__DONE__"):
                        logger.info(
                            f"Scenario {scenario.id}: scenario agent signaled DONE"
                            f" at turn {turn}"
                        )
                        break

                    # Send human's response to the POWER agent
                    logger.info(f"  human[prompt] >> {human_message}")
                    transcript.append(
                        TranscriptEntry(
                            role=TranscriptRole.HUMAN,
                            content=human_message,
                            turn=turn,
                        )
                    )

                    power_response = power_bridge.prompt(
                        agent=self.config.agent_name,
                        text=human_message,
                        timeout=scenario.timeout_seconds,
                        auto_approve=True,
                    )
                    token_usage.add(power_response.usage)

                    if power_response.status == BridgeResponseStatus.SUCCESS:
                        logger.info(f"  agent[reply] >> {power_response.text}")
                    else:
                        logger.info(
                            f"  agent[reply] >> [ERROR: {power_response.status.value}]"
                            f" {power_response.error}"
                        )

                    transcript.extend(_tool_call_entries(power_response, turn=turn))
                    transcript.append(
                        TranscriptEntry(
                            role=TranscriptRole.AGENT,
                            content=power_response.text,
                            turn=turn,
                        )
                    )

        except Exception as e:
            logger.error(f"Scenario {scenario.id} error: {e}")
            # Dump MCP logs on failure for debugging
            power_bridge.dump_mcp_logs()
            transcript.append(
                TranscriptEntry(
                    role=TranscriptRole.AGENT,
                    content=f"ERROR: {e}",
                    turn=0,
                )
            )
        finally:
            # Optional post-scenario cleanup (e.g., stop jobs, delete workspaces)
            if self.config.cleanup_prompt:
                try:
                    cleanup_response = power_bridge.prompt(
                        agent=self.config.agent_name,
                        text=self.config.cleanup_prompt,
                        timeout=60,
                        auto_approve=True,
                    )
                    if cleanup_response.status == BridgeResponseStatus.SUCCESS:
                        logger.info(f"  cleanup >> {cleanup_response.text}")
                    else:
                        logger.warning(f"  cleanup >> failed: {cleanup_response.error}")
                except Exception as e:
                    logger.warning(f"  cleanup >> error: {e}")
            # Guard each destroy() independently so a failure tearing down one
            # bridge can't leak the other's subprocess.
            try:
                power_bridge.destroy()
            except Exception as e:
                logger.warning(f"  power_bridge.destroy() failed: {e}")
            try:
                scenario_bridge.destroy()
            except Exception as e:
                logger.warning(f"  scenario_bridge.destroy() failed: {e}")

            # Tear down mocks (restore PATH, clean up artifacts).
            if mock_manager:
                mock_manager.teardown()

        # kiro-cli reports no usage over ACP, so token_usage is empty here.
        # Recover the real signals (credits, context %) from the power agent's
        # session file, which kiro-cli flushes on session end. Best-effort: keep
        # the ACP-accumulated usage if the session file yields nothing.
        session_usage = self._usage_from_power_session(session_ids.get("power"))
        if session_usage is not None:
            token_usage = session_usage

        return EvalResult(
            eval_id=scenario.id,
            transcript=transcript,
            turn_count=max((e.turn for e in transcript), default=0),
            duration_seconds=time.time() - start_time,
            token_usage=token_usage,
            work_dir=scenario_work_dir,
            log_paths=log_paths,
            session_ids=session_ids,
            run_timestamp=run_timestamp,
        )

    @staticmethod
    def _usage_from_power_session(session_id: str | None) -> TokenUsage | None:
        """Read usage from the power agent's kiro-cli session file.

        Returns None when there is no session id or the file carries no usable
        signal, so the caller can fall back to the ACP-accumulated usage.
        """
        if not session_id:
            return None
        session_file = Path.home() / ".kiro" / "sessions" / "cli" / f"{session_id}.json"
        usage = usage_from_session_file(session_file)
        has_signal = (
            usage.credits
            or usage.context_usage_percentage
            or usage.total_tokens
        )
        return usage if has_signal else None

    def grade(
        self,
        result: EvalResult,
        assertions: list[dict[str, Any]],
    ) -> list[AssertionResult]:
        """Grade an executed scenario's transcript with the LLM judge.

        Starts a judge bridge session in the scenario's work directory, sends the
        formatted transcript plus assertions, and parses the structured verdict.

        Args:
            result: The execution result from :meth:`run_scenario`.
            assertions: Assertion definitions to grade against (from the scenario).

        Returns:
            One :class:`AssertionResult` per assertion. On judge failure, returns a
            single ``NEEDS_REVIEW`` result describing the error.

        Side effect: records the judge's bridge log path in ``result.log_paths``
        under the ``"eval"`` key so the caller's log collection can pick it up.
        """
        transcript_text = _format_transcript(result.transcript)
        assertion_results, log_path, session_id = self.grade_transcript(
            transcript_text,
            assertions,
            eval_id=result.eval_id,
            work_dir=result.work_dir,
        )
        result.log_paths["eval"] = log_path
        result.session_ids["eval"] = session_id
        return assertion_results

    def grade_transcript(
        self,
        transcript_text: str,
        assertions: list[dict[str, Any]],
        eval_id: str = "transcript",
        work_dir: str | None = None,
    ) -> tuple[list[AssertionResult], str | None, str | None]:
        """Grade a pre-formatted transcript string with the LLM judge.

        This is the text-based grading core. It lets external scorers (e.g.
        eval_runner's ``llm_judge`` metric, which only has a flattened transcript
        string) reuse the judge without holding the structured ``EvalResult``.

        Args:
            transcript_text: The formatted transcript (see ``_format_transcript``).
            assertions: Assertion definitions to grade against.
            eval_id: Identifier used to name the judge bridge session.
            work_dir: Working directory for the judge bridge session.

        Returns:
            ``(assertion_results, judge_log_path, judge_session_id)``. On judge
            failure, the results list holds a single ``NEEDS_REVIEW`` entry and the
            log path / session id are None.
        """
        eval_bridge = BridgeRunner(
            session_name=f"eval-{eval_id}",
            cwd=work_dir or self.cwd,
            verbose=self.verbose,
            binary=self.config.acp_binary,
        )

        assertion_results: list[AssertionResult] = []
        log_path: str | None = None
        session_id: str | None = None
        try:
            eval_bridge.start(agent=self.config.judge_agent)
            session_id = eval_bridge.session_id

            eval_prompt = _build_eval_prompt(transcript_text, assertions)
            eval_response = eval_bridge.prompt(
                agent=self.config.judge_agent,
                text=eval_prompt,
                timeout=DEFAULT_EVAL_TIMEOUT,
                auto_approve=True,
            )
            log_path = eval_response.log_path
            assertion_results = _parse_eval_grades(eval_response)

        except Exception as e:
            logger.error(f"Eval agent {eval_id} error: {e}")
            assertion_results = [
                AssertionResult(
                    name="eval_agent_error",
                    result=AssertionResultStatus.NEEDS_REVIEW,
                    evidence=f"Eval agent failed: {e}",
                )
            ]
        finally:
            eval_bridge.destroy()

        return assertion_results, log_path, session_id

    def _collect_logs(
        self,
        scenario_id: str,
        run_timestamp: str,
        log_paths: dict[str, str | None],
        session_ids: dict[str, str | None] | None = None,
    ) -> list[str]:
        """Copy bridge log files to the results directory with a structured naming format.

        Renames logs from the bridge's internal format::

            /tmp/wt-acp-power-<id>-<agent>-<pid>.log

        To the structured format::

            eval-results/<scenario_id>_<timestamp>_<agent_type>_<agent_name>.log

        Args:
            scenario_id: The eval scenario ID (e.g., "dotnet-agent-selection").
            run_timestamp: Timestamp shared across all agents in this run (YYYYMMDD_HHMMSS).
            log_paths: Map of agent_type ("power", "scenario", "eval") to bridge log file paths.

        Returns:
            List of collected log file paths.
        """
        agent_names = {
            "power": self.config.agent_name,
            "scenario": self.config.scenario_agent,
            "eval": self.config.judge_agent,
        }

        collected: list[str] = []
        scenario_dir = self.results_dir / scenario_id
        scenario_dir.mkdir(parents=True, exist_ok=True)

        for agent_type, src_path in log_paths.items():
            if not src_path or not os.path.exists(src_path):
                continue

            agent_name = agent_names.get(agent_type, agent_type)
            dest_name = f"{scenario_id}_{run_timestamp}_{agent_type}_{agent_name}.log"
            dest_path = scenario_dir / dest_name

            try:
                shutil.copy2(src_path, dest_path)
                collected.append(str(dest_path))
                logger.info(f"Log collected: {dest_path}")
                # Also collect raw, stderr, and per-session kiro logs
                for suffix in ("-raw.log", "-stderr.log", "-kiro.log"):
                    extra_src = src_path.replace(".log", suffix)
                    if os.path.exists(extra_src) and os.path.getsize(extra_src) > 0:
                        extra_dest = scenario_dir / dest_name.replace(".log", suffix)
                        shutil.copy2(extra_src, extra_dest)
                        collected.append(str(extra_dest))
            except OSError as e:
                logger.warning(f"Failed to collect log {src_path}: {e}")

        # Collect agent-cli logs for debugging
        log_sources = [
            (Path(f"/run/user/{os.getuid()}/kiro-log"), ["kiro-chat.log", "mcp.log"]),
        ]
        for log_dir, log_names in log_sources:
            for log_name in log_names:
                src = log_dir / log_name
                if src.exists() and src.stat().st_size > 0:
                    dest = scenario_dir / f"{scenario_id}_{run_timestamp}_{log_name}"
                    try:
                        shutil.copy2(src, dest)
                        collected.append(str(dest))
                        logger.info(f"Log collected: {dest}")
                    except OSError as e:
                        logger.debug(f"Skipped log {src} → {dest}: {e}")

        # Collect agent-cli chat session files (~/.kiro/sessions/cli/<session-id>.*)
        if session_ids:
            sessions_dir = Path.home() / ".kiro" / "sessions" / "cli"
            for agent_type, sid in session_ids.items():
                if not sid:
                    continue
                agent_name = agent_names.get(agent_type, agent_type)
                for ext in (".json", ".jsonl"):
                    src = sessions_dir / f"{sid}{ext}"
                    if src.exists() and src.stat().st_size > 0:
                        dest = (
                            scenario_dir
                            / f"{scenario_id}_{run_timestamp}_{agent_type}_{agent_name}_session{ext}"
                        )
                        try:
                            shutil.copy2(src, dest)
                            collected.append(str(dest))
                            logger.info(f"Session collected: {dest}")
                        except OSError as e:
                            logger.debug(f"Skipped session {src} → {dest}: {e}")

        return collected

    def _save_result(self, grade: EvalGrade, scenario: EvalCase, run_timestamp: str) -> None:
        """Save structured result JSON alongside the log files.

        Result files are timestamped (``result_YYYYMMDD_HHMMSS.json``) so
        multiple runs accumulate without overwriting each other. The report
        generator picks the latest result per scenario.
        """
        scenario_dir = self.results_dir / scenario.id
        scenario_dir.mkdir(parents=True, exist_ok=True)

        data = grade.to_dict()
        data["scenario"] = {
            "id": scenario.id,
            "name": scenario.name,
            "prompt": scenario.prompt,
            "description": scenario.description,
            "tags": scenario.tags,
            "max_turns": scenario.max_turns,
            "timeout_seconds": scenario.timeout_seconds,
            "simulated_human_guidance": scenario.simulated_human_guidance,
            "assertions": scenario.assertions,
        }

        out_path = scenario_dir / f"result_{run_timestamp}.json"
        out_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        logger.info("Result saved: %s", out_path)

    def run_suite(
        self,
        scenarios: list[EvalCase],
        workspace_cwd: str | None = None,
        filter_tags: list[str] | None = None,
        filter_ids: list[str] | None = None,
    ) -> list[EvalGrade]:
        """Run all scenarios in a suite, each in an isolated session.

        Args:
            scenarios: List of eval cases to run.
            workspace_cwd: Working directory for agent-cli sessions.
            filter_tags: If provided, only run scenarios with at least one matching tag.
            filter_ids: If provided, only run scenarios with matching IDs.

        Returns:
            List of ``EvalGrade`` results, one per executed scenario.
        """
        results = []
        for scenario in scenarios:
            # Apply filters
            if filter_ids and scenario.id not in filter_ids:
                continue
            if filter_tags and not any(t in scenario.tags for t in filter_tags):
                continue

            logger.info(f"Running scenario: {scenario.name} ({scenario.id})")
            grade = self.run_eval(scenario, workspace_cwd)
            results.append(grade)

            status = "PASSED" if grade.passed else "FAILED"
            passed_count = sum(
                1 for a in grade.assertions if a.result == AssertionResultStatus.PASS
            )
            logger.info(
                f"  {status} ({grade.duration_seconds:.1f}s, {grade.turn_count} turns, {passed_count}/{len(grade.assertions)} assertions passed)"
            )

        return results
