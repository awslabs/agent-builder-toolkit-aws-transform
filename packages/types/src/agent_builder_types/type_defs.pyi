"""
Type annotations for AWS Transform Agentic service type definitions.

[Open documentation](https://vemel.github.io/boto3_stubs_docs/agent_builder_types/type_defs.html)

Usage::

    ```python
    from agent_builder_types.type_defs import AccountConnectionTypeDef

    data: AccountConnectionTypeDef = {...}
    ```
"""

import sys
from datetime import datetime
from typing import Any, Dict, List, Union

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
    OwnerTypeType,
    PlanStepStatusType,
    PutJobPlanStatusType,
    ResourceTypeType,
    RetrievalResultLocationTypeType,
    RetrievalScopeType,
    SeverityType,
    UpdateAgentInstanceStatusType,
    VersionStatusType,
    VisibilityType,
)

if sys.version_info >= (3, 8):
    from typing import Literal
else:
    from typing_extensions import Literal
if sys.version_info >= (3, 8):
    from typing import TypedDict
else:
    from typing_extensions import TypedDict

__all__ = (
    "AccountConnectionTypeDef",
    "AcknowledgeDeletionRequestRequestTypeDef",
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
    "ArtifactFilterTypeDef",
    "ArtifactPlanStepFilterTypeDef",
    "ArtifactReferenceTypeDef",
    "ArtifactTypeDef",
    "ArtifactTypeTypeDef",
    "ArtifactWorkspaceFilterTypeDef",
    "AwsAccountConnectionTypeDef",
    "AwsTemporaryCredentialsTypeDef",
    "ChunkingConfigurationTypeDef",
    "CloseHitlTaskRequestRequestTypeDef",
    "CloseHitlTaskResponseTypeDef",
    "CompleteArtifactUploadRequestRequestTypeDef",
    "CompleteArtifactUploadResponseTypeDef",
    "ConnectorSummaryDataTypeDef",
    "ContentDigestTypeDef",
    "CopyArtifactRequestRequestTypeDef",
    "CopyArtifactResponseTypeDef",
    "CreateArtifactDownloadUrlRequestRequestTypeDef",
    "CreateArtifactDownloadUrlResponseTypeDef",
    "CreateArtifactUploadUrlRequestRequestTypeDef",
    "CreateArtifactUploadUrlResponseTypeDef",
    "CreateHitlTaskRequestRequestTypeDef",
    "CreateHitlTaskResponseTypeDef",
    "CreateSkillDownloadUrlRequestRequestTypeDef",
    "CreateSkillDownloadUrlResponseTypeDef",
    "CreateWorklogRequestRequestTypeDef",
    "DeleteJobPlanStepRequestRequestTypeDef",
    "DeregisterKnowledgeBaseDocumentRequestRequestTypeDef",
    "EntityTypeDef",
    "FileMetadataTypeDef",
    "FilterAttributeTypeDef",
    "FixedSizeChunkingConfigurationTypeDef",
    "GetAgentInstanceRequestRequestTypeDef",
    "GetAgentInstanceResponseTypeDef",
    "GetAgentVersionRequestRequestTypeDef",
    "GetAgentVersionResponseTypeDef",
    "GetArtifactMetadataRequestRequestTypeDef",
    "GetArtifactMetadataResponseTypeDef",
    "GetConnectorRequestRequestTypeDef",
    "GetConnectorResponseTypeDef",
    "GetHitlTaskRequestRequestTypeDef",
    "GetHitlTaskResponseTypeDef",
    "GetJobRequestRequestTypeDef",
    "GetJobResponseTypeDef",
    "GetKnowledgeBaseIngestionRequestRequestTypeDef",
    "GetKnowledgeBaseIngestionResponseTypeDef",
    "GetTaskRequestRequestTypeDef",
    "GetTaskResponseTypeDef",
    "GetTemporaryCredentialsForConnectorRequestRequestTypeDef",
    "GetTemporaryCredentialsForConnectorResponseTypeDef",
    "GetTemporaryCredentialsForRoleRequestRequestTypeDef",
    "GetTemporaryCredentialsForRoleResponseTypeDef",
    "GetUsageRequestRequestTypeDef",
    "GetUsageResponseTypeDef",
    "HierarchicalChunkingConfigurationTypeDef",
    "HierarchicalChunkingLevelConfigurationTypeDef",
    "HitlTaskArtifactTypeDef",
    "HitlTaskFilterTypeDef",
    "HitlTaskTypeDef",
    "IngestionConfigurationTypeDef",
    "IngestionScopeMetadataTypeDef",
    "IngestionTypeDef",
    "InvokeAgentRequestRequestTypeDef",
    "InvokeAgentResponseTypeDef",
    "IsS3ObjectPresentTypeDef",
    "JobInfoTypeDef",
    "JobMetadataTypeDef",
    "JobPlanStepNodeTypeDef",
    "JobPlanStepTypeDef",
    "JobPlanTreeTypeDef",
    "LimitDefinitionTypeDef",
    "ListAgentFilterTypeDef",
    "ListAgentInstancesRequestRequestTypeDef",
    "ListAgentInstancesResponseTypeDef",
    "ListAgentsFilterTypeDef",
    "ListAgentsRequestRequestTypeDef",
    "ListAgentsResponseTypeDef",
    "ListArtifactsRequestRequestTypeDef",
    "ListArtifactsResponseTypeDef",
    "ListConnectorsRequestRequestTypeDef",
    "ListConnectorsResponseTypeDef",
    "ListHitlTasksRequestRequestTypeDef",
    "ListHitlTasksResponseTypeDef",
    "ListJobPlanStepsRequestRequestTypeDef",
    "ListJobPlanStepsResponseTypeDef",
    "ListWorklogsRequestRequestTypeDef",
    "ListWorklogsResponseTypeDef",
    "MetadataContextTypeDef",
    "MeteredAmountTypeDef",
    "MeteringAttributeTypeDef",
    "MeteringUsageTypeDef",
    "PaginatorConfigTypeDef",
    "PlanStepMappingTypeDef",
    "PlanStepUpdateTypeDef",
    "PreProdTestOperationRequestRequestTypeDef",
    "PublishMeteringEventRequestRequestTypeDef",
    "PutJobPlanModeTypeDef",
    "PutJobPlanRequestRequestTypeDef",
    "PutJobPlanResponseTypeDef",
    "RefreshAuthTokenRequestRequestTypeDef",
    "RefreshAuthTokenResponseTypeDef",
    "RegisterKnowledgeBaseDocumentRequestRequestTypeDef",
    "RequestContextTypeDef",
    "ResponseMetadataTypeDef",
    "RetrievalConfigurationTypeDef",
    "RetrievalFilterTypeDef",
    "RetrievalQueryTypeDef",
    "RetrievalResultContentTypeDef",
    "RetrievalResultLocationTypeDef",
    "RetrievalResultS3LocationTypeDef",
    "RetrievalResultTypeDef",
    "RetrievalResultWebLocationTypeDef",
    "RetrieveFromKnowledgeBaseRequestRequestTypeDef",
    "RetrieveFromKnowledgeBaseResponseTypeDef",
    "RollbackMeteringEventRequestRequestTypeDef",
    "SemanticChunkingConfigurationTypeDef",
    "SendMessageRequestRequestTypeDef",
    "SendMessageResponseTypeDef",
    "StartHitlTaskRequestRequestTypeDef",
    "StartHitlTaskResponseTypeDef",
    "StartJobRequestRequestTypeDef",
    "StartJobResponseTypeDef",
    "StartKnowledgeBaseIngestionRequestRequestTypeDef",
    "StartKnowledgeBaseIngestionResponseTypeDef",
    "StatusDetailsTypeDef",
    "StatusInfoTypeDef",
    "StepIdFilterTypeDef",
    "StopAgentRequestRequestTypeDef",
    "TemporaryCredentialsTypeDef",
    "TestOperationRequestRequestTypeDef",
    "TimeFilterTypeDef",
    "UpdateAgentInstanceRequestRequestTypeDef",
    "UpdateJobPlanStepRequestRequestTypeDef",
    "UpdateJobStatusRequestRequestTypeDef",
    "VectorIngestionConfigurationTypeDef",
    "VectorSearchConfigurationTypeDef",
    "WorklogFilterTypeDef",
    "WorklogTypeDef",
)

AccountConnectionTypeDef = TypedDict(
    "AccountConnectionTypeDef",
    {
        "awsAccountConnection": "AwsAccountConnectionTypeDef",
    },
    total=False,
)

AcknowledgeDeletionRequestRequestTypeDef = TypedDict(
    "AcknowledgeDeletionRequestRequestTypeDef",
    {
        "requestContext": "RequestContextTypeDef",
        "deletionAcknowledgementToken": str,
    },
)

