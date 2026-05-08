# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Tests for evaluation_card module."""

from pydantic import BaseModel

from agent_builder_sdk.orchestrator_strands.evaluation.evaluation_card import (
    ConnectorUsage,
    EvaluationCard,
    EvaluationCategory,
    EvaluationOutput,
    EvaluationOutputDetail,
    EvaluationStatus,
    HitlUsage,
    TaskEfficiencyCheck,
    TaskManipulationCheck,
    ToolUsage,
)


class TestEvaluationStatus:
    """Test EvaluationStatus enum."""

    def test_enum_values(self):
        """Test that enum has correct values."""
        assert EvaluationStatus.PASSED.value == "PASSED"
        assert EvaluationStatus.FAILED.value == "FAILED"
        assert EvaluationStatus.IN_PROGRESS.value == "IN_PROGRESS"


class TestEvaluationCategory:
    """Test EvaluationCategory enum."""

    def test_enum_values(self):
        """Test that enum has correct values."""
        assert EvaluationCategory.OUTPUT_FORMAT_CHECK.value == "OUTPUT_FORMAT_CHECK"
        assert EvaluationCategory.TOOL_USAGE_CHECK.value == "TOOL_USAGE_CHECK"
        assert EvaluationCategory.TASK_EFFICIENCY_CHECK.value == "TASK_EFFICIENCY_CHECK"
        assert EvaluationCategory.DOMAIN_VALIDATION_CHECK.value == "DOMAIN_VALIDATION_CHECK"
        assert EvaluationCategory.TASK_MANIPULATION_CHECK.value == "TASK_MANIPULATION_CHECK"
        assert EvaluationCategory.HITL_USAGE_CHECK.value == "HITL_USAGE_CHECK"
        assert EvaluationCategory.CONNECTOR_USAGE_CHECK.value == "CONNECTOR_USAGE_CHECK"


class TestToolUsage:
    """Test ToolUsage class."""

    def test_init_with_required_params(self):
        """Test initialization with required parameters."""
        tool_usage = ToolUsage("test_tool", True)

        assert tool_usage.tool_name == "test_tool"
        assert tool_usage.is_required is True
        assert tool_usage.allow_auth_errors is True
        assert tool_usage.max_retry_count == 0

    def test_init_with_all_params(self):
        """Test initialization with all parameters."""
        tool_usage = ToolUsage(
            tool_name="test_tool", is_required=False, allow_auth_errors=False, max_retry_count=3
        )

        assert tool_usage.tool_name == "test_tool"
        assert tool_usage.is_required is False
        assert tool_usage.allow_auth_errors is False
        assert tool_usage.max_retry_count == 3


class TestTaskEfficiencyCheck:
    """Test TaskEfficiencyCheck class."""

    def test_init_with_defaults(self):
        """Test initialization with default values."""
        check = TaskEfficiencyCheck()

        assert check.max_response_time_ms == 0
        assert check.max_llm_token_usage == 0
        assert check.max_event_loop_cycles == 0

    def test_init_with_custom_values(self):
        """Test initialization with custom values."""
        check = TaskEfficiencyCheck(
            max_response_time_ms=5000, max_llm_token_usage=10000, max_event_loop_cycles=100
        )

        assert check.max_response_time_ms == 5000
        assert check.max_llm_token_usage == 10000
        assert check.max_event_loop_cycles == 100


class TestTaskManipulationCheck:
    """Test TaskManipulationCheck class."""

    def test_init_with_defaults(self):
        """Test initialization with default values."""
        check = TaskManipulationCheck()

        assert check.intent_manipulation_check is False
        assert check.deceptive_behavior_check is False
        assert check.memory_poisoning_check is False
        assert check.communication_poisoning_check is False
        assert check.knowledge_mutation_check is False

    def test_init_with_custom_values(self):
        """Test initialization with custom values."""
        check = TaskManipulationCheck(
            intent_manipulation_check=True,
            deceptive_behavior_check=True,
            memory_poisoning_check=True,
            communication_poisoning_check=True,
            knowledge_mutation_check=True,
        )

        assert check.intent_manipulation_check is True
        assert check.deceptive_behavior_check is True
        assert check.memory_poisoning_check is True
        assert check.communication_poisoning_check is True
        assert check.knowledge_mutation_check is True


class TestHitlUsage:
    """Test HitlUsage class."""

    def test_init_with_defaults(self):
        """Test initialization with default values."""
        hitl = HitlUsage()

        assert hitl.overused_hitl_check is False
        assert hitl.missed_hitl_check is False

    def test_init_with_custom_values(self):
        """Test initialization with custom values."""
        hitl = HitlUsage(overused_hitl_check=True, missed_hitl_check=True)

        assert hitl.overused_hitl_check is True
        assert hitl.missed_hitl_check is True


class TestConnectorUsage:
    """Test ConnectorUsage class."""

    def test_init_with_defaults(self):
        """Test initialization with default values."""
        connector = ConnectorUsage()

        assert connector.allowed_connector_types == []

    def test_init_with_custom_values(self):
        """Test initialization with custom values."""
        connector_types = ["http", "database", "file"]
        connector = ConnectorUsage(allowed_connector_types=connector_types)

        assert connector.allowed_connector_types == connector_types


class TestEvaluationOutputDetail:
    """Test EvaluationOutputDetail class."""

    def test_init_with_required_params(self):
        """Test initialization with required parameters."""
        detail = EvaluationOutputDetail(
            EvaluationCategory.OUTPUT_FORMAT_CHECK, EvaluationStatus.PASSED
        )

        assert detail.category == EvaluationCategory.OUTPUT_FORMAT_CHECK
        assert detail.status == EvaluationStatus.PASSED
        assert detail.msg == ""

    def test_init_with_all_params(self):
        """Test initialization with all parameters."""
        detail = EvaluationOutputDetail(
            EvaluationCategory.TOOL_USAGE_CHECK,
            EvaluationStatus.FAILED,
            "Tool usage validation failed",
        )

        assert detail.category == EvaluationCategory.TOOL_USAGE_CHECK
        assert detail.status == EvaluationStatus.FAILED
        assert detail.msg == "Tool usage validation failed"


