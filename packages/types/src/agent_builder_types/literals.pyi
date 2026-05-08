"""
Type annotations for AWS Transform Agentic service literal definitions.

[Open documentation](https://vemel.github.io/boto3_stubs_docs/agent_builder_types/literals.html)

Usage::

    ```python
    from agent_builder_types.literals import AccessControlType

    data: AccessControlType = "DISABLED"
    ```
"""

import sys

if sys.version_info >= (3, 8):
    from typing import Literal
else:
    from typing_extensions import Literal

__all__ = (
    "AccessControlType",
    "AccountConnectionStatusType",
    "ActionType",
    "AgentConfigurationAvailabilityType",
    "AgentInstanceStatusType",
    "AgentTypeType",
    "AgentVisibilityType",
    "BlockingTypeType",
    "CategoryType",
    "CategoryTypeType",
    "ChunkingStrategyType",
    "ClosureTypeType",
    "CopyStatusType",
    "FailureCategoryType",
    "FileTypeType",
    "HitlTaskStatusType",
    "HitlTaskTypeType",
    "IngestionStatusType",
    "JobStatusType",
    "KnowledgeBaseConfigTypeType",
    "ListAgentInstancesPaginatorName",
    "ListArtifactsPaginatorName",
    "ListHitlTasksPaginatorName",
    "ListJobPlanStepsPaginatorName",
    "MeteredUnitType",
    "OwnerTypeType",
    "PlanStepStatusType",
    "PutJobPlanStatusType",
    "ResourceTypeType",
    "RetrievalResultLocationTypeType",
    "RetrievalScopeType",
    "SeverityType",
    "UpdateAgentInstanceStatusType",
    "VersionStatusType",
    "VisibilityType",
)