AgentConfigurationTypeDef = TypedDict(
    "AgentConfigurationTypeDef",
    {
        "shortDescription": str,
        "agentCard": Dict[str, Any],
    },
)

AgentInputPayloadTypeDef = TypedDict(
    "AgentInputPayloadTypeDef",
    {
        "serializedPayload": str,
    },
    total=False,
)

_RequiredAgentInstanceSummaryTypeDef = TypedDict(
    "_RequiredAgentInstanceSummaryTypeDef",
    {
        "agentInstanceId": str,
        "agentType": AgentTypeType,
        "agentInstanceStatus": AgentInstanceStatusType,
    },
)
_OptionalAgentInstanceSummaryTypeDef = TypedDict(
    "_OptionalAgentInstanceSummaryTypeDef",
    {
        "agentId": str,
        "agentVersion": str,
    },
    total=False,
)

class AgentInstanceSummaryTypeDef(
    _RequiredAgentInstanceSummaryTypeDef, _OptionalAgentInstanceSummaryTypeDef
):
    pass

AgentMetadataSummaryTypeDef = TypedDict(
    "AgentMetadataSummaryTypeDef",
    {
        "name": str,
        "type": AgentTypeType,
        "description": str,
        "accountAccess": AccessControlType,
        "visibility": AgentVisibilityType,
        "ownerType": OwnerTypeType,
        "customerConfigurationRequired": bool,
        "agentConfigurationAvailability": AgentConfigurationAvailabilityType,
        "customerConfiguredAgentDependencies": List[str],
    },
    total=False,
)

_RequiredAgentMetadataTypeDef = TypedDict(
    "_RequiredAgentMetadataTypeDef",
    {
        "type": AgentTypeType,
        "description": str,
        "ownerName": str,
        "ownerAccountId": str,
        "ownerContactInfo": str,
        "ownerType": OwnerTypeType,
        "customerConfigurationRequired": bool,
    },
)
_OptionalAgentMetadataTypeDef = TypedDict(
    "_OptionalAgentMetadataTypeDef",
    {
        "customerConfiguredAgentDependencies": List[str],
    },
    total=False,
)

class AgentMetadataTypeDef(_RequiredAgentMetadataTypeDef, _OptionalAgentMetadataTypeDef):
    pass

AgentOutputPayloadTypeDef = TypedDict(
    "AgentOutputPayloadTypeDef",
    {
        "serializedPayload": str,
    },
    total=False,
)

AgentTypeFilterTypeDef = TypedDict(
    "AgentTypeFilterTypeDef",
    {
        "agentType": AgentTypeType,
    },
    total=False,
)

_RequiredAppendModeTypeDef = TypedDict(
    "_RequiredAppendModeTypeDef",
    {
        "parentStepId": str,
    },
)
_OptionalAppendModeTypeDef = TypedDict(
    "_OptionalAppendModeTypeDef",
    {
        "afterStepId": str,
    },
    total=False,
)

class AppendModeTypeDef(_RequiredAppendModeTypeDef, _OptionalAppendModeTypeDef):
    pass

_RequiredArtifactAgentFilterTypeDef = TypedDict(
    "_RequiredArtifactAgentFilterTypeDef",
    {
        "agentInstanceId": str,
    },
)
_OptionalArtifactAgentFilterTypeDef = TypedDict(
    "_OptionalArtifactAgentFilterTypeDef",
    {
        "category": CategoryTypeType,
    },
    total=False,
)

class ArtifactAgentFilterTypeDef(
    _RequiredArtifactAgentFilterTypeDef, _OptionalArtifactAgentFilterTypeDef
):
    pass

_RequiredArtifactCategoryFilterTypeDef = TypedDict(
    "_RequiredArtifactCategoryFilterTypeDef",
    {
        "category": CategoryTypeType,
    },
)
_OptionalArtifactCategoryFilterTypeDef = TypedDict(
    "_OptionalArtifactCategoryFilterTypeDef",
    {
        "artifactLabel": str,
    },
    total=False,
)

class ArtifactCategoryFilterTypeDef(
    _RequiredArtifactCategoryFilterTypeDef, _OptionalArtifactCategoryFilterTypeDef
):
    pass

ArtifactFilterTypeDef = TypedDict(
    "ArtifactFilterTypeDef",
    {
        "agentFilter": "ArtifactAgentFilterTypeDef",
        "categoryFilter": "ArtifactCategoryFilterTypeDef",
        "workspaceFilter": "ArtifactWorkspaceFilterTypeDef",
        "planStepFilter": "ArtifactPlanStepFilterTypeDef",
    },
    total=False,
)

ArtifactPlanStepFilterTypeDef = TypedDict(
    "ArtifactPlanStepFilterTypeDef",
    {
        "planStepId": str,
        "category": CategoryTypeType,
    },
)

ArtifactReferenceTypeDef = TypedDict(
    "ArtifactReferenceTypeDef",
    {
        "artifactType": "ArtifactTypeTypeDef",
        "artifactId": str,
    },
    total=False,
)

_RequiredArtifactTypeDef = TypedDict(
    "_RequiredArtifactTypeDef",
    {
        "artifactId": str,
        "artifactType": "ArtifactTypeTypeDef",
        "artifactCreatedTimestamp": datetime,
        "artifactExpiryTimestamp": datetime,
    },
)
_OptionalArtifactTypeDef = TypedDict(
    "_OptionalArtifactTypeDef",
    {
        "artifactLabel": str,
        "fileMetadata": "FileMetadataTypeDef",
        "sizeInBytes": int,
        "storedInAtxBucket": bool,
    },
    total=False,
)

class ArtifactTypeDef(_RequiredArtifactTypeDef, _OptionalArtifactTypeDef):
    pass

_RequiredArtifactTypeTypeDef = TypedDict(
    "_RequiredArtifactTypeTypeDef",
    {
        "categoryType": CategoryTypeType,
        "fileType": FileTypeType,
    },
)
_OptionalArtifactTypeTypeDef = TypedDict(
    "_OptionalArtifactTypeTypeDef",
    {
        "schemaType": str,
    },
    total=False,
)

class ArtifactTypeTypeDef(_RequiredArtifactTypeTypeDef, _OptionalArtifactTypeTypeDef):
    pass

_RequiredArtifactWorkspaceFilterTypeDef = TypedDict(
    "_RequiredArtifactWorkspaceFilterTypeDef",
    {
        "category": CategoryTypeType,
    },
)
_OptionalArtifactWorkspaceFilterTypeDef = TypedDict(
    "_OptionalArtifactWorkspaceFilterTypeDef",
    {
        "artifactLabel": str,
    },
    total=False,
)

class ArtifactWorkspaceFilterTypeDef(
    _RequiredArtifactWorkspaceFilterTypeDef, _OptionalArtifactWorkspaceFilterTypeDef
):
    pass

AwsAccountConnectionTypeDef = TypedDict(
    "AwsAccountConnectionTypeDef",
    {
        "status": AccountConnectionStatusType,
        "createdDate": datetime,
        "expirationDate": datetime,
        "accountId": str,
        "roleArn": str,
        "connectionToken": str,
    },
    total=False,
)

AwsTemporaryCredentialsTypeDef = TypedDict(
    "AwsTemporaryCredentialsTypeDef",
    {
        "accessKey": str,
        "secretKey": str,
        "accessToken": str,
        "expirationTime": datetime,
    },
    total=False,
)

_RequiredChunkingConfigurationTypeDef = TypedDict(
    "_RequiredChunkingConfigurationTypeDef",
    {
        "chunkingStrategy": ChunkingStrategyType,
    },
)
_OptionalChunkingConfigurationTypeDef = TypedDict(
    "_OptionalChunkingConfigurationTypeDef",
    {
        "fixedSizeChunkingConfiguration": "FixedSizeChunkingConfigurationTypeDef",
        "hierarchicalChunkingConfiguration": "HierarchicalChunkingConfigurationTypeDef",
        "semanticChunkingConfiguration": "SemanticChunkingConfigurationTypeDef",
    },
    total=False,
)

class ChunkingConfigurationTypeDef(
    _RequiredChunkingConfigurationTypeDef, _OptionalChunkingConfigurationTypeDef
):
    pass

_RequiredCloseHitlTaskRequestRequestTypeDef = TypedDict(
    "_RequiredCloseHitlTaskRequestRequestTypeDef",
    {
        "requestContext": "RequestContextTypeDef",
        "hitlTaskId": str,
    },
)
_OptionalCloseHitlTaskRequestRequestTypeDef = TypedDict(
    "_OptionalCloseHitlTaskRequestRequestTypeDef",
    {
        "closureType": ClosureTypeType,
        "idempotencyToken": str,
    },
    total=False,
)

