# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Type annotations for transformagenticservice service type definitions.

[Open documentation](https://youtype.github.io/boto3_stubs_docs/agent_builder_types/type_defs/)

Usage::

    ```python
    from agent_builder_types.type_defs import AwsAccountConnectionTypeDef

    data: AwsAccountConnectionTypeDef = ...
    ```
"""

import sys
from datetime import datetime
from typing import Any, Dict, List, Mapping, Sequence, Union

from .literals import (
    AccessControlType,
    AccountConnectionStatusType,
    ActionType,
    AgentConfigurationAvailabilityType,
    AgentInstanceStatusType,
    AgentTypeType,
    AgentVisibilityType,
    BlockingTypeType,
    CategoryType,
    CategoryTypeType,
    ChunkingStrategyType,
    ClosureTypeType,
    CopyStatusType,
    FailureCategoryType,
    FileTypeType,
    HitlTaskStatusType,
    HitlTaskTypeType,
    IngestionStatusType,
    JobStatusType,
    MonitoringTypeType,
    OwnerTypeType,
    PlanStepStatusType,
    PutJobPlanStatusType,
    ResourceTypeType,
    RetrievalResultLocationTypeType,
    RetrievalScopeType,
    SeverityType,
    UmrAgreementStatusType,
    UmrEligibilityOutcomeType,
    UmrIncentiveTypeType,
    UmrMigrationPhaseType,
    UmrPartnerTypeType,
    UmrResourceStatusType,
    UmrResourceTypeType,
    UmrRiskLevelType,
    UmrStatusType,
    UpdateAgentInstanceStatusType,
    VersionStatusType,
    VisibilityType,
)

if sys.version_info >= (3, 12):
    from typing import Literal
else:
    from typing_extensions import Literal
if sys.version_info >= (3, 12):
    from typing import NotRequired
else:
    from typing_extensions import NotRequired
if sys.version_info >= (3, 12):
    from typing import TypedDict
else:
    from typing_extensions import TypedDict

__all__ = (
    "AwsAccountConnectionTypeDef",
    "AgentConfigurationTypeDef",
    "AgentInputPayloadTypeDef",
    "AgentInstanceSummaryTypeDef",
    "AgentMetadataSummaryTypeDef",
    "AgentMetadataTypeDef",
    "AgentOutputPayloadTypeDef",
    "AgentTypeFilterTypeDef",
    "AppendModeTypeDef",
    "ArtifactAgentFilterTypeDef",
    "ArtifactCategoryFilterTypeDef",
    "ArtifactPlanStepFilterTypeDef",
    "ArtifactWorkspaceFilterTypeDef",
    "ArtifactTypeTypeDef",
    "FileMetadataTypeDef",
    "AwsTemporaryCredentialsTypeDef",
    "FixedSizeChunkingConfigurationTypeDef",
    "SemanticChunkingConfigurationTypeDef",
    "ResponseMetadataTypeDef",
    "ConnectorSummaryDataTypeDef",
    "ContentDigestTypeDef",
    "HitlTaskArtifactTypeDef",
    "TimestampTypeDef",
    "EntityTypeDef",
    "FilterAttributeTypeDef",
    "IsS3ObjectPresentTypeDef",
    "UmrAgreementTypeDef",
    "UmrEligibilityTypeDef",
    "UmrMigrationPlanTypeDef",
    "HierarchicalChunkingLevelConfigurationTypeDef",
    "HitlTaskFilterTypeDef",
    "JobMetadataTypeDef",
    "StatusDetailsTypeDef",
    "JobPlanStepNodeTypeDef",
    "JobPlanStepTypeDef",
    "JobPlanTreeTypeDef",
    "LimitDefinitionTypeDef",
    "ListAgentFilterTypeDef",
    "PaginatorConfigTypeDef",
    "WorklogOutputTypeDef",
    "MeteredAmountTypeDef",
    "MeteringAttributeTypeDef",
    "PlanStepMappingTypeDef",
    "VectorSearchConfigurationTypeDef",
    "RetrievalQueryTypeDef",
    "RetrievalResultContentTypeDef",
    "RetrievalResultS3LocationTypeDef",
    "RetrievalResultWebLocationTypeDef",
    "StatusInfoTypeDef",
    "UmrResourceOutputTypeDef",
    "AccountConnectionTypeDef",
    "ListAgentsFilterTypeDef",
    "PutJobPlanModeTypeDef",
    "ArtifactFilterTypeDef",
    "ArtifactReferenceTypeDef",
    "ArtifactTypeDef",
    "TemporaryCredentialsTypeDef",
    "CloseHitlTaskResponseTypeDef",
    "CopyArtifactResponseTypeDef",
    "CreateArtifactUploadUrlResponseTypeDef",
    "CreateHitlTaskResponseTypeDef",
    "CreateSkillDownloadUrlResponseTypeDef",
    "GetAgentInstanceResponseTypeDef",
    "GetAgentVersionResponseTypeDef",
    "GetTaskResponseTypeDef",
    "InvokeAgentResponseTypeDef",
    "ListAgentInstancesResponseTypeDef",
    "ListAgentsResponseTypeDef",
    "PutAgreementResponseTypeDef",
    "PutEligibilityResponseTypeDef",
    "PutMigrationPlanResponseTypeDef",
    "PutPartnerDetailsResponseTypeDef",
    "RefreshAuthTokenResponseTypeDef",
    "SendMessageResponseTypeDef",
    "StartHitlTaskResponseTypeDef",
    "StartKnowledgeBaseIngestionResponseTypeDef",
    "UpdateUMRStatusResponseTypeDef",
    "ListConnectorsResponseTypeDef",
    "HitlTaskTypeDef",
    "PlanStepUpdateTypeDef",
    "TimeFilterTypeDef",
    "UmrResourceTypeDef",
    "WorklogTypeDef",
    "RetrievalFilterTypeDef",
    "HierarchicalChunkingConfigurationTypeDef",
    "IngestionScopeMetadataTypeDef",
    "RequestContextTypeDef",
    "JobInfoTypeDef",
    "ListJobPlanStepsResponseTypeDef",
    "MeteringUsageTypeDef",
    "ListWorklogsResponseTypeDef",
    "PutJobPlanResponseTypeDef",
    "RetrievalConfigurationTypeDef",
    "RetrievalResultLocationTypeDef",
    "UmrPartnerDetailsTypeDef",
    "GetConnectorResponseTypeDef",
    "CompleteArtifactUploadResponseTypeDef",
    "CreateArtifactDownloadUrlResponseTypeDef",
    "GetArtifactMetadataResponseTypeDef",
    "ListArtifactsResponseTypeDef",
    "GetTemporaryCredentialsForConnectorResponseTypeDef",
    "GetTemporaryCredentialsForRoleResponseTypeDef",
    "GetHitlTaskResponseTypeDef",
    "ListHitlTasksResponseTypeDef",
    "StepIdFilterTypeDef",
    "UmrResourceUnionTypeDef",
    "WorklogUnionTypeDef",
    "ChunkingConfigurationTypeDef",
    "IngestionTypeDef",
    "AcknowledgeDeletionRequestRequestTypeDef",
    "CloseHitlTaskRequestRequestTypeDef",
    "CompleteArtifactUploadRequestRequestTypeDef",
    "CopyArtifactRequestRequestTypeDef",
    "CreateArtifactDownloadUrlRequestRequestTypeDef",
    "CreateArtifactUploadUrlRequestRequestTypeDef",
    "CreateHitlTaskRequestRequestTypeDef",
    "CreateSkillDownloadUrlRequestRequestTypeDef",
    "CreateWorklogRequestRequestTypeDef",
    "DeleteJobPlanStepRequestRequestTypeDef",
    "DeregisterKnowledgeBaseDocumentRequestRequestTypeDef",
    "GetAgentInstanceRequestRequestTypeDef",
    "GetAgentVersionRequestRequestTypeDef",
    "GetArtifactMetadataRequestRequestTypeDef",
    "GetConnectorRequestRequestTypeDef",
    "GetHitlTaskRequestRequestTypeDef",
    "GetJobRequestRequestTypeDef",
    "GetKnowledgeBaseIngestionRequestRequestTypeDef",
    "GetTaskRequestRequestTypeDef",
    "GetTemporaryCredentialsForConnectorRequestRequestTypeDef",
    "GetTemporaryCredentialsForRoleRequestRequestTypeDef",
    "GetUMRRequestRequestTypeDef",
    "GetUsageRequestRequestTypeDef",
    "InvokeAgentRequestRequestTypeDef",
    "ListAgentInstancesRequestListAgentInstancesPaginateTypeDef",
    "ListAgentInstancesRequestRequestTypeDef",
    "ListAgentsRequestRequestTypeDef",
    "ListArtifactsRequestListArtifactsPaginateTypeDef",
    "ListArtifactsRequestRequestTypeDef",
    "ListConnectorsRequestRequestTypeDef",
    "ListHitlTasksRequestListHitlTasksPaginateTypeDef",
    "ListHitlTasksRequestRequestTypeDef",
    "ListJobPlanStepsRequestListJobPlanStepsPaginateTypeDef",
    "ListJobPlanStepsRequestRequestTypeDef",
    "PublishMeteringEventRequestRequestTypeDef",
    "PutAgreementRequestRequestTypeDef",
    "PutEligibilityRequestRequestTypeDef",
    "PutJobPlanRequestRequestTypeDef",
    "PutMigrationPlanRequestRequestTypeDef",
    "RefreshAuthTokenRequestRequestTypeDef",
    "RegisterKnowledgeBaseDocumentRequestRequestTypeDef",
    "RestoreAgentRequestRequestTypeDef",
    "RollbackMeteringEventRequestRequestTypeDef",
    "SendMessageRequestRequestTypeDef",
    "StartHitlTaskRequestRequestTypeDef",
    "StopAgentRequestRequestTypeDef",
    "UpdateAgentInstanceRequestRequestTypeDef",
    "UpdateJobPlanStepRequestRequestTypeDef",
    "UpdateJobStatusRequestRequestTypeDef",
    "UpdateUMRStatusRequestRequestTypeDef",
    "GetJobResponseTypeDef",
    "GetUsageResponseTypeDef",
    "RetrieveFromKnowledgeBaseRequestRequestTypeDef",
    "RetrievalResultTypeDef",
    "GetUMRResponseTypeDef",
    "WorklogFilterTypeDef",
    "PutPartnerDetailsRequestRequestTypeDef",
    "VectorIngestionConfigurationTypeDef",
    "GetKnowledgeBaseIngestionResponseTypeDef",
    "RetrieveFromKnowledgeBaseResponseTypeDef",
    "ListWorklogsRequestRequestTypeDef",
    "IngestionConfigurationTypeDef",
    "StartKnowledgeBaseIngestionRequestRequestTypeDef",
)

AwsAccountConnectionTypeDef = TypedDict(
    "AwsAccountConnectionTypeDef",
    {
        "status": NotRequired[AccountConnectionStatusType],
        "createdDate": NotRequired[datetime],
        "expirationDate": NotRequired[datetime],
        "accountId": NotRequired[str],
        "roleArn": NotRequired[str],
        "connectionToken": NotRequired[str],
    },
)
AgentConfigurationTypeDef = TypedDict(
    "AgentConfigurationTypeDef",
    {
        "shortDescription": str,
        "agentCard": Dict[str, Any],
        "monitoringType": NotRequired[MonitoringTypeType],
    },
)
AgentInputPayloadTypeDef = TypedDict(
    "AgentInputPayloadTypeDef",
    {
        "serializedPayload": NotRequired[str],
    },
)
AgentInstanceSummaryTypeDef = TypedDict(
    "AgentInstanceSummaryTypeDef",
    {
        "agentInstanceId": str,
        "agentType": AgentTypeType,
        "agentInstanceStatus": AgentInstanceStatusType,
        "agentId": NotRequired[str],
        "agentVersion": NotRequired[str],
    },
)
AgentMetadataSummaryTypeDef = TypedDict(
    "AgentMetadataSummaryTypeDef",
    {
        "name": NotRequired[str],
        "type": NotRequired[AgentTypeType],
        "description": NotRequired[str],
        "accountAccess": NotRequired[AccessControlType],
        "visibility": NotRequired[AgentVisibilityType],
        "ownerType": NotRequired[OwnerTypeType],
        "customerConfigurationRequired": NotRequired[bool],
        "agentConfigurationAvailability": NotRequired[AgentConfigurationAvailabilityType],
        "customerConfiguredAgentDependencies": NotRequired[List[str]],
    },
)
AgentMetadataTypeDef = TypedDict(
    "AgentMetadataTypeDef",
    {
        "type": AgentTypeType,
        "description": str,
        "ownerName": str,
        "ownerAccountId": str,
        "ownerContactInfo": str,
        "ownerType": OwnerTypeType,
        "customerConfigurationRequired": bool,
        "customerConfiguredAgentDependencies": NotRequired[List[str]],
    },
)
AgentOutputPayloadTypeDef = TypedDict(
    "AgentOutputPayloadTypeDef",
    {
        "serializedPayload": NotRequired[str],
    },
)
AgentTypeFilterTypeDef = TypedDict(
    "AgentTypeFilterTypeDef",
    {
        "agentType": NotRequired[AgentTypeType],
    },
)
AppendModeTypeDef = TypedDict(
    "AppendModeTypeDef",
    {
        "parentStepId": str,
        "afterStepId": NotRequired[str],
    },
)
ArtifactAgentFilterTypeDef = TypedDict(
    "ArtifactAgentFilterTypeDef",
    {
        "agentInstanceId": str,
        "category": NotRequired[CategoryTypeType],
    },
)
ArtifactCategoryFilterTypeDef = TypedDict(
    "ArtifactCategoryFilterTypeDef",
    {
        "category": CategoryTypeType,
        "artifactLabel": NotRequired[str],
    },
)
ArtifactPlanStepFilterTypeDef = TypedDict(
    "ArtifactPlanStepFilterTypeDef",
    {
        "planStepId": str,
        "category": CategoryTypeType,
    },
)
ArtifactWorkspaceFilterTypeDef = TypedDict(
    "ArtifactWorkspaceFilterTypeDef",
    {
        "category": CategoryTypeType,
        "artifactLabel": NotRequired[str],
    },
)
ArtifactTypeTypeDef = TypedDict(
    "ArtifactTypeTypeDef",
    {
        "categoryType": CategoryTypeType,
        "fileType": FileTypeType,
        "schemaType": NotRequired[str],
    },
)
FileMetadataTypeDef = TypedDict(
    "FileMetadataTypeDef",
    {
        "path": str,
        "description": NotRequired[str],
    },
)
AwsTemporaryCredentialsTypeDef = TypedDict(
    "AwsTemporaryCredentialsTypeDef",
    {
        "accessKey": NotRequired[str],
        "secretKey": NotRequired[str],
        "accessToken": NotRequired[str],
        "expirationTime": NotRequired[datetime],
    },
)
FixedSizeChunkingConfigurationTypeDef = TypedDict(
    "FixedSizeChunkingConfigurationTypeDef",
    {
        "maxTokens": int,
        "overlapPercentage": int,
    },
)
SemanticChunkingConfigurationTypeDef = TypedDict(
    "SemanticChunkingConfigurationTypeDef",
    {
        "breakpointPercentileThreshold": int,
        "bufferSize": int,
        "maxTokens": int,
    },
)
ResponseMetadataTypeDef = TypedDict(
    "ResponseMetadataTypeDef",
    {
        "RequestId": str,
        "HTTPStatusCode": int,
        "HTTPHeaders": Dict[str, str],
        "RetryAttempts": int,
        "HostId": NotRequired[str],
    },
)
ConnectorSummaryDataTypeDef = TypedDict(
    "ConnectorSummaryDataTypeDef",
    {
        "connectorId": str,
        "connectorName": NotRequired[str],
        "description": NotRequired[str],
        "connectorType": NotRequired[str],
        "targetRegions": NotRequired[List[str]],
    },
)
ContentDigestTypeDef = TypedDict(
    "ContentDigestTypeDef",
    {
        "sha256": NotRequired[str],
    },
)
HitlTaskArtifactTypeDef = TypedDict(
    "HitlTaskArtifactTypeDef",
    {
        "artifactId": NotRequired[str],
    },
)
TimestampTypeDef = Union[datetime, str]
EntityTypeDef = TypedDict(
    "EntityTypeDef",
    {
        "accountIdEntity": NotRequired[Mapping[str, Any]],
    },
)
FilterAttributeTypeDef = TypedDict(
    "FilterAttributeTypeDef",
    {
        "key": str,
        "value": Mapping[str, Any],
    },
)
IsS3ObjectPresentTypeDef = TypedDict(
    "IsS3ObjectPresentTypeDef",
    {
        "publicBucket": NotRequired[bool],
        "privateBucket": NotRequired[bool],
    },
)
UmrAgreementTypeDef = TypedDict(
    "UmrAgreementTypeDef",
    {
        "agreementId": str,
        "agreementStatus": UmrAgreementStatusType,
        "agreementType": NotRequired[UmrIncentiveTypeType],
        "executedTimestamp": NotRequired[datetime],
        "amendmentVersion": NotRequired[int],
        "agreementUrl": NotRequired[str],
        "signedBy": NotRequired[str],
        "awsSignatory": NotRequired[str],
        "createdAt": NotRequired[datetime],
        "updatedAt": NotRequired[datetime],
    },
)
UmrEligibilityTypeDef = TypedDict(
    "UmrEligibilityTypeDef",
    {
        "outcome": UmrEligibilityOutcomeType,
        "assessmentDate": datetime,
        "assessmentScore": NotRequired[int],
        "riskLevel": NotRequired[UmrRiskLevelType],
        "qualificationCriteria": NotRequired[Dict[str, bool]],
        "createdAt": NotRequired[datetime],
        "updatedAt": NotRequired[datetime],
    },
)
UmrMigrationPlanTypeDef = TypedDict(
    "UmrMigrationPlanTypeDef",
    {
        "incentiveType": UmrIncentiveTypeType,
        "startDate": datetime,
        "endDate": datetime,
        "creditCap": float,
        "creditPercentage": NotRequired[float],
        "linkedAccountDisbursement": NotRequired[bool],
        "baselineSpend": NotRequired[Dict[str, float]],
        "programFlags": NotRequired[Dict[str, bool]],
        "partnerSpmsId": NotRequired[str],
        "createdAt": NotRequired[datetime],
        "updatedAt": NotRequired[datetime],
    },
)
HierarchicalChunkingLevelConfigurationTypeDef = TypedDict(
    "HierarchicalChunkingLevelConfigurationTypeDef",
    {
        "maxTokens": int,
    },
)
HitlTaskFilterTypeDef = TypedDict(
    "HitlTaskFilterTypeDef",
    {
        "taskStatus": NotRequired[HitlTaskStatusType],
        "agentInstanceId": NotRequired[str],
        "stepId": NotRequired[str],
        "tag": NotRequired[str],
        "blockingType": NotRequired[BlockingTypeType],
        "categories": NotRequired[Sequence[CategoryType]],
    },
)
JobMetadataTypeDef = TypedDict(
    "JobMetadataTypeDef",
    {
        "jobId": str,
        "workspaceId": str,
    },
)
StatusDetailsTypeDef = TypedDict(
    "StatusDetailsTypeDef",
    {
        "status": JobStatusType,
        "failureReason": NotRequired[str],
    },
)
JobPlanStepNodeTypeDef = TypedDict(
    "JobPlanStepNodeTypeDef",
    {
        "stepLabel": str,
        "stepName": str,
        "description": str,
        "subSteps": NotRequired[Sequence[Dict[str, Any]]],
    },
)
JobPlanStepTypeDef = TypedDict(
    "JobPlanStepTypeDef",
    {
        "stepId": str,
        "parentStepId": str,
        "stepLabel": str,
        "stepName": str,
        "description": str,
        "score": NotRequired[float],
        "startTime": NotRequired[datetime],
        "endTime": NotRequired[datetime],
        "status": NotRequired[PlanStepStatusType],
    },
)
JobPlanTreeTypeDef = TypedDict(
    "JobPlanTreeTypeDef",
    {
        "nodes": NotRequired[Sequence["JobPlanStepNodeTypeDef"]],
    },
)
LimitDefinitionTypeDef = TypedDict(
    "LimitDefinitionTypeDef",
    {
        "limit": float,
        "unit": Literal["COUNT"],
    },
)
ListAgentFilterTypeDef = TypedDict(
    "ListAgentFilterTypeDef",
    {
        "requesterAgentInstanceId": NotRequired[str],
    },
)
PaginatorConfigTypeDef = TypedDict(
    "PaginatorConfigTypeDef",
    {
        "MaxItems": NotRequired[int],
        "PageSize": NotRequired[int],
        "StartingToken": NotRequired[str],
    },
)
WorklogOutputTypeDef = TypedDict(
    "WorklogOutputTypeDef",
    {
        "timestamp": datetime,
        "attributeMap": Dict[str, str],
        "description": NotRequired[str],
    },
)
MeteredAmountTypeDef = TypedDict(
    "MeteredAmountTypeDef",
    {
        "amount": NotRequired[int],
        "unit": NotRequired[Literal["COUNT"]],
    },
)
MeteringAttributeTypeDef = TypedDict(
    "MeteringAttributeTypeDef",
    {
        "name": str,
        "value": str,
    },
)
PlanStepMappingTypeDef = TypedDict(
    "PlanStepMappingTypeDef",
    {
        "stepLabel": str,
        "stepId": str,
    },
)
VectorSearchConfigurationTypeDef = TypedDict(
    "VectorSearchConfigurationTypeDef",
    {
        "numberOfResults": NotRequired[int],
        "filter": NotRequired["RetrievalFilterTypeDef"],
    },
)
RetrievalQueryTypeDef = TypedDict(
    "RetrievalQueryTypeDef",
    {
        "text": str,
    },
)
RetrievalResultContentTypeDef = TypedDict(
    "RetrievalResultContentTypeDef",
    {
        "text": NotRequired[str],
    },
)
RetrievalResultS3LocationTypeDef = TypedDict(
    "RetrievalResultS3LocationTypeDef",
    {
        "uri": NotRequired[str],
    },
)
RetrievalResultWebLocationTypeDef = TypedDict(
    "RetrievalResultWebLocationTypeDef",
    {
        "url": NotRequired[str],
    },
)
StatusInfoTypeDef = TypedDict(
    "StatusInfoTypeDef",
    {
        "status": JobStatusType,
        "failureCategory": NotRequired[FailureCategoryType],
        "failureType": NotRequired[str],
    },
)
UmrResourceOutputTypeDef = TypedDict(
    "UmrResourceOutputTypeDef",
    {
        "resourceType": UmrResourceTypeType,
        "resourceId": str,
        "status": UmrResourceStatusType,
        "metadata": NotRequired[Dict[str, str]],
        "createdAt": NotRequired[datetime],
    },
)
AccountConnectionTypeDef = TypedDict(
    "AccountConnectionTypeDef",
    {
        "awsAccountConnection": NotRequired[AwsAccountConnectionTypeDef],
    },
)
ListAgentsFilterTypeDef = TypedDict(
    "ListAgentsFilterTypeDef",
    {
        "agentTypeFilter": NotRequired[AgentTypeFilterTypeDef],
    },
)
PutJobPlanModeTypeDef = TypedDict(
    "PutJobPlanModeTypeDef",
    {
        "override": NotRequired[Mapping[str, Any]],
        "append": NotRequired[AppendModeTypeDef],
    },
)
ArtifactFilterTypeDef = TypedDict(
    "ArtifactFilterTypeDef",
    {
        "agentFilter": NotRequired[ArtifactAgentFilterTypeDef],
        "categoryFilter": NotRequired[ArtifactCategoryFilterTypeDef],
        "workspaceFilter": NotRequired[ArtifactWorkspaceFilterTypeDef],
        "planStepFilter": NotRequired[ArtifactPlanStepFilterTypeDef],
    },
)
ArtifactReferenceTypeDef = TypedDict(
    "ArtifactReferenceTypeDef",
    {
        "artifactType": NotRequired[ArtifactTypeTypeDef],
        "artifactId": NotRequired[str],
    },
)
ArtifactTypeDef = TypedDict(
    "ArtifactTypeDef",
    {
        "artifactId": str,
        "artifactType": ArtifactTypeTypeDef,
        "artifactCreatedTimestamp": datetime,
        "artifactExpiryTimestamp": datetime,
        "artifactLabel": NotRequired[str],
        "fileMetadata": NotRequired[FileMetadataTypeDef],
        "sizeInBytes": NotRequired[int],
        "storedInAtxBucket": NotRequired[bool],
    },
)
TemporaryCredentialsTypeDef = TypedDict(
    "TemporaryCredentialsTypeDef",
    {
        "awsTemporaryCredentials": NotRequired[AwsTemporaryCredentialsTypeDef],
    },
)
CloseHitlTaskResponseTypeDef = TypedDict(
    "CloseHitlTaskResponseTypeDef",
    {
        "hitlTaskStatus": HitlTaskStatusType,
        "ResponseMetadata": ResponseMetadataTypeDef,
    },
)
CopyArtifactResponseTypeDef = TypedDict(
    "CopyArtifactResponseTypeDef",
    {
        "copyStatus": CopyStatusType,
        "ResponseMetadata": ResponseMetadataTypeDef,
    },
)
CreateArtifactUploadUrlResponseTypeDef = TypedDict(
    "CreateArtifactUploadUrlResponseTypeDef",
    {
        "artifactId": str,
        "s3preSignedUrl": str,
        "s3UrlExpiryTimestamp": datetime,
        "requestHeaders": Dict[str, List[str]],
        "ResponseMetadata": ResponseMetadataTypeDef,
    },
)
CreateHitlTaskResponseTypeDef = TypedDict(
    "CreateHitlTaskResponseTypeDef",
    {
        "hitlTaskId": str,
        "ResponseMetadata": ResponseMetadataTypeDef,
    },
)
CreateSkillDownloadUrlResponseTypeDef = TypedDict(
    "CreateSkillDownloadUrlResponseTypeDef",
    {
        "s3PreSignedUrl": str,
        "s3UrlExpiryTimestamp": int,
        "requestHeaders": Dict[str, List[str]],
        "version": str,
        "ResponseMetadata": ResponseMetadataTypeDef,
    },
)
GetAgentInstanceResponseTypeDef = TypedDict(
    "GetAgentInstanceResponseTypeDef",
    {
        "agentInstanceId": str,
        "agentType": AgentTypeType,
        "agentId": str,
        "agentVersion": str,
        "agentInstanceStatus": AgentInstanceStatusType,
        "agentInput": AgentInputPayloadTypeDef,
        "agentOutput": AgentOutputPayloadTypeDef,
        "ResponseMetadata": ResponseMetadataTypeDef,
    },
)
GetAgentVersionResponseTypeDef = TypedDict(
    "GetAgentVersionResponseTypeDef",
    {
        "version": str,
        "metadata": AgentMetadataTypeDef,
        "visibility": AgentVisibilityType,
        "configuration": AgentConfigurationTypeDef,
        "status": VersionStatusType,
        "statusMessage": str,
        "ResponseMetadata": ResponseMetadataTypeDef,
    },
)
GetTaskResponseTypeDef = TypedDict(
    "GetTaskResponseTypeDef",
    {
        "result": Dict[str, Any],
        "error": Dict[str, Any],
        "ResponseMetadata": ResponseMetadataTypeDef,
    },
)
InvokeAgentResponseTypeDef = TypedDict(
    "InvokeAgentResponseTypeDef",
    {
        "agentInstanceId": str,
        "ResponseMetadata": ResponseMetadataTypeDef,
    },
)
ListAgentInstancesResponseTypeDef = TypedDict(
    "ListAgentInstancesResponseTypeDef",
    {
        "agentInstanceSummaries": List[AgentInstanceSummaryTypeDef],
        "nextToken": str,
        "ResponseMetadata": ResponseMetadataTypeDef,
    },
)
ListAgentsResponseTypeDef = TypedDict(
    "ListAgentsResponseTypeDef",
    {
        "items": List[AgentMetadataSummaryTypeDef],
        "nextToken": str,
        "ResponseMetadata": ResponseMetadataTypeDef,
    },
)
PutAgreementResponseTypeDef = TypedDict(
    "PutAgreementResponseTypeDef",
    {
        "version": int,
        "ResponseMetadata": ResponseMetadataTypeDef,
    },
)
PutEligibilityResponseTypeDef = TypedDict(
    "PutEligibilityResponseTypeDef",
    {
        "version": int,
        "ResponseMetadata": ResponseMetadataTypeDef,
    },
)
PutMigrationPlanResponseTypeDef = TypedDict(
    "PutMigrationPlanResponseTypeDef",
    {
        "version": int,
        "ResponseMetadata": ResponseMetadataTypeDef,
    },
)
PutPartnerDetailsResponseTypeDef = TypedDict(
    "PutPartnerDetailsResponseTypeDef",
    {
        "version": int,
        "ResponseMetadata": ResponseMetadataTypeDef,
    },
)
RefreshAuthTokenResponseTypeDef = TypedDict(
    "RefreshAuthTokenResponseTypeDef",
    {
        "authorizationToken": str,
        "authorizationExpiration": datetime,
        "ResponseMetadata": ResponseMetadataTypeDef,
    },
)
SendMessageResponseTypeDef = TypedDict(
    "SendMessageResponseTypeDef",
    {
        "result": Dict[str, Any],
        "error": Dict[str, Any],
        "ResponseMetadata": ResponseMetadataTypeDef,
    },
)
StartHitlTaskResponseTypeDef = TypedDict(
    "StartHitlTaskResponseTypeDef",
    {
        "hitlTaskStatus": HitlTaskStatusType,
        "ResponseMetadata": ResponseMetadataTypeDef,
    },
)
StartKnowledgeBaseIngestionResponseTypeDef = TypedDict(
    "StartKnowledgeBaseIngestionResponseTypeDef",
    {
        "ingestionId": str,
        "ResponseMetadata": ResponseMetadataTypeDef,
    },
)
UpdateUMRStatusResponseTypeDef = TypedDict(
    "UpdateUMRStatusResponseTypeDef",
    {
        "version": int,
        "ResponseMetadata": ResponseMetadataTypeDef,
    },
)
ListConnectorsResponseTypeDef = TypedDict(
    "ListConnectorsResponseTypeDef",
    {
        "connectorsList": List[ConnectorSummaryDataTypeDef],
        "nextToken": str,
        "ResponseMetadata": ResponseMetadataTypeDef,
    },
)
HitlTaskTypeDef = TypedDict(
    "HitlTaskTypeDef",
    {
        "hitlTaskId": str,
        "hitlTaskStatus": HitlTaskStatusType,
        "uxComponentId": str,
        "blockingType": BlockingTypeType,
        "severity": SeverityType,
        "hitlTaskType": HitlTaskTypeType,
        "createdAt": NotRequired[datetime],
        "updatedAt": NotRequired[datetime],
        "completedAt": NotRequired[datetime],
        "tag": NotRequired[str],
        "stepId": NotRequired[str],
        "agentArtifact": NotRequired[HitlTaskArtifactTypeDef],
        "humanArtifact": NotRequired[HitlTaskArtifactTypeDef],
        "description": NotRequired[str],
        "action": NotRequired[ActionType],
        "category": NotRequired[CategoryType],
    },
)
PlanStepUpdateTypeDef = TypedDict(
    "PlanStepUpdateTypeDef",
    {
        "stepId": str,
        "startTime": NotRequired[TimestampTypeDef],
        "endTime": NotRequired[TimestampTypeDef],
        "status": NotRequired[PlanStepStatusType],
        "description": NotRequired[str],
    },
)
TimeFilterTypeDef = TypedDict(
    "TimeFilterTypeDef",
    {
        "startTime": NotRequired[TimestampTypeDef],
        "endTime": NotRequired[TimestampTypeDef],
    },
)
UmrResourceTypeDef = TypedDict(
    "UmrResourceTypeDef",
    {
        "resourceType": UmrResourceTypeType,
        "resourceId": str,
        "status": UmrResourceStatusType,
        "metadata": NotRequired[Mapping[str, str]],
        "createdAt": NotRequired[TimestampTypeDef],
    },
)
WorklogTypeDef = TypedDict(
    "WorklogTypeDef",
    {
        "timestamp": TimestampTypeDef,
        "attributeMap": Mapping[str, str],
        "description": NotRequired[str],
    },
)
RetrievalFilterTypeDef = TypedDict(
    "RetrievalFilterTypeDef",
    {
        "equals": NotRequired[FilterAttributeTypeDef],
        "notEquals": NotRequired[FilterAttributeTypeDef],
        "greaterThan": NotRequired[FilterAttributeTypeDef],
        "greaterThanOrEquals": NotRequired[FilterAttributeTypeDef],
        "lessThan": NotRequired[FilterAttributeTypeDef],
        "lessThanOrEquals": NotRequired[FilterAttributeTypeDef],
        "in": NotRequired[FilterAttributeTypeDef],
        "notIn": NotRequired[FilterAttributeTypeDef],
        "startsWith": NotRequired[FilterAttributeTypeDef],
        "listContains": NotRequired[FilterAttributeTypeDef],
        "stringContains": NotRequired[FilterAttributeTypeDef],
        "andAll": NotRequired[Sequence[Dict[str, Any]]],
        "orAll": NotRequired[Sequence[Dict[str, Any]]],
    },
)
HierarchicalChunkingConfigurationTypeDef = TypedDict(
    "HierarchicalChunkingConfigurationTypeDef",
    {
        "levelConfigurations": Sequence[HierarchicalChunkingLevelConfigurationTypeDef],
        "overlapTokens": int,
    },
)
IngestionScopeMetadataTypeDef = TypedDict(
    "IngestionScopeMetadataTypeDef",
    {
        "jobScope": NotRequired[JobMetadataTypeDef],
    },
)
RequestContextTypeDef = TypedDict(
    "RequestContextTypeDef",
    {
        "jobMetadata": JobMetadataTypeDef,
        "agentInstanceId": str,
        "authorizationToken": str,
    },
)
JobInfoTypeDef = TypedDict(
    "JobInfoTypeDef",
    {
        "jobId": NotRequired[str],
        "workspaceId": NotRequired[str],
        "statusDetails": NotRequired[StatusDetailsTypeDef],
        "creationTime": NotRequired[datetime],
        "startExecutionTime": NotRequired[datetime],
        "endExecutionTime": NotRequired[datetime],
        "objective": NotRequired[str],
        "jobName": NotRequired[str],
        "intent": NotRequired[str],
        "runCountId": NotRequired[int],
        "latestPlanVersion": NotRequired[int],
        "clientSource": NotRequired[str],
        "clientAppId": NotRequired[str],
        "softDeleted": NotRequired[bool],
    },
)
ListJobPlanStepsResponseTypeDef = TypedDict(
    "ListJobPlanStepsResponseTypeDef",
    {
        "steps": List[JobPlanStepTypeDef],
        "nextToken": str,
        "ResponseMetadata": ResponseMetadataTypeDef,
    },
)
MeteringUsageTypeDef = TypedDict(
    "MeteringUsageTypeDef",
    {
        "resourceType": ResourceTypeType,
        "amount": float,
        "unit": Literal["COUNT"],
        "limits": LimitDefinitionTypeDef,
    },
)
ListWorklogsResponseTypeDef = TypedDict(
    "ListWorklogsResponseTypeDef",
    {
        "worklogs": List[WorklogOutputTypeDef],
        "nextToken": str,
        "ResponseMetadata": ResponseMetadataTypeDef,
    },
)
PutJobPlanResponseTypeDef = TypedDict(
    "PutJobPlanResponseTypeDef",
    {
        "status": PutJobPlanStatusType,
        "mappings": List[PlanStepMappingTypeDef],
        "ResponseMetadata": ResponseMetadataTypeDef,
    },
)
RetrievalConfigurationTypeDef = TypedDict(
    "RetrievalConfigurationTypeDef",
    {
        "vectorSearchConfiguration": VectorSearchConfigurationTypeDef,
    },
)
RetrievalResultLocationTypeDef = TypedDict(
    "RetrievalResultLocationTypeDef",
    {
        "type": RetrievalResultLocationTypeType,
        "s3Location": NotRequired[RetrievalResultS3LocationTypeDef],
        "webLocation": NotRequired[RetrievalResultWebLocationTypeDef],
    },
)
UmrPartnerDetailsTypeDef = TypedDict(
    "UmrPartnerDetailsTypeDef",
    {
        "partnerAccountId": str,
        "partnerName": str,
        "partnerType": NotRequired[UmrPartnerTypeType],
        "migrationPhase": NotRequired[UmrMigrationPhaseType],
        "prmId": NotRequired[str],
        "workspaceId": NotRequired[str],
        "resources": NotRequired[List[UmrResourceOutputTypeDef]],
        "createdAt": NotRequired[datetime],
        "updatedAt": NotRequired[datetime],
    },
)
GetConnectorResponseTypeDef = TypedDict(
    "GetConnectorResponseTypeDef",
    {
        "connectorName": str,
        "description": str,
        "connectorType": str,
        "configuration": Dict[str, str],
        "accountConnection": AccountConnectionTypeDef,
        "targetRegions": List[str],
        "ResponseMetadata": ResponseMetadataTypeDef,
    },
)
CompleteArtifactUploadResponseTypeDef = TypedDict(
    "CompleteArtifactUploadResponseTypeDef",
    {
        "artifact": ArtifactTypeDef,
        "ResponseMetadata": ResponseMetadataTypeDef,
    },
)
CreateArtifactDownloadUrlResponseTypeDef = TypedDict(
    "CreateArtifactDownloadUrlResponseTypeDef",
    {
        "s3preSignedUrl": str,
        "s3UrlExpiryTimestamp": datetime,
        "artifactType": ArtifactTypeTypeDef,
        "artifactLabel": str,
        "requestHeaders": Dict[str, List[str]],
        "artifact": ArtifactTypeDef,
        "ResponseMetadata": ResponseMetadataTypeDef,
    },
)
GetArtifactMetadataResponseTypeDef = TypedDict(
    "GetArtifactMetadataResponseTypeDef",
    {
        "artifact": ArtifactTypeDef,
        "isS3ObjectPresent": IsS3ObjectPresentTypeDef,
        "ResponseMetadata": ResponseMetadataTypeDef,
    },
)
ListArtifactsResponseTypeDef = TypedDict(
    "ListArtifactsResponseTypeDef",
    {
        "artifacts": List[ArtifactTypeDef],
        "nextToken": str,
        "ResponseMetadata": ResponseMetadataTypeDef,
    },
)
GetTemporaryCredentialsForConnectorResponseTypeDef = TypedDict(
    "GetTemporaryCredentialsForConnectorResponseTypeDef",
    {
        "temporaryCredentials": TemporaryCredentialsTypeDef,
        "connectorConfiguration": Dict[str, str],
        "targetRegion": str,
        "ResponseMetadata": ResponseMetadataTypeDef,
    },
)
GetTemporaryCredentialsForRoleResponseTypeDef = TypedDict(
    "GetTemporaryCredentialsForRoleResponseTypeDef",
    {
        "temporaryCredentials": TemporaryCredentialsTypeDef,
        "roleArn": str,
        "ResponseMetadata": ResponseMetadataTypeDef,
    },
)
GetHitlTaskResponseTypeDef = TypedDict(
    "GetHitlTaskResponseTypeDef",
    {
        "hitlTask": HitlTaskTypeDef,
        "ResponseMetadata": ResponseMetadataTypeDef,
    },
)
ListHitlTasksResponseTypeDef = TypedDict(
    "ListHitlTasksResponseTypeDef",
    {
        "hitlTasks": List[HitlTaskTypeDef],
        "nextToken": str,
        "ResponseMetadata": ResponseMetadataTypeDef,
    },
)
StepIdFilterTypeDef = TypedDict(
    "StepIdFilterTypeDef",
    {
        "stepId": str,
        "timeFilter": NotRequired[TimeFilterTypeDef],
    },
)
UmrResourceUnionTypeDef = Union[UmrResourceTypeDef, UmrResourceOutputTypeDef]
WorklogUnionTypeDef = Union[WorklogTypeDef, WorklogOutputTypeDef]
ChunkingConfigurationTypeDef = TypedDict(
    "ChunkingConfigurationTypeDef",
    {
        "chunkingStrategy": ChunkingStrategyType,
        "fixedSizeChunkingConfiguration": NotRequired[FixedSizeChunkingConfigurationTypeDef],
        "hierarchicalChunkingConfiguration": NotRequired[HierarchicalChunkingConfigurationTypeDef],
        "semanticChunkingConfiguration": NotRequired[SemanticChunkingConfigurationTypeDef],
    },
)
IngestionTypeDef = TypedDict(
    "IngestionTypeDef",
    {
        "ingestionId": str,
        "status": IngestionStatusType,
        "ingestionScopeMetadata": IngestionScopeMetadataTypeDef,
        "createdAt": NotRequired[datetime],
        "updatedAt": NotRequired[datetime],
        "failureReason": NotRequired[str],
    },
)
AcknowledgeDeletionRequestRequestTypeDef = TypedDict(
    "AcknowledgeDeletionRequestRequestTypeDef",
    {
        "requestContext": RequestContextTypeDef,
        "deletionAcknowledgementToken": str,
    },
)
CloseHitlTaskRequestRequestTypeDef = TypedDict(
    "CloseHitlTaskRequestRequestTypeDef",
    {
        "requestContext": RequestContextTypeDef,
        "hitlTaskId": str,
        "closureType": NotRequired[ClosureTypeType],
        "idempotencyToken": NotRequired[str],
    },
)
CompleteArtifactUploadRequestRequestTypeDef = TypedDict(
    "CompleteArtifactUploadRequestRequestTypeDef",
    {
        "requestContext": RequestContextTypeDef,
        "artifactId": str,
    },
)
CopyArtifactRequestRequestTypeDef = TypedDict(
    "CopyArtifactRequestRequestTypeDef",
    {
        "requestContext": RequestContextTypeDef,
        "artifactId": str,
        "idempotencyToken": NotRequired[str],
    },
)
CreateArtifactDownloadUrlRequestRequestTypeDef = TypedDict(
    "CreateArtifactDownloadUrlRequestRequestTypeDef",
    {
        "requestContext": RequestContextTypeDef,
        "artifactId": str,
        "visibility": NotRequired[VisibilityType],
    },
)
CreateArtifactUploadUrlRequestRequestTypeDef = TypedDict(
    "CreateArtifactUploadUrlRequestRequestTypeDef",
    {
        "requestContext": RequestContextTypeDef,
        "contentDigest": ContentDigestTypeDef,
        "artifactReference": ArtifactReferenceTypeDef,
        "label": NotRequired[str],
        "planStepId": NotRequired[str],
        "visibility": NotRequired[VisibilityType],
        "fileMetadata": NotRequired[FileMetadataTypeDef],
    },
)
CreateHitlTaskRequestRequestTypeDef = TypedDict(
    "CreateHitlTaskRequestRequestTypeDef",
    {
        "requestContext": RequestContextTypeDef,
        "uxComponentId": str,
        "description": str,
        "title": str,
        "severity": NotRequired[SeverityType],
        "hitlTaskType": NotRequired[HitlTaskTypeType],
        "stepId": NotRequired[str],
        "blockingType": NotRequired[BlockingTypeType],
        "hitlRequestArtifact": NotRequired[HitlTaskArtifactTypeDef],
        "expiredAt": NotRequired[TimestampTypeDef],
        "tag": NotRequired[str],
        "idempotencyToken": NotRequired[str],
        "category": NotRequired[CategoryType],
    },
)
CreateSkillDownloadUrlRequestRequestTypeDef = TypedDict(
    "CreateSkillDownloadUrlRequestRequestTypeDef",
    {
        "requestContext": RequestContextTypeDef,
        "skillName": str,
        "idempotencyToken": NotRequired[str],
        "version": NotRequired[str],
    },
)
CreateWorklogRequestRequestTypeDef = TypedDict(
    "CreateWorklogRequestRequestTypeDef",
    {
        "requestContext": RequestContextTypeDef,
        "worklog": WorklogTypeDef,
        "idempotencyToken": NotRequired[str],
    },
)
DeleteJobPlanStepRequestRequestTypeDef = TypedDict(
    "DeleteJobPlanStepRequestRequestTypeDef",
    {
        "requestContext": RequestContextTypeDef,
        "stepId": str,
        "idempotencyToken": NotRequired[str],
    },
)
DeregisterKnowledgeBaseDocumentRequestRequestTypeDef = TypedDict(
    "DeregisterKnowledgeBaseDocumentRequestRequestTypeDef",
    {
        "requestContext": RequestContextTypeDef,
        "artifactId": str,
        "knowledgeBaseConfigType": Literal["TEXT_TITAN_CONFIG"],
    },
)
GetAgentInstanceRequestRequestTypeDef = TypedDict(
    "GetAgentInstanceRequestRequestTypeDef",
    {
        "requestContext": RequestContextTypeDef,
        "agentInstanceId": str,
    },
)
GetAgentVersionRequestRequestTypeDef = TypedDict(
    "GetAgentVersionRequestRequestTypeDef",
    {
        "requestContext": RequestContextTypeDef,
        "name": str,
        "version": NotRequired[str],
    },
)
GetArtifactMetadataRequestRequestTypeDef = TypedDict(
    "GetArtifactMetadataRequestRequestTypeDef",
    {
        "requestContext": RequestContextTypeDef,
        "artifactId": str,
    },
)
GetConnectorRequestRequestTypeDef = TypedDict(
    "GetConnectorRequestRequestTypeDef",
    {
        "requestContext": RequestContextTypeDef,
        "connectorId": str,
    },
)
GetHitlTaskRequestRequestTypeDef = TypedDict(
    "GetHitlTaskRequestRequestTypeDef",
    {
        "requestContext": RequestContextTypeDef,
        "hitlTaskId": str,
    },
)
GetJobRequestRequestTypeDef = TypedDict(
    "GetJobRequestRequestTypeDef",
    {
        "requestContext": RequestContextTypeDef,
        "includeObjective": NotRequired[bool],
    },
)
GetKnowledgeBaseIngestionRequestRequestTypeDef = TypedDict(
    "GetKnowledgeBaseIngestionRequestRequestTypeDef",
    {
        "requestContext": RequestContextTypeDef,
        "ingestionId": str,
    },
)
GetTaskRequestRequestTypeDef = TypedDict(
    "GetTaskRequestRequestTypeDef",
    {
        "requestContext": RequestContextTypeDef,
        "agentInstanceId": str,
        "params": NotRequired[Mapping[str, Any]],
    },
)
GetTemporaryCredentialsForConnectorRequestRequestTypeDef = TypedDict(
    "GetTemporaryCredentialsForConnectorRequestRequestTypeDef",
    {
        "requestContext": RequestContextTypeDef,
        "connectorId": str,
        "targetRegion": NotRequired[str],
    },
)
GetTemporaryCredentialsForRoleRequestRequestTypeDef = TypedDict(
    "GetTemporaryCredentialsForRoleRequestRequestTypeDef",
    {
        "requestContext": RequestContextTypeDef,
        "hitlTaskId": str,
    },
)
GetUMRRequestRequestTypeDef = TypedDict(
    "GetUMRRequestRequestTypeDef",
    {
        "requestContext": RequestContextTypeDef,
    },
)
GetUsageRequestRequestTypeDef = TypedDict(
    "GetUsageRequestRequestTypeDef",
    {
        "requestContext": RequestContextTypeDef,
        "resourceTypes": Sequence[ResourceTypeType],
    },
)
InvokeAgentRequestRequestTypeDef = TypedDict(
    "InvokeAgentRequestRequestTypeDef",
    {
        "requestContext": RequestContextTypeDef,
        "agentId": str,
        "inputPayload": NotRequired[AgentInputPayloadTypeDef],
        "idempotencyToken": NotRequired[str],
        "agentVersion": NotRequired[str],
        "agentInstanceId": NotRequired[str],
        "agentType": NotRequired[AgentTypeType],
    },
)
ListAgentInstancesRequestListAgentInstancesPaginateTypeDef = TypedDict(
    "ListAgentInstancesRequestListAgentInstancesPaginateTypeDef",
    {
        "requestContext": RequestContextTypeDef,
        "agentFilter": NotRequired[ListAgentFilterTypeDef],
        "PaginationConfig": NotRequired[PaginatorConfigTypeDef],
    },
)
ListAgentInstancesRequestRequestTypeDef = TypedDict(
    "ListAgentInstancesRequestRequestTypeDef",
    {
        "requestContext": RequestContextTypeDef,
        "nextToken": NotRequired[str],
        "agentFilter": NotRequired[ListAgentFilterTypeDef],
        "maxResults": NotRequired[int],
    },
)
ListAgentsRequestRequestTypeDef = TypedDict(
    "ListAgentsRequestRequestTypeDef",
    {
        "requestContext": RequestContextTypeDef,
        "agentFilter": NotRequired[ListAgentsFilterTypeDef],
        "nextToken": NotRequired[str],
        "maxResults": NotRequired[int],
    },
)
ListArtifactsRequestListArtifactsPaginateTypeDef = TypedDict(
    "ListArtifactsRequestListArtifactsPaginateTypeDef",
    {
        "requestContext": RequestContextTypeDef,
        "artifactFilter": NotRequired[ArtifactFilterTypeDef],
        "pathPrefix": NotRequired[str],
        "PaginationConfig": NotRequired[PaginatorConfigTypeDef],
    },
)
ListArtifactsRequestRequestTypeDef = TypedDict(
    "ListArtifactsRequestRequestTypeDef",
    {
        "requestContext": RequestContextTypeDef,
        "artifactFilter": NotRequired[ArtifactFilterTypeDef],
        "nextToken": NotRequired[str],
        "pathPrefix": NotRequired[str],
        "maxResults": NotRequired[int],
    },
)
ListConnectorsRequestRequestTypeDef = TypedDict(
    "ListConnectorsRequestRequestTypeDef",
    {
        "requestContext": RequestContextTypeDef,
        "maxResults": NotRequired[int],
        "nextToken": NotRequired[str],
    },
)
ListHitlTasksRequestListHitlTasksPaginateTypeDef = TypedDict(
    "ListHitlTasksRequestListHitlTasksPaginateTypeDef",
    {
        "requestContext": RequestContextTypeDef,
        "taskType": HitlTaskTypeType,
        "taskFilter": NotRequired[HitlTaskFilterTypeDef],
        "PaginationConfig": NotRequired[PaginatorConfigTypeDef],
    },
)
ListHitlTasksRequestRequestTypeDef = TypedDict(
    "ListHitlTasksRequestRequestTypeDef",
    {
        "requestContext": RequestContextTypeDef,
        "taskType": HitlTaskTypeType,
        "taskFilter": NotRequired[HitlTaskFilterTypeDef],
        "nextToken": NotRequired[str],
        "maxResults": NotRequired[int],
    },
)
ListJobPlanStepsRequestListJobPlanStepsPaginateTypeDef = TypedDict(
    "ListJobPlanStepsRequestListJobPlanStepsPaginateTypeDef",
    {
        "requestContext": RequestContextTypeDef,
        "parentStepId": NotRequired[str],
        "PaginationConfig": NotRequired[PaginatorConfigTypeDef],
    },
)
ListJobPlanStepsRequestRequestTypeDef = TypedDict(
    "ListJobPlanStepsRequestRequestTypeDef",
    {
        "requestContext": RequestContextTypeDef,
        "parentStepId": NotRequired[str],
        "maxResults": NotRequired[int],
        "nextToken": NotRequired[str],
    },
)
PublishMeteringEventRequestRequestTypeDef = TypedDict(
    "PublishMeteringEventRequestRequestTypeDef",
    {
        "requestContext": RequestContextTypeDef,
        "entity": EntityTypeDef,
        "resourceType": ResourceTypeType,
        "resourceId": str,
        "startTime": TimestampTypeDef,
        "amount": NotRequired[MeteredAmountTypeDef],
        "idempotencyToken": NotRequired[str],
        "attributes": NotRequired[Sequence[MeteringAttributeTypeDef]],
    },
)
PutAgreementRequestRequestTypeDef = TypedDict(
    "PutAgreementRequestRequestTypeDef",
    {
        "requestContext": RequestContextTypeDef,
        "agreementId": str,
        "agreementStatus": UmrAgreementStatusType,
        "agreementType": NotRequired[UmrIncentiveTypeType],
        "executedTimestamp": NotRequired[TimestampTypeDef],
        "amendmentVersion": NotRequired[int],
        "agreementUrl": NotRequired[str],
        "signedBy": NotRequired[str],
        "awsSignatory": NotRequired[str],
        "idempotencyToken": NotRequired[str],
    },
)
PutEligibilityRequestRequestTypeDef = TypedDict(
    "PutEligibilityRequestRequestTypeDef",
    {
        "requestContext": RequestContextTypeDef,
        "outcome": UmrEligibilityOutcomeType,
        "assessmentDate": TimestampTypeDef,
        "assessmentScore": NotRequired[int],
        "riskLevel": NotRequired[UmrRiskLevelType],
        "qualificationCriteria": NotRequired[Mapping[str, bool]],
        "idempotencyToken": NotRequired[str],
    },
)
PutJobPlanRequestRequestTypeDef = TypedDict(
    "PutJobPlanRequestRequestTypeDef",
    {
        "requestContext": RequestContextTypeDef,
        "plan": JobPlanTreeTypeDef,
        "mode": PutJobPlanModeTypeDef,
        "idempotencyToken": NotRequired[str],
    },
)
PutMigrationPlanRequestRequestTypeDef = TypedDict(
    "PutMigrationPlanRequestRequestTypeDef",
    {
        "requestContext": RequestContextTypeDef,
        "incentiveType": UmrIncentiveTypeType,
        "startDate": TimestampTypeDef,
        "endDate": TimestampTypeDef,
        "creditCap": float,
        "creditPercentage": NotRequired[float],
        "linkedAccountDisbursement": NotRequired[bool],
        "baselineSpend": NotRequired[Mapping[str, float]],
        "programFlags": NotRequired[Mapping[str, bool]],
        "partnerSpmsId": NotRequired[str],
        "idempotencyToken": NotRequired[str],
    },
)
RefreshAuthTokenRequestRequestTypeDef = TypedDict(
    "RefreshAuthTokenRequestRequestTypeDef",
    {
        "requestContext": RequestContextTypeDef,
        "sessionDuration": int,
    },
)
RegisterKnowledgeBaseDocumentRequestRequestTypeDef = TypedDict(
    "RegisterKnowledgeBaseDocumentRequestRequestTypeDef",
    {
        "requestContext": RequestContextTypeDef,
        "artifactId": str,
        "knowledgeBaseConfigType": Literal["TEXT_TITAN_CONFIG"],
        "indexingMetadata": NotRequired[Mapping[str, str]],
    },
)
RestoreAgentRequestRequestTypeDef = TypedDict(
    "RestoreAgentRequestRequestTypeDef",
    {
        "requestContext": RequestContextTypeDef,
        "agentId": str,
        "agentInstanceId": str,
        "agentType": AgentTypeType,
        "agentVersion": NotRequired[str],
        "idempotencyToken": NotRequired[str],
    },
)
RollbackMeteringEventRequestRequestTypeDef = TypedDict(
    "RollbackMeteringEventRequestRequestTypeDef",
    {
        "requestContext": RequestContextTypeDef,
        "entity": EntityTypeDef,
        "resourceType": ResourceTypeType,
        "resourceId": str,
        "amendTime": TimestampTypeDef,
    },
)
SendMessageRequestRequestTypeDef = TypedDict(
    "SendMessageRequestRequestTypeDef",
    {
        "requestContext": RequestContextTypeDef,
        "agentInstanceId": str,
        "params": NotRequired[Mapping[str, Any]],
    },
)
StartHitlTaskRequestRequestTypeDef = TypedDict(
    "StartHitlTaskRequestRequestTypeDef",
    {
        "requestContext": RequestContextTypeDef,
        "hitlTaskId": str,
        "firstInChain": NotRequired[bool],
        "idempotencyToken": NotRequired[str],
    },
)
StopAgentRequestRequestTypeDef = TypedDict(
    "StopAgentRequestRequestTypeDef",
    {
        "requestContext": RequestContextTypeDef,
        "agentInstanceId": str,
        "idempotencyToken": NotRequired[str],
    },
)
UpdateAgentInstanceRequestRequestTypeDef = TypedDict(
    "UpdateAgentInstanceRequestRequestTypeDef",
    {
        "requestContext": RequestContextTypeDef,
        "agentInstanceId": str,
        "agentInstanceStatus": UpdateAgentInstanceStatusType,
        "agentInstanceStatusReason": NotRequired[str],
        "agentOutput": NotRequired[AgentOutputPayloadTypeDef],
    },
)
UpdateJobPlanStepRequestRequestTypeDef = TypedDict(
    "UpdateJobPlanStepRequestRequestTypeDef",
    {
        "requestContext": RequestContextTypeDef,
        "planStep": PlanStepUpdateTypeDef,
        "idempotencyToken": NotRequired[str],
    },
)
UpdateJobStatusRequestRequestTypeDef = TypedDict(
    "UpdateJobStatusRequestRequestTypeDef",
    {
        "requestContext": RequestContextTypeDef,
        "status": NotRequired[JobStatusType],
        "statusInfo": NotRequired[StatusInfoTypeDef],
        "idempotencyToken": NotRequired[str],
        "notificationArtifactId": NotRequired[str],
    },
)
UpdateUMRStatusRequestRequestTypeDef = TypedDict(
    "UpdateUMRStatusRequestRequestTypeDef",
    {
        "requestContext": RequestContextTypeDef,
        "status": UmrStatusType,
        "idempotencyToken": NotRequired[str],
    },
)
GetJobResponseTypeDef = TypedDict(
    "GetJobResponseTypeDef",
    {
        "job": JobInfoTypeDef,
        "ResponseMetadata": ResponseMetadataTypeDef,
    },
)
GetUsageResponseTypeDef = TypedDict(
    "GetUsageResponseTypeDef",
    {
        "usageResults": List[MeteringUsageTypeDef],
        "ResponseMetadata": ResponseMetadataTypeDef,
    },
)
RetrieveFromKnowledgeBaseRequestRequestTypeDef = TypedDict(
    "RetrieveFromKnowledgeBaseRequestRequestTypeDef",
    {
        "requestContext": RequestContextTypeDef,
        "retrievalQuery": RetrievalQueryTypeDef,
        "retrievalScope": RetrievalScopeType,
        "retrievalConfiguration": NotRequired[RetrievalConfigurationTypeDef],
        "nextToken": NotRequired[str],
    },
)
RetrievalResultTypeDef = TypedDict(
    "RetrievalResultTypeDef",
    {
        "content": RetrievalResultContentTypeDef,
        "location": NotRequired[RetrievalResultLocationTypeDef],
        "score": NotRequired[float],
        "metadata": NotRequired[Dict[str, Dict[str, Any]]],
    },
)
GetUMRResponseTypeDef = TypedDict(
    "GetUMRResponseTypeDef",
    {
        "customerAccountId": str,
        "projectName": str,
        "status": UmrStatusType,
        "version": int,
        "plan": UmrMigrationPlanTypeDef,
        "eligibility": UmrEligibilityTypeDef,
        "agreements": List[UmrAgreementTypeDef],
        "partners": List[UmrPartnerDetailsTypeDef],
        "ResponseMetadata": ResponseMetadataTypeDef,
    },
)
WorklogFilterTypeDef = TypedDict(
    "WorklogFilterTypeDef",
    {
        "stepIdFilter": NotRequired[StepIdFilterTypeDef],
        "timeFilter": NotRequired[TimeFilterTypeDef],
    },
)
PutPartnerDetailsRequestRequestTypeDef = TypedDict(
    "PutPartnerDetailsRequestRequestTypeDef",
    {
        "requestContext": RequestContextTypeDef,
        "partnerAccountId": str,
        "partnerName": str,
        "partnerType": NotRequired[UmrPartnerTypeType],
        "migrationPhase": NotRequired[UmrMigrationPhaseType],
        "prmId": NotRequired[str],
        "workspaceId": NotRequired[str],
        "resources": NotRequired[Sequence[UmrResourceUnionTypeDef]],
        "idempotencyToken": NotRequired[str],
    },
)
VectorIngestionConfigurationTypeDef = TypedDict(
    "VectorIngestionConfigurationTypeDef",
    {
        "chunkingConfiguration": NotRequired[ChunkingConfigurationTypeDef],
    },
)
GetKnowledgeBaseIngestionResponseTypeDef = TypedDict(
    "GetKnowledgeBaseIngestionResponseTypeDef",
    {
        "ingestion": IngestionTypeDef,
        "ResponseMetadata": ResponseMetadataTypeDef,
    },
)
RetrieveFromKnowledgeBaseResponseTypeDef = TypedDict(
    "RetrieveFromKnowledgeBaseResponseTypeDef",
    {
        "retrievalResults": List[RetrievalResultTypeDef],
        "nextToken": str,
        "ResponseMetadata": ResponseMetadataTypeDef,
    },
)
ListWorklogsRequestRequestTypeDef = TypedDict(
    "ListWorklogsRequestRequestTypeDef",
    {
        "requestContext": RequestContextTypeDef,
        "worklogFilter": NotRequired[WorklogFilterTypeDef],
        "nextToken": NotRequired[str],
    },
)
IngestionConfigurationTypeDef = TypedDict(
    "IngestionConfigurationTypeDef",
    {
        "vectorIngestionConfiguration": NotRequired[VectorIngestionConfigurationTypeDef],
    },
)
StartKnowledgeBaseIngestionRequestRequestTypeDef = TypedDict(
    "StartKnowledgeBaseIngestionRequestRequestTypeDef",
    {
        "requestContext": RequestContextTypeDef,
        "knowledgeBaseConfigType": Literal["TEXT_TITAN_CONFIG"],
        "ingestionScopeMetadata": IngestionScopeMetadataTypeDef,
        "ingestionConfiguration": NotRequired[IngestionConfigurationTypeDef],
    },
)