class TestEvaluationOutput:
    """Test EvaluationOutput class."""

    def test_init_with_defaults(self):
        """Test initialization with default values."""
        output = EvaluationOutput()

        assert output.eval_status == EvaluationStatus.PASSED
        assert output.eval_score == 1.0
        assert output.eval_summary == ""
        assert output.iteration == 1
        assert output.agent_feedback_summary == ""
        assert output.task_completed is True
        assert output.eval_details == []

    def test_init_with_custom_values(self):
        """Test initialization with custom values."""
        details = [
            EvaluationOutputDetail(EvaluationCategory.OUTPUT_FORMAT_CHECK, EvaluationStatus.PASSED)
        ]

        output = EvaluationOutput(
            eval_status=EvaluationStatus.FAILED,
            eval_score=0.5,
            eval_summary="Partial completion",
            iteration=2,
            agent_feedback_summary="Needs improvement",
            task_completed=False,
            eval_details=details,
        )

        assert output.eval_status == EvaluationStatus.FAILED
        assert output.eval_score == 0.5
        assert output.eval_summary == "Partial completion"
        assert output.iteration == 2
        assert output.agent_feedback_summary == "Needs improvement"
        assert output.task_completed is False
        assert output.eval_details == details

    def test_init_with_none_eval_details(self):
        """Test initialization with None eval_details defaults to empty list."""
        output = EvaluationOutput(eval_details=None)

        assert output.eval_details == []


class TestEvaluationCard:
    """Test EvaluationCard class."""

    def test_init_with_required_params(self):
        """Test initialization with required parameters."""
        card = EvaluationCard(agent_name="Test Agent", agent_capabilities="Test capabilities")

        assert card.agent_name == "Test Agent"
        assert card.agent_capabilities == "Test capabilities"
        assert card.agent_retries == 0
        assert card.output_model is None
        assert card.tool_usages == []
        assert isinstance(card.task_efficiency_check, TaskEfficiencyCheck)
        assert card.require_domain_validation is False
        assert isinstance(card.task_manipulation_check, TaskManipulationCheck)
        assert isinstance(card.hitl_usage, HitlUsage)
        assert isinstance(card.connector_usage, ConnectorUsage)
        assert card.allow_subagent_invocation is False

    def test_init_with_all_params(self):
        """Test initialization with all parameters."""

        class MockOutputModel(BaseModel):
            test_field: str

        tool_usages = [ToolUsage("tool1", True), ToolUsage("tool2", False)]

        task_efficiency = TaskEfficiencyCheck(
            max_response_time_ms=5000, max_llm_token_usage=10000, max_event_loop_cycles=100
        )

        task_manipulation = TaskManipulationCheck(
            intent_manipulation_check=True, deceptive_behavior_check=True
        )

        hitl_usage = HitlUsage(overused_hitl_check=True, missed_hitl_check=True)

        connector_usage = ConnectorUsage(allowed_connector_types=["http", "database"])

        card = EvaluationCard(
            agent_name="Advanced Agent",
            agent_capabilities="Advanced capabilities",
            agent_retries=3,
            output_model=MockOutputModel,
            tool_usages=tool_usages,
            task_efficiency_check=task_efficiency,
            require_domain_validation=True,
            task_manipulation_check=task_manipulation,
            hitl_usage=hitl_usage,
            connector_usage=connector_usage,
            allow_subagent_invocation=True,
        )

        assert card.agent_name == "Advanced Agent"
        assert card.agent_capabilities == "Advanced capabilities"
        assert card.agent_retries == 3
        assert card.output_model == MockOutputModel
        assert card.tool_usages == tool_usages
        assert card.task_efficiency_check == task_efficiency
        assert card.require_domain_validation is True
        assert card.task_manipulation_check == task_manipulation
        assert card.hitl_usage == hitl_usage
        assert card.connector_usage == connector_usage
        assert card.allow_subagent_invocation is True

    def test_init_with_none_tool_usages(self):
        """Test initialization with None tool_usages defaults to empty list."""
        card = EvaluationCard(
            agent_name="Test Agent", agent_capabilities="Test capabilities", tool_usages=None
        )

        assert card.tool_usages == []

    def test_sample_initialization_pattern(self):
        """Test the sample initialization pattern from the docstring."""

        class WavePlan(BaseModel):
            plan_id: str
            waves: list

        agent_eval_card = EvaluationCard(
            agent_name="Windows Database Modernization Agent",
            agent_capabilities="Database planning agent that can assess databases and source code repos to find associations between them and generate a wave plan.",
            agent_retries=0,
            output_model=WavePlan,
            tool_usages=[
                ToolUsage("discover_repositories", True),
                ToolUsage("discover_databases", True),
                ToolUsage("assess_database", True),
                ToolUsage("assess_repository", True),
                ToolUsage("generate_wave_plan", True),
            ],
            task_efficiency_check=TaskEfficiencyCheck(
                max_response_time_ms=900000,
                max_llm_token_usage=100000,
                max_event_loop_cycles=1000,
            ),
        )

        assert agent_eval_card.agent_name == "Windows Database Modernization Agent"
        assert agent_eval_card.output_model == WavePlan
        assert len(agent_eval_card.tool_usages) == 5
        assert all(tool.is_required for tool in agent_eval_card.tool_usages)
        assert agent_eval_card.task_efficiency_check.max_response_time_ms == 900000