class CloseHitlTaskRequestRequestTypeDef(
    _RequiredCloseHitlTaskRequestRequestTypeDef, _OptionalCloseHitlTaskRequestRequestTypeDef
):
    pass

CloseHitlTaskResponseTypeDef = TypedDict(
    "CloseHitlTaskResponseTypeDef",
    {
        "hitlTaskStatus": HitlTaskStatusType,
        "ResponseMetadata": "ResponseMetadataTypeDef",
    },
)

CompleteArtifactUploadRequestRequestTypeDef = TypedDict(
    "CompleteArtifactUploadRequestRequestTypeDef",
    {
        "requestContext": "RequestContextTypeDef",
        "artifactId": str,
    },
)

CompleteArtifactUploadResponseTypeDef = TypedDict(
    "CompleteArtifactUploadResponseTypeDef",
    {
        "artifact": "ArtifactTypeDef",
        "ResponseMetadata": "ResponseMetadataTypeDef",
    },
)

_RequiredConnectorSummaryDataTypeDef = TypedDict(
    "_RequiredConnectorSummaryDataTypeDef",
    {
        "connectorId": str,
    },
)
_OptionalConnectorSummaryDataTypeDef = TypedDict(
    "_OptionalConnectorSummaryDataTypeDef",
    {
        "connectorName": str,
        "description": str,
        "connectorType": str,
        "targetRegions": List[str],
    },
    total=False,
)

class ConnectorSummaryDataTypeDef(
    _RequiredConnectorSummaryDataTypeDef, _OptionalConnectorSummaryDataTypeDef
):
    pass

ContentDigestTypeDef = TypedDict(
    "ContentDigestTypeDef",
    {
        "sha256": str,
    },
    total=False,
)

_RequiredCopyArtifactRequestRequestTypeDef = TypedDict(
    "_RequiredCopyArtifactRequestRequestTypeDef",
    {
        "requestContext": "RequestContextTypeDef",
        "artifactId": str,
    },
)
_OptionalCopyArtifactRequestRequestTypeDef = TypedDict(
    "_OptionalCopyArtifactRequestRequestTypeDef",
    {
        "idempotencyToken": str,
    },
    total=False,
)

class CopyArtifactRequestRequestTypeDef(
    _RequiredCopyArtifactRequestRequestTypeDef, _OptionalCopyArtifactRequestRequestTypeDef
):
    pass

CopyArtifactResponseTypeDef = TypedDict(
    "CopyArtifactResponseTypeDef",
    {
        "copyStatus": CopyStatusType,
        "ResponseMetadata": "ResponseMetadataTypeDef",
    },
)

_RequiredCreateArtifactDownloadUrlRequestRequestTypeDef = TypedDict(
    "_RequiredCreateArtifactDownloadUrlRequestRequestTypeDef",
    {
        "requestContext": "RequestContextTypeDef",
        "artifactId": str,
    },
)
_OptionalCreateArtifactDownloadUrlRequestRequestTypeDef = TypedDict(
    "_OptionalCreateArtifactDownloadUrlRequestRequestTypeDef",
    {
        "visibility": VisibilityType,
    },
    total=False,
)

class CreateArtifactDownloadUrlRequestRequestTypeDef(
    _RequiredCreateArtifactDownloadUrlRequestRequestTypeDef,
    _OptionalCreateArtifactDownloadUrlRequestRequestTypeDef,
):
    pass

CreateArtifactDownloadUrlResponseTypeDef = TypedDict(
    "CreateArtifactDownloadUrlResponseTypeDef",
    {
        "s3preSignedUrl": str,
        "s3UrlExpiryTimestamp": datetime,
        "artifactType": "ArtifactTypeTypeDef",
        "artifactLabel": str,
        "requestHeaders": Dict[str, List[str]],
        "artifact": "ArtifactTypeDef",
        "ResponseMetadata": "ResponseMetadataTypeDef",
    },
)

_RequiredCreateArtifactUploadUrlRequestRequestTypeDef = TypedDict(
    "_RequiredCreateArtifactUploadUrlRequestRequestTypeDef",
    {
        "requestContext": "RequestContextTypeDef",
        "contentDigest": "ContentDigestTypeDef",
        "artifactReference": "ArtifactReferenceTypeDef",
    },
)
_OptionalCreateArtifactUploadUrlRequestRequestTypeDef = TypedDict(
    "_OptionalCreateArtifactUploadUrlRequestRequestTypeDef",
    {
        "label": str,
        "planStepId": str,
        "visibility": VisibilityType,
        "metadata": "MetadataContextTypeDef",
        "fileMetadata": "FileMetadataTypeDef",
    },
    total=False,
)

class CreateArtifactUploadUrlRequestRequestTypeDef(
    _RequiredCreateArtifactUploadUrlRequestRequestTypeDef,
    _OptionalCreateArtifactUploadUrlRequestRequestTypeDef,
):
    pass

CreateArtifactUploadUrlResponseTypeDef = TypedDict(
    "CreateArtifactUploadUrlResponseTypeDef",
    {
        "artifactId": str,
        "s3preSignedUrl": str,
        "s3UrlExpiryTimestamp": datetime,
        "requestHeaders": Dict[str, List[str]],
        "ResponseMetadata": "ResponseMetadataTypeDef",
    },
)

_RequiredCreateHitlTaskRequestRequestTypeDef = TypedDict(
    "_RequiredCreateHitlTaskRequestRequestTypeDef",
    {
        "requestContext": "RequestContextTypeDef",
        "uxComponentId": str,
        "description": str,
        "title": str,
    },
)
_OptionalCreateHitlTaskRequestRequestTypeDef = TypedDict(
    "_OptionalCreateHitlTaskRequestRequestTypeDef",
    {
        "severity": SeverityType,
        "hitlTaskType": HitlTaskTypeType,
        "stepId": str,
        "blockingType": BlockingTypeType,
        "hitlRequestArtifact": "HitlTaskArtifactTypeDef",
        "expiredAt": Union[datetime, str],
        "tag": str,
        "idempotencyToken": str,
        "category": CategoryType,
    },
    total=False,
)

class CreateHitlTaskRequestRequestTypeDef(
    _RequiredCreateHitlTaskRequestRequestTypeDef, _OptionalCreateHitlTaskRequestRequestTypeDef
):
    pass

CreateHitlTaskResponseTypeDef = TypedDict(
    "CreateHitlTaskResponseTypeDef",
    {
        "hitlTaskId": str,
        "ResponseMetadata": "ResponseMetadataTypeDef",
    },
)

_RequiredCreateSkillDownloadUrlRequestRequestTypeDef = TypedDict(
    "_RequiredCreateSkillDownloadUrlRequestRequestTypeDef",
    {
        "requestContext": "RequestContextTypeDef",
        "skillName": str,
    },
)
_OptionalCreateSkillDownloadUrlRequestRequestTypeDef = TypedDict(
    "_OptionalCreateSkillDownloadUrlRequestRequestTypeDef",
    {
        "idempotencyToken": str,
        "version": str,
    },
    total=False,
)

class CreateSkillDownloadUrlRequestRequestTypeDef(
    _RequiredCreateSkillDownloadUrlRequestRequestTypeDef,
    _OptionalCreateSkillDownloadUrlRequestRequestTypeDef,
):
    pass

CreateSkillDownloadUrlResponseTypeDef = TypedDict(
    "CreateSkillDownloadUrlResponseTypeDef",
    {
        "s3PreSignedUrl": str,
        "s3UrlExpiryTimestamp": int,
        "requestHeaders": Dict[str, List[str]],
        "version": str,
        "ResponseMetadata": "ResponseMetadataTypeDef",
    },
)

_RequiredCreateWorklogRequestRequestTypeDef = TypedDict(
    "_RequiredCreateWorklogRequestRequestTypeDef",
    {
        "requestContext": "RequestContextTypeDef",
        "worklog": "WorklogTypeDef",
    },
)
_OptionalCreateWorklogRequestRequestTypeDef = TypedDict(
    "_OptionalCreateWorklogRequestRequestTypeDef",
    {
        "idempotencyToken": str,
    },
    total=False,
)

class CreateWorklogRequestRequestTypeDef(
    _RequiredCreateWorklogRequestRequestTypeDef, _OptionalCreateWorklogRequestRequestTypeDef
):
    pass

