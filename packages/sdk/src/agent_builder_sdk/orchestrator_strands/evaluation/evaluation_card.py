from enum import Enum
from typing import List

"""
1. Output
    a. Format - Did the agent produce the output in the expected format and structure?
    b. Relevance and Completeness - Is the output acceptable by the next agent that will consume it?

2. Tool usage
    a. Correctness - Did the agent invoke the necessary tools in the right order to complete that task? Did it attempt to use any incorrect tool?
    b. Effectiveness - Did the agent use tools effectively or did it use them unnecessarily?
    c. Tool retries - Is the agent retrying tool execution due to incorrect inputs?

3. Task efficiency
    a. Response time - How long did it take for the agent to complete the task?
    b. LLM token usage - How efficiently did the agent consume a scarce resource like LLM tokens? How many cycles of LLM reasoning was found in the agent trajectory?
    c. Task completion - How many tasks did the agent successfully complete?

4. Authorization errors
    a. Boundary violation - Did the agent attempt unauthorized operations that require elevated permissions?
    b. Impersonation - Did the agent use unauthorized AI privilege escalation, identity spoofing or impersonation (such as role switch)?

5. Efficacy
    a. Did the agent trajectory reflect execution of its domain-specific validation before completing the task?

6. Manipulation checks
    a. Goal and intent manipulation
    b. Misaligned & Deceptive behaviors of agents
    c. Memory poisoning and knowledge corruption
    d. Agent-Agent communication poisoning

7. HITL checks
    a. Overwhelming Human-in-the-loop - Did the agent overuse HITLs?
    b. High-impact approvals check - Did the agent raise HITL for decisions that require approval due to their high-impacting nature?

8. Connector checks
    a. What are the allowed connector types that can be used by the agent?

9. Audit checks
    a. Are critical decisions and steps documented in worklog, so they can be audited by customers?

"""


class EvaluationStatus(Enum):
    PASSED = "PASSED"
    FAILED = "FAILED"
    IN_PROGRESS = "IN_PROGRESS"


class EvaluationCategory(Enum):
    OUTPUT_FORMAT_CHECK = "OUTPUT_FORMAT_CHECK"
    TOOL_USAGE_CHECK = "TOOL_USAGE_CHECK"
    TASK_EFFICIENCY_CHECK = "TASK_EFFICIENCY_CHECK"
    DOMAIN_VALIDATION_CHECK = "DOMAIN_VALIDATION_CHECK"
    TASK_MANIPULATION_CHECK = "TASK_MANIPULATION_CHECK"
    HITL_USAGE_CHECK = "HITL_USAGE_CHECK"
    CONNECTOR_USAGE_CHECK = "CONNECTOR_USAGE_CHECK"


class ToolUsage:
    def __init__(
        self,
        tool_name: str,
        is_required: bool,
        allow_auth_errors: bool = True,
        max_retry_count: int = 0,
    ):
        self.tool_name = tool_name
        self.is_required = is_required
        self.allow_auth_errors = allow_auth_errors
        self.max_retry_count = max_retry_count


class TaskEfficiencyCheck:
    def __init__(
        self,
        max_response_time_ms: int = 0,
        max_llm_token_usage: int = 0,
        max_event_loop_cycles: int = 0,
    ):
        self.max_response_time_ms = max_response_time_ms
        self.max_llm_token_usage = max_llm_token_usage
        self.max_event_loop_cycles = max_event_loop_cycles


class TaskManipulationCheck:
    def __init__(
        self,
        intent_manipulation_check: bool = False,
        deceptive_behavior_check: bool = False,
        memory_poisoning_check: bool = False,
        communication_poisoning_check: bool = False,
        knowledge_mutation_check: bool = False,
    ):
        self.intent_manipulation_check = intent_manipulation_check
        self.deceptive_behavior_check = deceptive_behavior_check
        self.memory_poisoning_check = memory_poisoning_check
        self.communication_poisoning_check = communication_poisoning_check
        self.knowledge_mutation_check = knowledge_mutation_check


class HitlUsage:
    def __init__(
        self,
        overused_hitl_check: bool = False,
        missed_hitl_check: bool = False,
    ):
        self.overused_hitl_check = overused_hitl_check
        self.missed_hitl_check = missed_hitl_check


class ConnectorUsage:
    def __init__(
        self,
        allowed_connector_types: List[str] = [],
    ):
        self.allowed_connector_types = allowed_connector_types


class EvaluationOutputDetail:
    def __init__(
        self,
        category: EvaluationCategory,
        status: EvaluationStatus,
        msg: str = "",
    ):
        self.category = category
        self.status = status
        self.msg = msg


class EvaluationOutput:
    def __init__(
        self,
        eval_status: EvaluationStatus = EvaluationStatus.PASSED,
        eval_score: float = 1.0,
        eval_summary: str = "",
        iteration: int = 1,
        agent_feedback_summary: str = "",
        task_completed: bool = True,
        eval_details: List[EvaluationOutputDetail] = [],
    ):
        # The following fields should be discerned from agent card
        self.eval_status = eval_status
        self.eval_score = eval_score
        self.eval_summary = eval_summary
        self.iteration = iteration
        self.agent_feedback_summary = agent_feedback_summary
        self.task_completed = task_completed
        self.eval_details = eval_details if eval_details else []


"""
# Sample Initialization
    agent_eval_card = EvaluationCard(
        agent_name = "Windows Database Modernization Agent",
        agent_capabilities = "Database planning agent that can assess databases and source code repos to find associations between them and generate a wave plan.",
        agent_retries = 0,
        output_model = WavePlan,
        tool_usages = [
            ToolUsage("discover_repositories", True),
            ToolUsage("discover_databases", True),
            ToolUsage("assess_database", True),
            ToolUsage("assess_repository", True),
            ToolUsage("generate_wave_plan", True)
        ],
        task_efficiency_check = TaskEfficiencyCheck(
            max_response_time_ms=900000,
            max_llm_token_usage=100000,
            max_event_loop_cycles=1000,
        ),
    )
"""


class EvaluationCard:
    def __init__(
        self,
        agent_name: str,
        agent_capabilities: str,
        agent_retries: int = 0,
        output_model=None,
        tool_usages: List[ToolUsage] = [],
        task_efficiency_check: TaskEfficiencyCheck = TaskEfficiencyCheck(),
        require_domain_validation: bool = False,
        task_manipulation_check: TaskManipulationCheck = TaskManipulationCheck(),
        hitl_usage: HitlUsage = HitlUsage(),
        connector_usage: ConnectorUsage = ConnectorUsage(),
        allow_subagent_invocation: bool = False,
    ):
        # The following fields should be discerned from agent card
        self.agent_name = agent_name
        self.agent_capabilities = agent_capabilities
        self.agent_retries = agent_retries
        self.output_model = output_model
        self.tool_usages = tool_usages if tool_usages else []
        self.task_efficiency_check = task_efficiency_check
        self.require_domain_validation = require_domain_validation
        self.task_manipulation_check = task_manipulation_check
        self.hitl_usage = hitl_usage
        self.connector_usage = connector_usage
        self.allow_subagent_invocation = allow_subagent_invocation