AccessControlType = Literal["DISABLED", "ENABLED"]
AccountConnectionStatusType = Literal["ACTIVE", "PENDING", "REJECTED"]
ActionType = Literal["APPROVE", "REJECT"]
AgentConfigurationAvailabilityType = Literal[
    "ANY", "NEEDS_RUNTIME_CONFIGURATION", "RUNTIME_CONFIGURATION_AVAILABLE"
]
AgentInstanceStatusType = Literal[
    "COMPLETED", "FAILED", "INVOKED", "INVOKING", "RUNNING", "STOPPED", "STOPPING", "UNRESPONSIVE"
]
AgentTypeType = Literal["ORCHESTRATOR_AGENT", "SUB_AGENT"]
AgentVisibilityType = Literal["PUBLIC", "RESTRICTED"]
BlockingTypeType = Literal["BLOCKING", "NON_BLOCKING"]
CategoryType = Literal["REGULAR", "TOOL_APPROVAL"]
CategoryTypeType = Literal[
    "AGENT_INPUT",
    "AGENT_OUTPUT",
    "CUSTOMER_INPUT",
    "CUSTOMER_OUTPUT",
    "HITL_FROM_AGENT",
    "HITL_FROM_USER",
    "INTERNAL",
    "PLAN_STEP_OUTPUT",
    "PLAN_STEP_SUMMARY",
    "STATE",
]
ChunkingStrategyType = Literal["FIXED_SIZE", "HIERARCHICAL", "NONE", "SEMANTIC"]
ClosureTypeType = Literal["CANCELLED", "CLOSED", "CLOSED_PENDING_NEXT_TASK"]
CopyStatusType = Literal["COMPLETED", "IN_PROGRESS"]
FailureCategoryType = Literal["CUSTOMER_ERROR", "EXPECTED_FAILURE", "SERVICE_ERROR"]
FileTypeType = Literal[
    "CSV", "HTML", "JSON", "MARKDOWN", "OTHER", "PDF", "PPTX", "TXT", "XLSX", "ZIP"
]
HitlTaskStatusType = Literal[
    "AWAITING_APPROVAL",
    "AWAITING_HUMAN_INPUT",
    "CANCELLED",
    "CLOSED",
    "CLOSED_PENDING_NEXT_TASK",
    "CREATED",
    "DELIVERED",
    "IN_PROGRESS",
    "SUBMITTED",
    "WAITING_APPROVAL",
]
HitlTaskTypeType = Literal["DASHBOARD", "NORMAL"]
IngestionStatusType = Literal[
    "COMPLETE", "FAILED", "IN_PROGRESS", "STARTING", "STOPPED", "STOPPING"
]
JobStatusType = Literal[
    "ASSESSING",
    "AWAITING_HUMAN_INPUT",
    "COMPLETED",
    "CREATED",
    "EXECUTING",
    "FAILED",
    "PLANNED",
    "PLANNING",
    "STARTING",
    "STOPPED",
    "STOPPING",
]
KnowledgeBaseConfigTypeType = Literal["TEXT_TITAN_CONFIG"]
ListAgentInstancesPaginatorName = Literal["list_agent_instances"]
ListArtifactsPaginatorName = Literal["list_artifacts"]
ListHitlTasksPaginatorName = Literal["list_hitl_tasks"]
ListJobPlanStepsPaginatorName = Literal["list_job_plan_steps"]
MeteredUnitType = Literal["COUNT"]
OwnerTypeType = Literal["DIRECT_AGENT", "INTERNAL_AGENT", "MARKETPLACE_AGENT"]
PlanStepStatusType = Literal[
    "FAILED", "IN_PROGRESS", "NOT_STARTED", "PENDING_HUMAN_INPUT", "STOPPED", "SUCCEEDED"
]
PutJobPlanStatusType = Literal["COMPLETED", "IN_PROGRESS"]
ResourceTypeType = Literal[
    "ASSESSMENTS_MONTHLY_COMPLETED_ASSESSMENTS",
    "DOT_NET_TRANSFORMATION_BILLED_LOC",
    "DOT_NET_TRANSFORMATION_MONTHLY_LOC",
    "DOT_NET_TRANSFORMATION_MONTHLY_REPOSITORIES",
    "DOT_NET_TRANSFORMATION_TOTAL_LOC",
    "MAINFRAME_ANALYSIS_LOC",
    "MAINFRAME_ASSESSMENT_LOC",
    "MAINFRAME_BUSINESS_RULE_DEPENDENCY_LOC",
    "MAINFRAME_BUSINESS_RULE_LOC",
    "MAINFRAME_DATA_ANALYSIS_LOC",
    "MAINFRAME_DECOMPOSITION_LOC",
    "MAINFRAME_DOCUMENTATION_DEPENDENCY_LOC",
    "MAINFRAME_DOCUMENTATION_LOC",
    "MAINFRAME_LOC",
    "MAINFRAME_PLAN_MIGRATION_ITERATION",
    "MAINFRAME_REFORGE_LOC",
    "MAINFRAME_TESTPLAN_LLM_CALLS",
    "MAINFRAME_TESTPLAN_LOC",
    "MAINFRAME_TESTPLAN_TC_APPROVED",
    "MAINFRAME_TESTPLAN_TC_GENERATED",
    "MAINFRAME_TESTPLAN_TC_GUIDANCE",
    "MAINFRAME_TEST_DATA_COLLECTION_TC_SELECTED",
    "MAINFRAME_TEST_SCRIPT_GENERATION_TC_SELECTED",
    "MAINFRAME_TRANSFORM_LOC",
    "QT_AGENTIC_PLATFORM_BILLING_TEST",
    "QT_AGENTIC_PLATFORM_TEST",
    "VMS_MIGRATED_SUCCESSFUL_COUNT",
    "VM_NETWORKS_DEPLOYED_COUNT",
    "VM_NETWORKS_GENERATED_COUNT",
]
RetrievalResultLocationTypeType = Literal["S3", "WEB"]
RetrievalScopeType = Literal["AGENT_INGESTED", "AWS", "PRODUCT"]
SeverityType = Literal["CRITICAL", "STANDARD"]
UpdateAgentInstanceStatusType = Literal["COMPLETED", "FAILED", "RUNNING", "STOPPED"]
VersionStatusType = Literal["ACTIVE", "CREATED", "IN_VERIFICATION", "VERIFICATION_FAILED"]
VisibilityType = Literal["EXTERNAL", "INTERNAL"]