_RequiredDeleteJobPlanStepRequestRequestTypeDef = TypedDict(
    "_RequiredDeleteJobPlanStepRequestRequestTypeDef",
    {
        "requestContext": "RequestContextTypeDef",
        "stepId": str,
    },
)
_OptionalDeleteJobPlanStepRequestRequestTypeDef = TypedDict(
    "_OptionalDeleteJobPlanStepRequestRequestTypeDef",
    {
        "idempotencyToken": str,
    },
    total=False,
)

class DeleteJobPlanStepRequestRequestTypeDef(
    _RequiredDeleteJobPlanStepRequestRequestTypeDef, _OptionalDeleteJobPlanStepRequestRequestTypeDef
):
    pass

DeregisterKnowledgeBaseDocumentRequestRequestTypeDef = TypedDict(
    "DeregisterKnowledgeBaseDocumentRequestRequestTypeDef",
    {
        "requestContext": "RequestContextTypeDef",
        "artifactId": str,
        "knowledgeBaseConfigType": Literal["TEXT_TITAN_CONFIG"],
    },
)

EntityTypeDef = TypedDict(
    "EntityTypeDef",
    {
        "accountIdEntity": Dict[str, Any],
    },
    total=False,
)

_RequiredFileMetadataTypeDef = TypedDict(
    "_RequiredFileMetadataTypeDef",
    {
        "path": str,
    },
)
_OptionalFileMetadataTypeDef = TypedDict(
    "_OptionalFileMetadataTypeDef",
    {
        "description": str,
    },
    total=False,
)

class FileMetadataTypeDef(_RequiredFileMetadataTypeDef, _OptionalFileMetadataTypeDef):
    pass

FilterAttributeTypeDef = TypedDict(
    "FilterAttributeTypeDef",
    {
        "key": str,
        "value": Dict[str, Any],
    },
)

FixedSizeChunkingConfigurationTypeDef = TypedDict(
    "FixedSizeChunkingConfigurationTypeDef",
    {
        "maxTokens": int,
        "overlapPercentage": int,
    },
)

GetAgentInstanceRequestRequestTypeDef = TypedDict(
    "GetAgentInstanceRequestRequestTypeDef",
    {
        "requestContext": "RequestContextTypeDef",
        "agentInstanceId": str,
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
        "agentInput": "AgentInputPayloadTypeDef",
        "agentOutput": "AgentOutputPayloadTypeDef",
        "ResponseMetadata": "ResponseMetadataTypeDef",
    },
)

_RequiredGetAgentVersionRequestRequestTypeDef = TypedDict(
    "_RequiredGetAgentVersionRequestRequestTypeDef",
    {
        "requestContext": "RequestContextTypeDef",
        "name": str,
    },
)
_OptionalGetAgentVersionRequestRequestTypeDef = TypedDict(
    "_OptionalGetAgentVersionRequestRequestTypeDef",
    {
        "version": str,
    },
    total=False,
)

class GetAgentVersionRequestRequestTypeDef(
    _RequiredGetAgentVersionRequestRequestTypeDef, _OptionalGetAgentVersionRequestRequestTypeDef
):
    pass

GetAgentVersionResponseTypeDef = TypedDict(
    "GetAgentVersionResponseTypeDef",
    {
        "version": str,
        "metadata": "AgentMetadataTypeDef",
        "visibility": AgentVisibilityType,
        "configuration": "AgentConfigurationTypeDef",
        "status": VersionStatusType,
        "statusMessage": str,
        "ResponseMetadata": "ResponseMetadataTypeDef",
    },
)

GetArtifactMetadataRequestRequestTypeDef = TypedDict(
    "GetArtifactMetadataRequestRequestTypeDef",
    {
        "requestContext": "RequestContextTypeDef",
        "artifactId": str,
    },
)

GetArtifactMetadataResponseTypeDef = TypedDict(
    "GetArtifactMetadataResponseTypeDef",
    {
        "artifact": "ArtifactTypeDef",
        "isS3ObjectPresent": "IsS3ObjectPresentTypeDef",
        "metadata": "MetadataContextTypeDef",
        "ResponseMetadata": "ResponseMetadataTypeDef",
    },
)

GetConnectorRequestRequestTypeDef = TypedDict(
    "GetConnectorRequestRequestTypeDef",
    {
        "requestContext": "RequestContextTypeDef",
        "connectorId": str,
    },
)

GetConnectorResponseTypeDef = TypedDict(
    "GetConnectorResponseTypeDef",
    {
        "connectorName": str,
        "description": str,
        "connectorType": str,
        "configuration": Dict[str, str],
        "accountConnection": "AccountConnectionTypeDef",
        "targetRegions": List[str],
        "ResponseMetadata": "ResponseMetadataTypeDef",
    },
)

GetHitlTaskRequestRequestTypeDef = TypedDict(
    "GetHitlTaskRequestRequestTypeDef",
    {
        "requestContext": "RequestContextTypeDef",
        "hitlTaskId": str,
    },
)

GetHitlTaskResponseTypeDef = TypedDict(
    "GetHitlTaskResponseTypeDef",
    {
        "hitlTask": "HitlTaskTypeDef",
        "ResponseMetadata": "ResponseMetadataTypeDef",
    },
)

_RequiredGetJobRequestRequestTypeDef = TypedDict(
    "_RequiredGetJobRequestRequestTypeDef",
    {
        "requestContext": "RequestContextTypeDef",
    },
)
_OptionalGetJobRequestRequestTypeDef = TypedDict(
    "_OptionalGetJobRequestRequestTypeDef",
    {
        "includeObjective": bool,
    },
    total=False,
)

class GetJobRequestRequestTypeDef(
    _RequiredGetJobRequestRequestTypeDef, _OptionalGetJobRequestRequestTypeDef
):
    pass

GetJobResponseTypeDef = TypedDict(
    "GetJobResponseTypeDef",
    {
        "job": "JobInfoTypeDef",
        "ResponseMetadata": "ResponseMetadataTypeDef",
    },
)

GetKnowledgeBaseIngestionRequestRequestTypeDef = TypedDict(
    "GetKnowledgeBaseIngestionRequestRequestTypeDef",
    {
        "requestContext": "RequestContextTypeDef",
        "ingestionId": str,
    },
)

GetKnowledgeBaseIngestionResponseTypeDef = TypedDict(
    "GetKnowledgeBaseIngestionResponseTypeDef",
    {
        "ingestion": "IngestionTypeDef",
        "ResponseMetadata": "ResponseMetadataTypeDef",
    },
)

_RequiredGetTaskRequestRequestTypeDef = TypedDict(
    "_RequiredGetTaskRequestRequestTypeDef",
    {
        "requestContext": "RequestContextTypeDef",
        "agentInstanceId": str,
    },
)
_OptionalGetTaskRequestRequestTypeDef = TypedDict(
    "_OptionalGetTaskRequestRequestTypeDef",
    {
        "params": Dict[str, Any],
    },
    total=False,
)

class GetTaskRequestRequestTypeDef(
    _RequiredGetTaskRequestRequestTypeDef, _OptionalGetTaskRequestRequestTypeDef
):
    pass

GetTaskResponseTypeDef = TypedDict(
    "GetTaskResponseTypeDef",
    {
        "result": Dict[str, Any],
        "error": Dict[str, Any],
        "ResponseMetadata": "ResponseMetadataTypeDef",
    },
)

_RequiredGetTemporaryCredentialsForConnectorRequestRequestTypeDef = TypedDict(
    "_RequiredGetTemporaryCredentialsForConnectorRequestRequestTypeDef",
    {
        "requestContext": "RequestContextTypeDef",
        "connectorId": str,
    },
)
_OptionalGetTemporaryCredentialsForConnectorRequestRequestTypeDef = TypedDict(
    "_OptionalGetTemporaryCredentialsForConnectorRequestRequestTypeDef",
    {
        "targetRegion": str,
    },
    total=False,
)

class GetTemporaryCredentialsForConnectorRequestRequestTypeDef(
    _RequiredGetTemporaryCredentialsForConnectorRequestRequestTypeDef,
    _OptionalGetTemporaryCredentialsForConnectorRequestRequestTypeDef,
):
    pass

GetTemporaryCredentialsForConnectorResponseTypeDef = TypedDict(
    "GetTemporaryCredentialsForConnectorResponseTypeDef",
    {
        "temporaryCredentials": "TemporaryCredentialsTypeDef",
        "connectorConfiguration": Dict[str, str],
        "targetRegion": str,
        "ResponseMetadata": "ResponseMetadataTypeDef",
    },
)

GetTemporaryCredentialsForRoleRequestRequestTypeDef = TypedDict(
    "GetTemporaryCredentialsForRoleRequestRequestTypeDef",
    {
        "requestContext": "RequestContextTypeDef",
        "hitlTaskId": str,
    },
)

GetTemporaryCredentialsForRoleResponseTypeDef = TypedDict(
    "GetTemporaryCredentialsForRoleResponseTypeDef",
    {
        "temporaryCredentials": "TemporaryCredentialsTypeDef",
        "roleArn": str,
        "ResponseMetadata": "ResponseMetadataTypeDef",
    },
)

GetUsageRequestRequestTypeDef = TypedDict(
    "GetUsageRequestRequestTypeDef",
    {
        "requestContext": "RequestContextTypeDef",
        "resourceTypes": List[ResourceTypeType],
    },
)

GetUsageResponseTypeDef = TypedDict(
    "GetUsageResponseTypeDef",
    {
        "usageResults": List["MeteringUsageTypeDef"],
        "ResponseMetadata": "ResponseMetadataTypeDef",
    },
)

HierarchicalChunkingConfigurationTypeDef = TypedDict(
    "HierarchicalChunkingConfigurationTypeDef",
    {
        "levelConfigurations": List["HierarchicalChunkingLevelConfigurationTypeDef"],
        "overlapTokens": int,
    },
)

HierarchicalChunkingLevelConfigurationTypeDef = TypedDict(
    "HierarchicalChunkingLevelConfigurationTypeDef",
    {
        "maxTokens": int,
    },
)

HitlTaskArtifactTypeDef = TypedDict(
    "HitlTaskArtifactTypeDef",
    {
        "artifactId": str,
    },
    total=False,
)

HitlTaskFilterTypeDef = TypedDict(
    "HitlTaskFilterTypeDef",
    {
        "taskStatus": HitlTaskStatusType,
        "agentInstanceId": str,
        "stepId": str,
        "tag": str,
        "blockingType": BlockingTypeType,
        "categories": List[CategoryType],
    },
    total=False,
)

_RequiredHitlTaskTypeDef = TypedDict(
    "_RequiredHitlTaskTypeDef",
    {
        "hitlTaskId": str,
        "hitlTaskStatus": HitlTaskStatusType,
        "uxComponentId": str,
        "blockingType": BlockingTypeType,
        "severity": SeverityType,
        "hitlTaskType": HitlTaskTypeType,
    },
)
_OptionalHitlTaskTypeDef = TypedDict(
    "_OptionalHitlTaskTypeDef",
    {
        "createdAt": datetime,
        "updatedAt": datetime,
        "completedAt": datetime,
        "tag": str,
        "stepId": str,
        "agentArtifact": "HitlTaskArtifactTypeDef",
        "humanArtifact": "HitlTaskArtifactTypeDef",
        "description": str,
        "action": ActionType,
        "category": CategoryType,
    },
    total=False,
)

class HitlTaskTypeDef(_RequiredHitlTaskTypeDef, _OptionalHitlTaskTypeDef):
    pass

IngestionConfigurationTypeDef = TypedDict(
    "IngestionConfigurationTypeDef",
    {
        "vectorIngestionConfiguration": "VectorIngestionConfigurationTypeDef",
    },
    total=False,
)

IngestionScopeMetadataTypeDef = TypedDict(
    "IngestionScopeMetadataTypeDef",
    {
        "jobScope": "JobMetadataTypeDef",
    },
    total=False,
)

_RequiredIngestionTypeDef = TypedDict(
    "_RequiredIngestionTypeDef",
    {
        "ingestionId": str,
        "status": IngestionStatusType,
        "ingestionScopeMetadata": "IngestionScopeMetadataTypeDef",
    },
)
_OptionalIngestionTypeDef = TypedDict(
    "_OptionalIngestionTypeDef",
    {
        "createdAt": datetime,
        "updatedAt": datetime,
        "failureReason": str,
    },
    total=False,
)

class IngestionTypeDef(_RequiredIngestionTypeDef, _OptionalIngestionTypeDef):
    pass

_RequiredInvokeAgentRequestRequestTypeDef = TypedDict(
    "_RequiredInvokeAgentRequestRequestTypeDef",
    {
        "requestContext": "RequestContextTypeDef",
        "agentId": str,
    },
)
_OptionalInvokeAgentRequestRequestTypeDef = TypedDict(
    "_OptionalInvokeAgentRequestRequestTypeDef",
    {
        "inputPayload": "AgentInputPayloadTypeDef",
        "idempotencyToken": str,
        "agentVersion": str,
        "agentInstanceId": str,
        "agentType": AgentTypeType,
    },
    total=False,
)

class InvokeAgentRequestRequestTypeDef(
    _RequiredInvokeAgentRequestRequestTypeDef, _OptionalInvokeAgentRequestRequestTypeDef
):
    pass

InvokeAgentResponseTypeDef = TypedDict(
    "InvokeAgentResponseTypeDef",
    {
        "agentInstanceId": str,
        "ResponseMetadata": "ResponseMetadataTypeDef",
    },
)

IsS3ObjectPresentTypeDef = TypedDict(
    "IsS3ObjectPresentTypeDef",
    {
        "publicBucket": bool,
        "privateBucket": bool,
    },
    total=False,
)

JobInfoTypeDef = TypedDict(
    "JobInfoTypeDef",
    {
        "jobId": str,
        "workspaceId": str,
        "statusDetails": "StatusDetailsTypeDef",
        "creationTime": datetime,
        "startExecutionTime": datetime,
        "endExecutionTime": datetime,
        "objective": str,
        "jobName": str,
        "intent": str,
        "runCountId": int,
        "latestPlanVersion": int,
        "clientSource": str,
        "clientAppId": str,
        "softDeleted": bool,
    },
    total=False,
)

JobMetadataTypeDef = TypedDict(
    "JobMetadataTypeDef",
    {
        "jobId": str,
        "workspaceId": str,
    },
)

_RequiredJobPlanStepNodeTypeDef = TypedDict(
    "_RequiredJobPlanStepNodeTypeDef",
    {
        "stepLabel": str,
        "stepName": str,
        "description": str,
    },
)
_OptionalJobPlanStepNodeTypeDef = TypedDict(
    "_OptionalJobPlanStepNodeTypeDef",
    {
        "subSteps": List[Dict[str, Any]],
    },
    total=False,
)

class JobPlanStepNodeTypeDef(_RequiredJobPlanStepNodeTypeDef, _OptionalJobPlanStepNodeTypeDef):
    pass

_RequiredJobPlanStepTypeDef = TypedDict(
    "_RequiredJobPlanStepTypeDef",
    {
        "stepId": str,
        "parentStepId": str,
        "stepLabel": str,
        "stepName": str,
        "description": str,
    },
)
_OptionalJobPlanStepTypeDef = TypedDict(
    "_OptionalJobPlanStepTypeDef",
    {
        "score": float,
        "startTime": datetime,
        "endTime": datetime,
        "status": PlanStepStatusType,
    },
    total=False,
)

class JobPlanStepTypeDef(_RequiredJobPlanStepTypeDef, _OptionalJobPlanStepTypeDef):
    pass

JobPlanTreeTypeDef = TypedDict(
    "JobPlanTreeTypeDef",
    {
        "nodes": List["JobPlanStepNodeTypeDef"],
    },
    total=False,
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
        "requesterAgentInstanceId": str,
    },
    total=False,
)

_RequiredListAgentInstancesRequestRequestTypeDef = TypedDict(
    "_RequiredListAgentInstancesRequestRequestTypeDef",
    {
        "requestContext": "RequestContextTypeDef",
    },
)
_OptionalListAgentInstancesRequestRequestTypeDef = TypedDict(
    "_OptionalListAgentInstancesRequestRequestTypeDef",
    {
        "nextToken": str,
        "agentFilter": "ListAgentFilterTypeDef",
        "maxResults": int,
    },
    total=False,
)

class ListAgentInstancesRequestRequestTypeDef(
    _RequiredListAgentInstancesRequestRequestTypeDef,
    _OptionalListAgentInstancesRequestRequestTypeDef,
):
    pass

ListAgentInstancesResponseTypeDef = TypedDict(
    "ListAgentInstancesResponseTypeDef",
    {
        "agentInstanceSummaries": List["AgentInstanceSummaryTypeDef"],
        "nextToken": str,
        "ResponseMetadata": "ResponseMetadataTypeDef",
    },
)

ListAgentsFilterTypeDef = TypedDict(
    "ListAgentsFilterTypeDef",
    {
        "agentTypeFilter": "AgentTypeFilterTypeDef",
    },
    total=False,
)

_RequiredListAgentsRequestRequestTypeDef = TypedDict(
    "_RequiredListAgentsRequestRequestTypeDef",
    {
        "requestContext": "RequestContextTypeDef",
    },
)
_OptionalListAgentsRequestRequestTypeDef = TypedDict(
    "_OptionalListAgentsRequestRequestTypeDef",
    {
        "agentFilter": "ListAgentsFilterTypeDef",
        "nextToken": str,
        "maxResults": int,
    },
    total=False,
)

class ListAgentsRequestRequestTypeDef(
    _RequiredListAgentsRequestRequestTypeDef, _OptionalListAgentsRequestRequestTypeDef
):
    pass

ListAgentsResponseTypeDef = TypedDict(
    "ListAgentsResponseTypeDef",
    {
        "items": List["AgentMetadataSummaryTypeDef"],
        "nextToken": str,
        "ResponseMetadata": "ResponseMetadataTypeDef",
    },
)

_RequiredListArtifactsRequestRequestTypeDef = TypedDict(
    "_RequiredListArtifactsRequestRequestTypeDef",
    {
        "requestContext": "RequestContextTypeDef",
    },
)
_OptionalListArtifactsRequestRequestTypeDef = TypedDict(
    "_OptionalListArtifactsRequestRequestTypeDef",
    {
        "artifactFilter": "ArtifactFilterTypeDef",
        "nextToken": str,
        "pathPrefix": str,
        "maxResults": int,
    },
    total=False,
)

class ListArtifactsRequestRequestTypeDef(
    _RequiredListArtifactsRequestRequestTypeDef, _OptionalListArtifactsRequestRequestTypeDef
):
    pass

ListArtifactsResponseTypeDef = TypedDict(
    "ListArtifactsResponseTypeDef",
    {
        "artifacts": List["ArtifactTypeDef"],
        "nextToken": str,
        "ResponseMetadata": "ResponseMetadataTypeDef",
    },
)

_RequiredListConnectorsRequestRequestTypeDef = TypedDict(
    "_RequiredListConnectorsRequestRequestTypeDef",
    {
        "requestContext": "RequestContextTypeDef",
    },
)
_OptionalListConnectorsRequestRequestTypeDef = TypedDict(
    "_OptionalListConnectorsRequestRequestTypeDef",
    {
        "maxResults": int,
        "nextToken": str,
    },
    total=False,
)

class ListConnectorsRequestRequestTypeDef(
    _RequiredListConnectorsRequestRequestTypeDef, _OptionalListConnectorsRequestRequestTypeDef
):
    pass

ListConnectorsResponseTypeDef = TypedDict(
    "ListConnectorsResponseTypeDef",
    {
        "connectorsList": List["ConnectorSummaryDataTypeDef"],
        "nextToken": str,
        "ResponseMetadata": "ResponseMetadataTypeDef",
    },
)

_RequiredListHitlTasksRequestRequestTypeDef = TypedDict(
    "_RequiredListHitlTasksRequestRequestTypeDef",
    {
        "requestContext": "RequestContextTypeDef",
        "taskType": HitlTaskTypeType,
    },
)
_OptionalListHitlTasksRequestRequestTypeDef = TypedDict(
    "_OptionalListHitlTasksRequestRequestTypeDef",
    {
        "taskFilter": "HitlTaskFilterTypeDef",
        "nextToken": str,
        "maxResults": int,
    },
    total=False,
)

class ListHitlTasksRequestRequestTypeDef(
    _RequiredListHitlTasksRequestRequestTypeDef, _OptionalListHitlTasksRequestRequestTypeDef
):
    pass

ListHitlTasksResponseTypeDef = TypedDict(
    "ListHitlTasksResponseTypeDef",
    {
        "hitlTasks": List["HitlTaskTypeDef"],
        "nextToken": str,
        "ResponseMetadata": "ResponseMetadataTypeDef",
    },
)

_RequiredListJobPlanStepsRequestRequestTypeDef = TypedDict(
    "_RequiredListJobPlanStepsRequestRequestTypeDef",
    {
        "requestContext": "RequestContextTypeDef",
    },
)
_OptionalListJobPlanStepsRequestRequestTypeDef = TypedDict(
    "_OptionalListJobPlanStepsRequestRequestTypeDef",
    {
        "parentStepId": str,
        "maxResults": int,
        "nextToken": str,
    },
    total=False,
)

class ListJobPlanStepsRequestRequestTypeDef(
    _RequiredListJobPlanStepsRequestRequestTypeDef, _OptionalListJobPlanStepsRequestRequestTypeDef
):
    pass

ListJobPlanStepsResponseTypeDef = TypedDict(
    "ListJobPlanStepsResponseTypeDef",
    {
        "steps": List["JobPlanStepTypeDef"],
        "nextToken": str,
        "ResponseMetadata": "ResponseMetadataTypeDef",
    },
)

_RequiredListWorklogsRequestRequestTypeDef = TypedDict(
    "_RequiredListWorklogsRequestRequestTypeDef",
    {
        "requestContext": "RequestContextTypeDef",
    },
)
_OptionalListWorklogsRequestRequestTypeDef = TypedDict(
    "_OptionalListWorklogsRequestRequestTypeDef",
    {
        "worklogFilter": "WorklogFilterTypeDef",
        "nextToken": str,
    },
    total=False,
)

class ListWorklogsRequestRequestTypeDef(
    _RequiredListWorklogsRequestRequestTypeDef, _OptionalListWorklogsRequestRequestTypeDef
):
    pass

ListWorklogsResponseTypeDef = TypedDict(
    "ListWorklogsResponseTypeDef",
    {
        "worklogs": List["WorklogTypeDef"],
        "nextToken": str,
        "ResponseMetadata": "ResponseMetadataTypeDef",
    },
)

MetadataContextTypeDef = TypedDict(
    "MetadataContextTypeDef",
    {
        "schemaVersion": str,
        "content": Dict[str, Any],
    },
    total=False,
)

MeteredAmountTypeDef = TypedDict(
    "MeteredAmountTypeDef",
    {
        "amount": int,
        "unit": Literal["COUNT"],
    },
    total=False,
)

MeteringAttributeTypeDef = TypedDict(
    "MeteringAttributeTypeDef",
    {
        "name": str,
        "value": str,
    },
)

MeteringUsageTypeDef = TypedDict(
    "MeteringUsageTypeDef",
    {
        "resourceType": ResourceTypeType,
        "amount": float,
        "unit": Literal["COUNT"],
        "limits": "LimitDefinitionTypeDef",
    },
)

PaginatorConfigTypeDef = TypedDict(
    "PaginatorConfigTypeDef",
    {
        "MaxItems": int,
        "PageSize": int,
        "StartingToken": str,
    },
    total=False,
)

PlanStepMappingTypeDef = TypedDict(
    "PlanStepMappingTypeDef",
    {
        "stepLabel": str,
        "stepId": str,
    },
)

_RequiredPlanStepUpdateTypeDef = TypedDict(
    "_RequiredPlanStepUpdateTypeDef",
    {
        "stepId": str,
    },
)
_OptionalPlanStepUpdateTypeDef = TypedDict(
    "_OptionalPlanStepUpdateTypeDef",
    {
        "startTime": Union[datetime, str],
        "endTime": Union[datetime, str],
        "status": PlanStepStatusType,
        "description": str,
    },
    total=False,
)

class PlanStepUpdateTypeDef(_RequiredPlanStepUpdateTypeDef, _OptionalPlanStepUpdateTypeDef):
    pass

PreProdTestOperationRequestRequestTypeDef = TypedDict(
    "PreProdTestOperationRequestRequestTypeDef",
    {
        "requestContext": "RequestContextTypeDef",
    },
)

_RequiredPublishMeteringEventRequestRequestTypeDef = TypedDict(
    "_RequiredPublishMeteringEventRequestRequestTypeDef",
    {
        "requestContext": "RequestContextTypeDef",
        "entity": "EntityTypeDef",
        "resourceType": ResourceTypeType,
        "resourceId": str,
        "startTime": Union[datetime, str],
    },
)
_OptionalPublishMeteringEventRequestRequestTypeDef = TypedDict(
    "_OptionalPublishMeteringEventRequestRequestTypeDef",
    {
        "amount": "MeteredAmountTypeDef",
        "idempotencyToken": str,
        "attributes": List["MeteringAttributeTypeDef"],
    },
    total=False,
)

class PublishMeteringEventRequestRequestTypeDef(
    _RequiredPublishMeteringEventRequestRequestTypeDef,
    _OptionalPublishMeteringEventRequestRequestTypeDef,
):
    pass

PutJobPlanModeTypeDef = TypedDict(
    "PutJobPlanModeTypeDef",
    {
        "override": Dict[str, Any],
        "append": "AppendModeTypeDef",
    },
    total=False,
)

_RequiredPutJobPlanRequestRequestTypeDef = TypedDict(
    "_RequiredPutJobPlanRequestRequestTypeDef",
    {
        "requestContext": "RequestContextTypeDef",
        "plan": "JobPlanTreeTypeDef",
        "mode": "PutJobPlanModeTypeDef",
    },
)
_OptionalPutJobPlanRequestRequestTypeDef = TypedDict(
    "_OptionalPutJobPlanRequestRequestTypeDef",
    {
        "idempotencyToken": str,
    },
    total=False,
)

class PutJobPlanRequestRequestTypeDef(
    _RequiredPutJobPlanRequestRequestTypeDef, _OptionalPutJobPlanRequestRequestTypeDef
):
    pass

PutJobPlanResponseTypeDef = TypedDict(
    "PutJobPlanResponseTypeDef",
    {
        "status": PutJobPlanStatusType,
        "mappings": List["PlanStepMappingTypeDef"],
        "ResponseMetadata": "ResponseMetadataTypeDef",
    },
)

RefreshAuthTokenRequestRequestTypeDef = TypedDict(
    "RefreshAuthTokenRequestRequestTypeDef",
    {
        "requestContext": "RequestContextTypeDef",
        "sessionDuration": int,
    },
)

RefreshAuthTokenResponseTypeDef = TypedDict(
    "RefreshAuthTokenResponseTypeDef",
    {
        "authorizationToken": str,
        "authorizationExpiration": datetime,
        "ResponseMetadata": "ResponseMetadataTypeDef",
    },
)

_RequiredRegisterKnowledgeBaseDocumentRequestRequestTypeDef = TypedDict(
    "_RequiredRegisterKnowledgeBaseDocumentRequestRequestTypeDef",
    {
        "requestContext": "RequestContextTypeDef",
        "artifactId": str,
        "knowledgeBaseConfigType": Literal["TEXT_TITAN_CONFIG"],
    },
)
_OptionalRegisterKnowledgeBaseDocumentRequestRequestTypeDef = TypedDict(
    "_OptionalRegisterKnowledgeBaseDocumentRequestRequestTypeDef",
    {
        "indexingMetadata": Dict[str, str],
    },
    total=False,
)

class RegisterKnowledgeBaseDocumentRequestRequestTypeDef(
    _RequiredRegisterKnowledgeBaseDocumentRequestRequestTypeDef,
    _OptionalRegisterKnowledgeBaseDocumentRequestRequestTypeDef,
):
    pass

RequestContextTypeDef = TypedDict(
    "RequestContextTypeDef",
    {
        "jobMetadata": "JobMetadataTypeDef",
        "agentInstanceId": str,
        "authorizationToken": str,
    },
)

ResponseMetadataTypeDef = TypedDict(
    "ResponseMetadataTypeDef",
    {
        "RequestId": str,
        "HostId": str,
        "HTTPStatusCode": int,
        "HTTPHeaders": Dict[str, Any],
        "RetryAttempts": int,
    },
)

RetrievalConfigurationTypeDef = TypedDict(
    "RetrievalConfigurationTypeDef",
    {
        "vectorSearchConfiguration": "VectorSearchConfigurationTypeDef",
    },
)

RetrievalFilterTypeDef = TypedDict(
    "RetrievalFilterTypeDef",
    {
        "equals": "FilterAttributeTypeDef",
        "notEquals": "FilterAttributeTypeDef",
        "greaterThan": "FilterAttributeTypeDef",
        "greaterThanOrEquals": "FilterAttributeTypeDef",
        "lessThan": "FilterAttributeTypeDef",
        "lessThanOrEquals": "FilterAttributeTypeDef",
        "in": "FilterAttributeTypeDef",
        "notIn": "FilterAttributeTypeDef",
        "startsWith": "FilterAttributeTypeDef",
        "listContains": "FilterAttributeTypeDef",
        "stringContains": "FilterAttributeTypeDef",
        "andAll": List[Dict[str, Any]],
        "orAll": List[Dict[str, Any]],
    },
    total=False,
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
        "text": str,
    },
    total=False,
)

_RequiredRetrievalResultLocationTypeDef = TypedDict(
    "_RequiredRetrievalResultLocationTypeDef",
    {
        "type": RetrievalResultLocationTypeType,
    },
)
_OptionalRetrievalResultLocationTypeDef = TypedDict(
    "_OptionalRetrievalResultLocationTypeDef",
    {
        "s3Location": "RetrievalResultS3LocationTypeDef",
        "webLocation": "RetrievalResultWebLocationTypeDef",
    },
    total=False,
)

class RetrievalResultLocationTypeDef(
    _RequiredRetrievalResultLocationTypeDef, _OptionalRetrievalResultLocationTypeDef
):
    pass

RetrievalResultS3LocationTypeDef = TypedDict(
    "RetrievalResultS3LocationTypeDef",
    {
        "uri": str,
    },
    total=False,
)

_RequiredRetrievalResultTypeDef = TypedDict(
    "_RequiredRetrievalResultTypeDef",
    {
        "content": "RetrievalResultContentTypeDef",
    },
)
_OptionalRetrievalResultTypeDef = TypedDict(
    "_OptionalRetrievalResultTypeDef",
    {
        "location": "RetrievalResultLocationTypeDef",
        "score": float,
        "metadata": Dict[str, Dict[str, Any]],
    },
    total=False,
)

class RetrievalResultTypeDef(_RequiredRetrievalResultTypeDef, _OptionalRetrievalResultTypeDef):
    pass

RetrievalResultWebLocationTypeDef = TypedDict(
    "RetrievalResultWebLocationTypeDef",
    {
        "url": str,
    },
    total=False,
)

_RequiredRetrieveFromKnowledgeBaseRequestRequestTypeDef = TypedDict(
    "_RequiredRetrieveFromKnowledgeBaseRequestRequestTypeDef",
    {
        "requestContext": "RequestContextTypeDef",
        "retrievalQuery": "RetrievalQueryTypeDef",
        "retrievalScope": RetrievalScopeType,
    },
)
_OptionalRetrieveFromKnowledgeBaseRequestRequestTypeDef = TypedDict(
    "_OptionalRetrieveFromKnowledgeBaseRequestRequestTypeDef",
    {
        "retrievalConfiguration": "RetrievalConfigurationTypeDef",
        "nextToken": str,
    },
    total=False,
)

class RetrieveFromKnowledgeBaseRequestRequestTypeDef(
    _RequiredRetrieveFromKnowledgeBaseRequestRequestTypeDef,
    _OptionalRetrieveFromKnowledgeBaseRequestRequestTypeDef,
):
    pass

RetrieveFromKnowledgeBaseResponseTypeDef = TypedDict(
    "RetrieveFromKnowledgeBaseResponseTypeDef",
    {
        "retrievalResults": List["RetrievalResultTypeDef"],
        "nextToken": str,
        "ResponseMetadata": "ResponseMetadataTypeDef",
    },
)

RollbackMeteringEventRequestRequestTypeDef = TypedDict(
    "RollbackMeteringEventRequestRequestTypeDef",
    {
        "requestContext": "RequestContextTypeDef",
        "entity": "EntityTypeDef",
        "resourceType": ResourceTypeType,
        "resourceId": str,
        "amendTime": Union[datetime, str],
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

_RequiredSendMessageRequestRequestTypeDef = TypedDict(
    "_RequiredSendMessageRequestRequestTypeDef",
    {
        "requestContext": "RequestContextTypeDef",
        "agentInstanceId": str,
    },
)
_OptionalSendMessageRequestRequestTypeDef = TypedDict(
    "_OptionalSendMessageRequestRequestTypeDef",
    {
        "params": Dict[str, Any],
    },
    total=False,
)

class SendMessageRequestRequestTypeDef(
    _RequiredSendMessageRequestRequestTypeDef, _OptionalSendMessageRequestRequestTypeDef
):
    pass

SendMessageResponseTypeDef = TypedDict(
    "SendMessageResponseTypeDef",
    {
        "result": Dict[str, Any],
        "error": Dict[str, Any],
        "ResponseMetadata": "ResponseMetadataTypeDef",
    },
)

_RequiredStartHitlTaskRequestRequestTypeDef = TypedDict(
    "_RequiredStartHitlTaskRequestRequestTypeDef",
    {
        "requestContext": "RequestContextTypeDef",
        "hitlTaskId": str,
    },
)
_OptionalStartHitlTaskRequestRequestTypeDef = TypedDict(
    "_OptionalStartHitlTaskRequestRequestTypeDef",
    {
        "firstInChain": bool,
        "idempotencyToken": str,
    },
    total=False,
)

class StartHitlTaskRequestRequestTypeDef(
    _RequiredStartHitlTaskRequestRequestTypeDef, _OptionalStartHitlTaskRequestRequestTypeDef
):
    pass

StartHitlTaskResponseTypeDef = TypedDict(
    "StartHitlTaskResponseTypeDef",
    {
        "hitlTaskStatus": HitlTaskStatusType,
        "ResponseMetadata": "ResponseMetadataTypeDef",
    },
)

_RequiredStartJobRequestRequestTypeDef = TypedDict(
    "_RequiredStartJobRequestRequestTypeDef",
    {
        "requestContext": "RequestContextTypeDef",
    },
)
_OptionalStartJobRequestRequestTypeDef = TypedDict(
    "_OptionalStartJobRequestRequestTypeDef",
    {
        "idempotencyToken": str,
    },
    total=False,
)

class StartJobRequestRequestTypeDef(
    _RequiredStartJobRequestRequestTypeDef, _OptionalStartJobRequestRequestTypeDef
):
    pass

StartJobResponseTypeDef = TypedDict(
    "StartJobResponseTypeDef",
    {
        "status": JobStatusType,
        "ResponseMetadata": "ResponseMetadataTypeDef",
    },
)

_RequiredStartKnowledgeBaseIngestionRequestRequestTypeDef = TypedDict(
    "_RequiredStartKnowledgeBaseIngestionRequestRequestTypeDef",
    {
        "requestContext": "RequestContextTypeDef",
        "knowledgeBaseConfigType": Literal["TEXT_TITAN_CONFIG"],
        "ingestionScopeMetadata": "IngestionScopeMetadataTypeDef",
    },
)
_OptionalStartKnowledgeBaseIngestionRequestRequestTypeDef = TypedDict(
    "_OptionalStartKnowledgeBaseIngestionRequestRequestTypeDef",
    {
        "ingestionConfiguration": "IngestionConfigurationTypeDef",
    },
    total=False,
)

class StartKnowledgeBaseIngestionRequestRequestTypeDef(
    _RequiredStartKnowledgeBaseIngestionRequestRequestTypeDef,
    _OptionalStartKnowledgeBaseIngestionRequestRequestTypeDef,
):
    pass

StartKnowledgeBaseIngestionResponseTypeDef = TypedDict(
    "StartKnowledgeBaseIngestionResponseTypeDef",
    {
        "ingestionId": str,
        "ResponseMetadata": "ResponseMetadataTypeDef",
    },
)

_RequiredStatusDetailsTypeDef = TypedDict(
    "_RequiredStatusDetailsTypeDef",
    {
        "status": JobStatusType,
    },
)
_OptionalStatusDetailsTypeDef = TypedDict(
    "_OptionalStatusDetailsTypeDef",
    {
        "failureReason": str,
    },
    total=False,
)

class StatusDetailsTypeDef(_RequiredStatusDetailsTypeDef, _OptionalStatusDetailsTypeDef):
    pass

_RequiredStatusInfoTypeDef = TypedDict(
    "_RequiredStatusInfoTypeDef",
    {
        "status": JobStatusType,
    },
)
_OptionalStatusInfoTypeDef = TypedDict(
    "_OptionalStatusInfoTypeDef",
    {
        "failureCategory": FailureCategoryType,
        "failureType": str,
    },
    total=False,
)

class StatusInfoTypeDef(_RequiredStatusInfoTypeDef, _OptionalStatusInfoTypeDef):
    pass

_RequiredStepIdFilterTypeDef = TypedDict(
    "_RequiredStepIdFilterTypeDef",
    {
        "stepId": str,
    },
)
_OptionalStepIdFilterTypeDef = TypedDict(
    "_OptionalStepIdFilterTypeDef",
    {
        "timeFilter": "TimeFilterTypeDef",
    },
    total=False,
)

class StepIdFilterTypeDef(_RequiredStepIdFilterTypeDef, _OptionalStepIdFilterTypeDef):
    pass

_RequiredStopAgentRequestRequestTypeDef = TypedDict(
    "_RequiredStopAgentRequestRequestTypeDef",
    {
        "requestContext": "RequestContextTypeDef",
        "agentInstanceId": str,
    },
)
_OptionalStopAgentRequestRequestTypeDef = TypedDict(
    "_OptionalStopAgentRequestRequestTypeDef",
    {
        "idempotencyToken": str,
    },
    total=False,
)

class StopAgentRequestRequestTypeDef(
    _RequiredStopAgentRequestRequestTypeDef, _OptionalStopAgentRequestRequestTypeDef
):
    pass

TemporaryCredentialsTypeDef = TypedDict(
    "TemporaryCredentialsTypeDef",
    {
        "awsTemporaryCredentials": "AwsTemporaryCredentialsTypeDef",
    },
    total=False,
)

TestOperationRequestRequestTypeDef = TypedDict(
    "TestOperationRequestRequestTypeDef",
    {
        "requestContext": "RequestContextTypeDef",
    },
)

TimeFilterTypeDef = TypedDict(
    "TimeFilterTypeDef",
    {
        "startTime": Union[datetime, str],
        "endTime": Union[datetime, str],
    },
    total=False,
)

_RequiredUpdateAgentInstanceRequestRequestTypeDef = TypedDict(
    "_RequiredUpdateAgentInstanceRequestRequestTypeDef",
    {
        "requestContext": "RequestContextTypeDef",
        "agentInstanceId": str,
        "agentInstanceStatus": UpdateAgentInstanceStatusType,
    },
)
_OptionalUpdateAgentInstanceRequestRequestTypeDef = TypedDict(
    "_OptionalUpdateAgentInstanceRequestRequestTypeDef",
    {
        "agentInstanceStatusReason": str,
        "agentOutput": "AgentOutputPayloadTypeDef",
    },
    total=False,
)

class UpdateAgentInstanceRequestRequestTypeDef(
    _RequiredUpdateAgentInstanceRequestRequestTypeDef,
    _OptionalUpdateAgentInstanceRequestRequestTypeDef,
):
    pass

_RequiredUpdateJobPlanStepRequestRequestTypeDef = TypedDict(
    "_RequiredUpdateJobPlanStepRequestRequestTypeDef",
    {
        "requestContext": "RequestContextTypeDef",
        "planStep": "PlanStepUpdateTypeDef",
    },
)
_OptionalUpdateJobPlanStepRequestRequestTypeDef = TypedDict(
    "_OptionalUpdateJobPlanStepRequestRequestTypeDef",
    {
        "idempotencyToken": str,
    },
    total=False,
)

class UpdateJobPlanStepRequestRequestTypeDef(
    _RequiredUpdateJobPlanStepRequestRequestTypeDef, _OptionalUpdateJobPlanStepRequestRequestTypeDef
):
    pass

_RequiredUpdateJobStatusRequestRequestTypeDef = TypedDict(
    "_RequiredUpdateJobStatusRequestRequestTypeDef",
    {
        "requestContext": "RequestContextTypeDef",
    },
)
_OptionalUpdateJobStatusRequestRequestTypeDef = TypedDict(
    "_OptionalUpdateJobStatusRequestRequestTypeDef",
    {
        "status": JobStatusType,
        "statusInfo": "StatusInfoTypeDef",
        "idempotencyToken": str,
        "notificationArtifactId": str,
    },
    total=False,
)

class UpdateJobStatusRequestRequestTypeDef(
    _RequiredUpdateJobStatusRequestRequestTypeDef, _OptionalUpdateJobStatusRequestRequestTypeDef
):
    pass

VectorIngestionConfigurationTypeDef = TypedDict(
    "VectorIngestionConfigurationTypeDef",
    {
        "chunkingConfiguration": "ChunkingConfigurationTypeDef",
    },
    total=False,
)

VectorSearchConfigurationTypeDef = TypedDict(
    "VectorSearchConfigurationTypeDef",
    {
        "numberOfResults": int,
        "filter": "RetrievalFilterTypeDef",
    },
    total=False,
)

WorklogFilterTypeDef = TypedDict(
    "WorklogFilterTypeDef",
    {
        "stepIdFilter": "StepIdFilterTypeDef",
        "timeFilter": "TimeFilterTypeDef",
    },
    total=False,
)

_RequiredWorklogTypeDef = TypedDict(
    "_RequiredWorklogTypeDef",
    {
        "timestamp": Union[datetime, str],
        "attributeMap": Dict[str, str],
    },
)
_OptionalWorklogTypeDef = TypedDict(
    "_OptionalWorklogTypeDef",
    {
        "description": str,
    },
    total=False,
)

class WorklogTypeDef(_RequiredWorklogTypeDef, _OptionalWorklogTypeDef):
    pass
