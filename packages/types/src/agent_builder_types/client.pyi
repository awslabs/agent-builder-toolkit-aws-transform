# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Type annotations for transformagenticservice service client.

[Open documentation](https://youtype.github.io/boto3_stubs_docs/agent_builder_types/client/)

Usage::

    ```python
    from boto3.session import Session
    from agent_builder_types.client import TransformAgenticServiceClient

    session = Session()
    client: TransformAgenticServiceClient = session.client("transformagenticservice")
    ```
"""

import sys
from typing import Any, Dict, Mapping, Sequence, Type, overload

from botocore.client import BaseClient, ClientMeta

from .literals import (
    AgentTypeType,
    BlockingTypeType,
    CategoryType,
    ClosureTypeType,
    HitlTaskTypeType,
    JobStatusType,
    ResourceTypeType,
    RetrievalScopeType,
    SeverityType,
    UmrAgreementStatusType,
    UmrEligibilityOutcomeType,
    UmrIncentiveTypeType,
    UmrMigrationPhaseType,
    UmrPartnerTypeType,
    UmrRiskLevelType,
    UmrStatusType,
    UpdateAgentInstanceStatusType,
    VisibilityType,
)
from .paginator import (
    ListAgentInstancesPaginator,
    ListArtifactsPaginator,
    ListHitlTasksPaginator,
    ListJobPlanStepsPaginator,
)
from .type_defs import (
    AgentInputPayloadTypeDef,
    AgentOutputPayloadTypeDef,
    ArtifactFilterTypeDef,
    ArtifactReferenceTypeDef,
    CloseHitlTaskResponseTypeDef,
    CompleteArtifactUploadResponseTypeDef,
    ContentDigestTypeDef,
    CopyArtifactResponseTypeDef,
    CreateArtifactDownloadUrlResponseTypeDef,
    CreateArtifactUploadUrlResponseTypeDef,
    CreateHitlTaskResponseTypeDef,
    CreateSkillDownloadUrlResponseTypeDef,
    EntityTypeDef,
    FileMetadataTypeDef,
    GetAgentInstanceResponseTypeDef,
    GetAgentVersionResponseTypeDef,
    GetArtifactMetadataResponseTypeDef,
    GetConnectorResponseTypeDef,
    GetHitlTaskResponseTypeDef,
    GetJobResponseTypeDef,
    GetKnowledgeBaseIngestionResponseTypeDef,
    GetTaskResponseTypeDef,
    GetTemporaryCredentialsForConnectorResponseTypeDef,
    GetTemporaryCredentialsForRoleResponseTypeDef,
    GetUMRResponseTypeDef,
    GetUsageResponseTypeDef,
    HitlTaskArtifactTypeDef,
    HitlTaskFilterTypeDef,
    IngestionConfigurationTypeDef,
    IngestionScopeMetadataTypeDef,
    InvokeAgentResponseTypeDef,
    JobPlanTreeTypeDef,
    ListAgentFilterTypeDef,
    ListAgentInstancesResponseTypeDef,
    ListAgentsFilterTypeDef,
    ListAgentsResponseTypeDef,
    ListArtifactsResponseTypeDef,
    ListConnectorsResponseTypeDef,
    ListHitlTasksResponseTypeDef,
    ListJobPlanStepsResponseTypeDef,
    ListWorklogsResponseTypeDef,
    MeteredAmountTypeDef,
    MeteringAttributeTypeDef,
    PlanStepUpdateTypeDef,
    PutAgreementResponseTypeDef,
    PutEligibilityResponseTypeDef,
    PutJobPlanModeTypeDef,
    PutJobPlanResponseTypeDef,
    PutMigrationPlanResponseTypeDef,
    PutPartnerDetailsResponseTypeDef,
    RefreshAuthTokenResponseTypeDef,
    RequestContextTypeDef,
    RetrievalConfigurationTypeDef,
    RetrievalQueryTypeDef,
    RetrieveFromKnowledgeBaseResponseTypeDef,
    SendMessageResponseTypeDef,
    StartHitlTaskResponseTypeDef,
    StartKnowledgeBaseIngestionResponseTypeDef,
    StatusInfoTypeDef,
    TimestampTypeDef,
    UmrResourceUnionTypeDef,
    UpdateUMRStatusResponseTypeDef,
    WorklogFilterTypeDef,
    WorklogUnionTypeDef,
)

if sys.version_info >= (3, 12):
    from typing import Literal
else:
    from typing_extensions import Literal

__all__ = ("TransformAgenticServiceClient",)

class BotocoreClientError(Exception):
    MSG_TEMPLATE: str

    def __init__(self, error_response: Mapping[str, Any], operation_name: str) -> None:
        self.response: Dict[str, Any]
        self.operation_name: str

class Exceptions:
    AccessDeniedException: Type[BotocoreClientError]
    AssumeRoleException: Type[BotocoreClientError]
    ClientError: Type[BotocoreClientError]
    ConflictException: Type[BotocoreClientError]
    CustomerConfigurationException: Type[BotocoreClientError]
    DependencyInternalServerException: Type[BotocoreClientError]
    FileAlreadyExistsException: Type[BotocoreClientError]
    InternalServerException: Type[BotocoreClientError]
    ResourceNotFoundException: Type[BotocoreClientError]
    ServiceQuotaExceededException: Type[BotocoreClientError]
    TerminalResourceException: Type[BotocoreClientError]
    ThrottlingException: Type[BotocoreClientError]
    ValidationException: Type[BotocoreClientError]

class TransformAgenticServiceClient(BaseClient):
    """
    [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/transformagenticservice.html#TransformAgenticService.Client)
    [Show boto3-stubs documentation](https://youtype.github.io/boto3_stubs_docs/agent_builder_types/client/)
    """

    meta: ClientMeta

    @property
    def exceptions(self) -> Exceptions:
        """
        TransformAgenticServiceClient exceptions.

        [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/transformagenticservice.html#TransformAgenticService.Client.exceptions)
        [Show boto3-stubs documentation](https://youtype.github.io/boto3_stubs_docs/agent_builder_types/client/#exceptions)
        """

    def acknowledge_deletion(
        self, *, requestContext: RequestContextTypeDef, deletionAcknowledgementToken: str
    ) -> Dict[str, Any]:
        """
        API used by agents to acknowledge they have completed the data cleanup for the
        corresponding job See also: [AWS API
        Documentation](https://docs.aws.amazon.com/goto/WebAPI/transformagents-2018-05-10/AcknowledgeDeletion).

        [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/transformagenticservice.html#TransformAgenticService.Client.acknowledge_deletion)
        [Show boto3-stubs documentation](https://youtype.github.io/boto3_stubs_docs/agent_builder_types/client/#acknowledge_deletion)
        """

    def can_paginate(self, operation_name: str) -> bool:
        """
        Check if an operation can be paginated.

        [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/transformagenticservice.html#TransformAgenticService.Client.can_paginate)
        [Show boto3-stubs documentation](https://youtype.github.io/boto3_stubs_docs/agent_builder_types/client/#can_paginate)
        """

    def close(self) -> None:
        """
        Closes underlying endpoint connections.

        [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/transformagenticservice.html#TransformAgenticService.Client.close)
        [Show boto3-stubs documentation](https://youtype.github.io/boto3_stubs_docs/agent_builder_types/client/#close)
        """

    def close_hitl_task(
        self,
        *,
        requestContext: RequestContextTypeDef,
        hitlTaskId: str,
        closureType: ClosureTypeType = ...,
        idempotencyToken: str = ...,
    ) -> CloseHitlTaskResponseTypeDef:
        """
        See also: [AWS API
        Documentation](https://docs.aws.amazon.com/goto/WebAPI/transformagents-2018-05-10/CloseHitlTask).

        [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/transformagenticservice.html#TransformAgenticService.Client.close_hitl_task)
        [Show boto3-stubs documentation](https://youtype.github.io/boto3_stubs_docs/agent_builder_types/client/#close_hitl_task)
        """

    def complete_artifact_upload(
        self, *, requestContext: RequestContextTypeDef, artifactId: str
    ) -> CompleteArtifactUploadResponseTypeDef:
        """
        API used by agents to let ATX Foundation know that upload is complete.

        [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/transformagenticservice.html#TransformAgenticService.Client.complete_artifact_upload)
        [Show boto3-stubs documentation](https://youtype.github.io/boto3_stubs_docs/agent_builder_types/client/#complete_artifact_upload)
        """

    def copy_artifact(
        self, *, requestContext: RequestContextTypeDef, artifactId: str, idempotencyToken: str = ...
    ) -> CopyArtifactResponseTypeDef:
        """
        API used by agents to copy artifacts from artifact store bucket to public
        bucket See also: [AWS API
        Documentation](https://docs.aws.amazon.com/goto/WebAPI/transformagents-2018-05-10/CopyArtifact).

        [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/transformagenticservice.html#TransformAgenticService.Client.copy_artifact)
        [Show boto3-stubs documentation](https://youtype.github.io/boto3_stubs_docs/agent_builder_types/client/#copy_artifact)
        """

    def create_artifact_download_url(
        self,
        *,
        requestContext: RequestContextTypeDef,
        artifactId: str,
        visibility: VisibilityType = ...,
    ) -> CreateArtifactDownloadUrlResponseTypeDef:
        """
        API used by agents to generate an S3 presigned URL for downloading an artifact.

        [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/transformagenticservice.html#TransformAgenticService.Client.create_artifact_download_url)
        [Show boto3-stubs documentation](https://youtype.github.io/boto3_stubs_docs/agent_builder_types/client/#create_artifact_download_url)
        """

    def create_artifact_upload_url(
        self,
        *,
        requestContext: RequestContextTypeDef,
        contentDigest: ContentDigestTypeDef,
        artifactReference: ArtifactReferenceTypeDef,
        label: str = ...,
        planStepId: str = ...,
        visibility: VisibilityType = ...,
        fileMetadata: FileMetadataTypeDef = ...,
    ) -> CreateArtifactUploadUrlResponseTypeDef:
        """
        API used by agents to generate an S3 presigned URL for uploading an artifact.

        [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/transformagenticservice.html#TransformAgenticService.Client.create_artifact_upload_url)
        [Show boto3-stubs documentation](https://youtype.github.io/boto3_stubs_docs/agent_builder_types/client/#create_artifact_upload_url)
        """

    def create_hitl_task(
        self,
        *,
        requestContext: RequestContextTypeDef,
        uxComponentId: str,
        description: str,
        title: str,
        severity: SeverityType = ...,
        hitlTaskType: HitlTaskTypeType = ...,
        stepId: str = ...,
        blockingType: BlockingTypeType = ...,
        hitlRequestArtifact: HitlTaskArtifactTypeDef = ...,
        expiredAt: TimestampTypeDef = ...,
        tag: str = ...,
        idempotencyToken: str = ...,
        category: CategoryType = ...,
    ) -> CreateHitlTaskResponseTypeDef:
        """
        API used by agents to trigger a Human-In-The-Loop request.

        [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/transformagenticservice.html#TransformAgenticService.Client.create_hitl_task)
        [Show boto3-stubs documentation](https://youtype.github.io/boto3_stubs_docs/agent_builder_types/client/#create_hitl_task)
        """

    def create_skill_download_url(
        self,
        *,
        requestContext: RequestContextTypeDef,
        skillName: str,
        idempotencyToken: str = ...,
        version: str = ...,
    ) -> CreateSkillDownloadUrlResponseTypeDef:
        """
        See also: [AWS API
        Documentation](https://docs.aws.amazon.com/goto/WebAPI/transformagents-2018-05-10/CreateSkillDownloadUrl).

        [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/transformagenticservice.html#TransformAgenticService.Client.create_skill_download_url)
        [Show boto3-stubs documentation](https://youtype.github.io/boto3_stubs_docs/agent_builder_types/client/#create_skill_download_url)
        """

    def create_worklog(
        self,
        *,
        requestContext: RequestContextTypeDef,
        worklog: WorklogUnionTypeDef,
        idempotencyToken: str = ...,
    ) -> Dict[str, Any]:
        """
        API to allow ingestion of agent/ HITL/ job level worklogs See also: [AWS API
        Documentation](https://docs.aws.amazon.com/goto/WebAPI/transformagents-2018-05-10/CreateWorklog).

        [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/transformagenticservice.html#TransformAgenticService.Client.create_worklog)
        [Show boto3-stubs documentation](https://youtype.github.io/boto3_stubs_docs/agent_builder_types/client/#create_worklog)
        """

    def delete_job_plan_step(
        self, *, requestContext: RequestContextTypeDef, stepId: str, idempotencyToken: str = ...
    ) -> Dict[str, Any]:
        """
        API used by agents to delete an existing step of the job plan.

        [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/transformagenticservice.html#TransformAgenticService.Client.delete_job_plan_step)
        [Show boto3-stubs documentation](https://youtype.github.io/boto3_stubs_docs/agent_builder_types/client/#delete_job_plan_step)
        """

    def deregister_knowledge_base_document(
        self,
        *,
        requestContext: RequestContextTypeDef,
        artifactId: str,
        knowledgeBaseConfigType: Literal["TEXT_TITAN_CONFIG"],
    ) -> Dict[str, Any]:
        """
        API used by agents to deregister a document from knowledge base See also: [AWS
        API
        Documentation](https://docs.aws.amazon.com/goto/WebAPI/transformagents-2018-05-10/DeregisterKnowledgeBaseDocument).

        [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/transformagenticservice.html#TransformAgenticService.Client.deregister_knowledge_base_document)
        [Show boto3-stubs documentation](https://youtype.github.io/boto3_stubs_docs/agent_builder_types/client/#deregister_knowledge_base_document)
        """

    def generate_presigned_url(
        self,
        ClientMethod: str,
        Params: Mapping[str, Any] = ...,
        ExpiresIn: int = 3600,
        HttpMethod: str = ...,
    ) -> str:
        """
        Generate a presigned url given a client, its method, and arguments.

        [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/transformagenticservice.html#TransformAgenticService.Client.generate_presigned_url)
        [Show boto3-stubs documentation](https://youtype.github.io/boto3_stubs_docs/agent_builder_types/client/#generate_presigned_url)
        """

    def get_agent_instance(
        self, *, requestContext: RequestContextTypeDef, agentInstanceId: str
    ) -> GetAgentInstanceResponseTypeDef:
        """
        API used to Get details about a specific agent's invocation See also: [AWS API
        Documentation](https://docs.aws.amazon.com/goto/WebAPI/transformagents-2018-05-10/GetAgentInstance).

        [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/transformagenticservice.html#TransformAgenticService.Client.get_agent_instance)
        [Show boto3-stubs documentation](https://youtype.github.io/boto3_stubs_docs/agent_builder_types/client/#get_agent_instance)
        """

    def get_agent_version(
        self, *, requestContext: RequestContextTypeDef, name: str, version: str = ...
    ) -> GetAgentVersionResponseTypeDef:
        """
        See also: [AWS API
        Documentation](https://docs.aws.amazon.com/goto/WebAPI/transformagents-2018-05-10/GetAgentVersion).

        [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/transformagenticservice.html#TransformAgenticService.Client.get_agent_version)
        [Show boto3-stubs documentation](https://youtype.github.io/boto3_stubs_docs/agent_builder_types/client/#get_agent_version)
        """

    def get_artifact_metadata(
        self, *, requestContext: RequestContextTypeDef, artifactId: str
    ) -> GetArtifactMetadataResponseTypeDef:
        """
        This API is used to retrieve metadata about an artifact See also: [AWS API
        Documentation](https://docs.aws.amazon.com/goto/WebAPI/transformagents-2018-05-10/GetArtifactMetadata).

        [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/transformagenticservice.html#TransformAgenticService.Client.get_artifact_metadata)
        [Show boto3-stubs documentation](https://youtype.github.io/boto3_stubs_docs/agent_builder_types/client/#get_artifact_metadata)
        """

    def get_connector(
        self, *, requestContext: RequestContextTypeDef, connectorId: str
    ) -> GetConnectorResponseTypeDef:
        """
        API used by agents to get resource level details of connector by connectorId
        See also: [AWS API
        Documentation](https://docs.aws.amazon.com/goto/WebAPI/transformagents-2018-05-10/GetConnector).

        [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/transformagenticservice.html#TransformAgenticService.Client.get_connector)
        [Show boto3-stubs documentation](https://youtype.github.io/boto3_stubs_docs/agent_builder_types/client/#get_connector)
        """

    def get_hitl_task(
        self, *, requestContext: RequestContextTypeDef, hitlTaskId: str
    ) -> GetHitlTaskResponseTypeDef:
        """
        API used by agents to Get the status for a Human-In-The-Loop request.

        [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/transformagenticservice.html#TransformAgenticService.Client.get_hitl_task)
        [Show boto3-stubs documentation](https://youtype.github.io/boto3_stubs_docs/agent_builder_types/client/#get_hitl_task)
        """

    def get_job(
        self, *, requestContext: RequestContextTypeDef, includeObjective: bool = ...
    ) -> GetJobResponseTypeDef:
        """
        API used by agents to Get details about a Transformation Job See also: [AWS API
        Documentation](https://docs.aws.amazon.com/goto/WebAPI/transformagents-2018-05-10/GetJob).

        [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/transformagenticservice.html#TransformAgenticService.Client.get_job)
        [Show boto3-stubs documentation](https://youtype.github.io/boto3_stubs_docs/agent_builder_types/client/#get_job)
        """

    def get_knowledge_base_ingestion(
        self, *, requestContext: RequestContextTypeDef, ingestionId: str
    ) -> GetKnowledgeBaseIngestionResponseTypeDef:
        """
        API used by agents to get ingestion details See also: [AWS API
        Documentation](https://docs.aws.amazon.com/goto/WebAPI/transformagents-2018-05-10/GetKnowledgeBaseIngestion).

        [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/transformagenticservice.html#TransformAgenticService.Client.get_knowledge_base_ingestion)
        [Show boto3-stubs documentation](https://youtype.github.io/boto3_stubs_docs/agent_builder_types/client/#get_knowledge_base_ingestion)
        """

    def get_task(
        self,
        *,
        requestContext: RequestContextTypeDef,
        agentInstanceId: str,
        params: Mapping[str, Any] = ...,
    ) -> GetTaskResponseTypeDef:
        """
        This API is modeled similarly to the corresponding A2A protocol method
        (https://a2a-protocol.org/latest/specification/#73-tasksget).

        [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/transformagenticservice.html#TransformAgenticService.Client.get_task)
        [Show boto3-stubs documentation](https://youtype.github.io/boto3_stubs_docs/agent_builder_types/client/#get_task)
        """

    def get_temporary_credentials_for_connector(
        self, *, requestContext: RequestContextTypeDef, connectorId: str, targetRegion: str = ...
    ) -> GetTemporaryCredentialsForConnectorResponseTypeDef:
        """
        API used by agents to get temporary credentials and details related to data
        source See also: [AWS API
        Documentation](https://docs.aws.amazon.com/goto/WebAPI/transformagents-2018-05-10/GetTemporaryCredentialsForConnector).

        [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/transformagenticservice.html#TransformAgenticService.Client.get_temporary_credentials_for_connector)
        [Show boto3-stubs documentation](https://youtype.github.io/boto3_stubs_docs/agent_builder_types/client/#get_temporary_credentials_for_connector)
        """

    def get_temporary_credentials_for_role(
        self, *, requestContext: RequestContextTypeDef, hitlTaskId: str
    ) -> GetTemporaryCredentialsForRoleResponseTypeDef:
        """
        API used by agents to get temporary credentials for a given IAM role See also:
        [AWS API
        Documentation](https://docs.aws.amazon.com/goto/WebAPI/transformagents-2018-05-10/GetTemporaryCredentialsForRole).

        [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/transformagenticservice.html#TransformAgenticService.Client.get_temporary_credentials_for_role)
        [Show boto3-stubs documentation](https://youtype.github.io/boto3_stubs_docs/agent_builder_types/client/#get_temporary_credentials_for_role)
        """

    def get_umr(self, *, requestContext: RequestContextTypeDef) -> GetUMRResponseTypeDef:
        """
        Retrieves the full UMR record for an engagement.

        [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/transformagenticservice.html#TransformAgenticService.Client.get_umr)
        [Show boto3-stubs documentation](https://youtype.github.io/boto3_stubs_docs/agent_builder_types/client/#get_umr)
        """

    def get_usage(
        self, *, requestContext: RequestContextTypeDef, resourceTypes: Sequence[ResourceTypeType]
    ) -> GetUsageResponseTypeDef:
        """
        API used to get a customers usage of a resource type See also: [AWS API
        Documentation](https://docs.aws.amazon.com/goto/WebAPI/transformagents-2018-05-10/GetUsage).

        [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/transformagenticservice.html#TransformAgenticService.Client.get_usage)
        [Show boto3-stubs documentation](https://youtype.github.io/boto3_stubs_docs/agent_builder_types/client/#get_usage)
        """

    def invoke_agent(
        self,
        *,
        requestContext: RequestContextTypeDef,
        agentId: str,
        inputPayload: AgentInputPayloadTypeDef = ...,
        idempotencyToken: str = ...,
        agentVersion: str = ...,
        agentInstanceId: str = ...,
        agentType: AgentTypeType = ...,
    ) -> InvokeAgentResponseTypeDef:
        """
        API used to Invoke Agents See also: [AWS API
        Documentation](https://docs.aws.amazon.com/goto/WebAPI/transformagents-2018-05-10/InvokeAgent).

        [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/transformagenticservice.html#TransformAgenticService.Client.invoke_agent)
        [Show boto3-stubs documentation](https://youtype.github.io/boto3_stubs_docs/agent_builder_types/client/#invoke_agent)
        """

    def list_agent_instances(
        self,
        *,
        requestContext: RequestContextTypeDef,
        nextToken: str = ...,
        agentFilter: ListAgentFilterTypeDef = ...,
        maxResults: int = ...,
    ) -> ListAgentInstancesResponseTypeDef:
        """
        API used to List all agent invocations for a specific transformation job See
        also: [AWS API
        Documentation](https://docs.aws.amazon.com/goto/WebAPI/transformagents-2018-05-10/ListAgentInstances).

        [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/transformagenticservice.html#TransformAgenticService.Client.list_agent_instances)
        [Show boto3-stubs documentation](https://youtype.github.io/boto3_stubs_docs/agent_builder_types/client/#list_agent_instances)
        """

    def list_agents(
        self,
        *,
        requestContext: RequestContextTypeDef,
        agentFilter: ListAgentsFilterTypeDef = ...,
        nextToken: str = ...,
        maxResults: int = ...,
    ) -> ListAgentsResponseTypeDef:
        """
        See also: [AWS API
        Documentation](https://docs.aws.amazon.com/goto/WebAPI/transformagents-2018-05-10/ListAgents).

        [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/transformagenticservice.html#TransformAgenticService.Client.list_agents)
        [Show boto3-stubs documentation](https://youtype.github.io/boto3_stubs_docs/agent_builder_types/client/#list_agents)
        """

    def list_artifacts(
        self,
        *,
        requestContext: RequestContextTypeDef,
        artifactFilter: ArtifactFilterTypeDef = ...,
        nextToken: str = ...,
        pathPrefix: str = ...,
        maxResults: int = ...,
    ) -> ListArtifactsResponseTypeDef:
        """
        API used by agents to list artifacts for a transformation job See also: [AWS
        API
        Documentation](https://docs.aws.amazon.com/goto/WebAPI/transformagents-2018-05-10/ListArtifacts).

        [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/transformagenticservice.html#TransformAgenticService.Client.list_artifacts)
        [Show boto3-stubs documentation](https://youtype.github.io/boto3_stubs_docs/agent_builder_types/client/#list_artifacts)
        """

    def list_connectors(
        self, *, requestContext: RequestContextTypeDef, maxResults: int = ..., nextToken: str = ...
    ) -> ListConnectorsResponseTypeDef:
        """
        API used by agents to get list of all the connectors available based on the
        agent Type See also: [AWS API
        Documentation](https://docs.aws.amazon.com/goto/WebAPI/transformagents-2018-05-10/ListConnectors).

        [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/transformagenticservice.html#TransformAgenticService.Client.list_connectors)
        [Show boto3-stubs documentation](https://youtype.github.io/boto3_stubs_docs/agent_builder_types/client/#list_connectors)
        """

    def list_hitl_tasks(
        self,
        *,
        requestContext: RequestContextTypeDef,
        taskType: HitlTaskTypeType,
        taskFilter: HitlTaskFilterTypeDef = ...,
        nextToken: str = ...,
        maxResults: int = ...,
    ) -> ListHitlTasksResponseTypeDef:
        """
        See also: [AWS API
        Documentation](https://docs.aws.amazon.com/goto/WebAPI/transformagents-2018-05-10/ListHitlTasks).

        [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/transformagenticservice.html#TransformAgenticService.Client.list_hitl_tasks)
        [Show boto3-stubs documentation](https://youtype.github.io/boto3_stubs_docs/agent_builder_types/client/#list_hitl_tasks)
        """

    def list_job_plan_steps(
        self,
        *,
        requestContext: RequestContextTypeDef,
        parentStepId: str = ...,
        maxResults: int = ...,
        nextToken: str = ...,
    ) -> ListJobPlanStepsResponseTypeDef:
        """
        API used by agents to list the plan steps for a job See also: [AWS API
        Documentation](https://docs.aws.amazon.com/goto/WebAPI/transformagents-2018-05-10/ListJobPlanSteps).

        [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/transformagenticservice.html#TransformAgenticService.Client.list_job_plan_steps)
        [Show boto3-stubs documentation](https://youtype.github.io/boto3_stubs_docs/agent_builder_types/client/#list_job_plan_steps)
        """

    def list_worklogs(
        self,
        *,
        requestContext: RequestContextTypeDef,
        worklogFilter: WorklogFilterTypeDef = ...,
        nextToken: str = ...,
    ) -> ListWorklogsResponseTypeDef:
        """
        API to allow retrieval of worklogs for a specific job.

        [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/transformagenticservice.html#TransformAgenticService.Client.list_worklogs)
        [Show boto3-stubs documentation](https://youtype.github.io/boto3_stubs_docs/agent_builder_types/client/#list_worklogs)
        """

    def publish_metering_event(
        self,
        *,
        requestContext: RequestContextTypeDef,
        entity: EntityTypeDef,
        resourceType: ResourceTypeType,
        resourceId: str,
        startTime: TimestampTypeDef,
        amount: MeteredAmountTypeDef = ...,
        idempotencyToken: str = ...,
        attributes: Sequence[MeteringAttributeTypeDef] = ...,
    ) -> Dict[str, Any]:
        """
        See also: [AWS API
        Documentation](https://docs.aws.amazon.com/goto/WebAPI/transformagents-2018-05-10/PublishMeteringEvent).

        [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/transformagenticservice.html#TransformAgenticService.Client.publish_metering_event)
        [Show boto3-stubs documentation](https://youtype.github.io/boto3_stubs_docs/agent_builder_types/client/#publish_metering_event)
        """

    def put_agreement(
        self,
        *,
        requestContext: RequestContextTypeDef,
        agreementId: str,
        agreementStatus: UmrAgreementStatusType,
        agreementType: UmrIncentiveTypeType = ...,
        executedTimestamp: TimestampTypeDef = ...,
        amendmentVersion: int = ...,
        agreementUrl: str = ...,
        signedBy: str = ...,
        awsSignatory: str = ...,
        idempotencyToken: str = ...,
    ) -> PutAgreementResponseTypeDef:
        """
        Creates or updates agreement details for a UMR engagement.

        [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/transformagenticservice.html#TransformAgenticService.Client.put_agreement)
        [Show boto3-stubs documentation](https://youtype.github.io/boto3_stubs_docs/agent_builder_types/client/#put_agreement)
        """

    def put_eligibility(
        self,
        *,
        requestContext: RequestContextTypeDef,
        outcome: UmrEligibilityOutcomeType,
        assessmentDate: TimestampTypeDef,
        assessmentScore: int = ...,
        riskLevel: UmrRiskLevelType = ...,
        qualificationCriteria: Mapping[str, bool] = ...,
        idempotencyToken: str = ...,
    ) -> PutEligibilityResponseTypeDef:
        """
        Creates or updates eligibility assessment for a UMR engagement.

        [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/transformagenticservice.html#TransformAgenticService.Client.put_eligibility)
        [Show boto3-stubs documentation](https://youtype.github.io/boto3_stubs_docs/agent_builder_types/client/#put_eligibility)
        """

    def put_job_plan(
        self,
        *,
        requestContext: RequestContextTypeDef,
        plan: JobPlanTreeTypeDef,
        mode: PutJobPlanModeTypeDef,
        idempotencyToken: str = ...,
    ) -> PutJobPlanResponseTypeDef:
        """
        API used by agents to put a job plan See also: [AWS API
        Documentation](https://docs.aws.amazon.com/goto/WebAPI/transformagents-2018-05-10/PutJobPlan).

        [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/transformagenticservice.html#TransformAgenticService.Client.put_job_plan)
        [Show boto3-stubs documentation](https://youtype.github.io/boto3_stubs_docs/agent_builder_types/client/#put_job_plan)
        """

    def put_migration_plan(
        self,
        *,
        requestContext: RequestContextTypeDef,
        incentiveType: UmrIncentiveTypeType,
        startDate: TimestampTypeDef,
        endDate: TimestampTypeDef,
        creditCap: float,
        creditPercentage: float = ...,
        linkedAccountDisbursement: bool = ...,
        baselineSpend: Mapping[str, float] = ...,
        programFlags: Mapping[str, bool] = ...,
        partnerSpmsId: str = ...,
        idempotencyToken: str = ...,
    ) -> PutMigrationPlanResponseTypeDef:
        """
        Creates or updates a migration plan for a UMR engagement.

        [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/transformagenticservice.html#TransformAgenticService.Client.put_migration_plan)
        [Show boto3-stubs documentation](https://youtype.github.io/boto3_stubs_docs/agent_builder_types/client/#put_migration_plan)
        """

    def put_partner_details(
        self,
        *,
        requestContext: RequestContextTypeDef,
        partnerAccountId: str,
        partnerName: str,
        partnerType: UmrPartnerTypeType = ...,
        migrationPhase: UmrMigrationPhaseType = ...,
        prmId: str = ...,
        workspaceId: str = ...,
        resources: Sequence[UmrResourceUnionTypeDef] = ...,
        idempotencyToken: str = ...,
    ) -> PutPartnerDetailsResponseTypeDef:
        """
        Creates or updates partner details for a UMR engagement.

        [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/transformagenticservice.html#TransformAgenticService.Client.put_partner_details)
        [Show boto3-stubs documentation](https://youtype.github.io/boto3_stubs_docs/agent_builder_types/client/#put_partner_details)
        """

    def refresh_auth_token(
        self, *, requestContext: RequestContextTypeDef, sessionDuration: int
    ) -> RefreshAuthTokenResponseTypeDef:
        """
        API used to generate a new agent authorization token with a later expiration
        time See also: [AWS API
        Documentation](https://docs.aws.amazon.com/goto/WebAPI/transformagents-2018-05-10/RefreshAuthToken).

        [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/transformagenticservice.html#TransformAgenticService.Client.refresh_auth_token)
        [Show boto3-stubs documentation](https://youtype.github.io/boto3_stubs_docs/agent_builder_types/client/#refresh_auth_token)
        """

    def register_knowledge_base_document(
        self,
        *,
        requestContext: RequestContextTypeDef,
        artifactId: str,
        knowledgeBaseConfigType: Literal["TEXT_TITAN_CONFIG"],
        indexingMetadata: Mapping[str, str] = ...,
    ) -> Dict[str, Any]:
        """
        API used by agents to register a document to knowledge base See also: [AWS API
        Documentation](https://docs.aws.amazon.com/goto/WebAPI/transformagents-2018-05-10/RegisterKnowledgeBaseDocument).

        [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/transformagenticservice.html#TransformAgenticService.Client.register_knowledge_base_document)
        [Show boto3-stubs documentation](https://youtype.github.io/boto3_stubs_docs/agent_builder_types/client/#register_knowledge_base_document)
        """

    def restore_agent(
        self,
        *,
        requestContext: RequestContextTypeDef,
        agentId: str,
        agentInstanceId: str,
        agentType: AgentTypeType,
        agentVersion: str = ...,
        idempotencyToken: str = ...,
    ) -> Dict[str, Any]:
        """
        API used to restore an agent instance, supporting session chaining when an
        agent is approaching the max session lifetime See also: [AWS API
        Documentation](https://docs.aws.amazon.com/goto/WebAPI/transformagents-2018-05-10/RestoreAgent).

        [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/transformagenticservice.html#TransformAgenticService.Client.restore_agent)
        [Show boto3-stubs documentation](https://youtype.github.io/boto3_stubs_docs/agent_builder_types/client/#restore_agent)
        """

    def retrieve_from_knowledge_base(
        self,
        *,
        requestContext: RequestContextTypeDef,
        retrievalQuery: RetrievalQueryTypeDef,
        retrievalScope: RetrievalScopeType,
        retrievalConfiguration: RetrievalConfigurationTypeDef = ...,
        nextToken: str = ...,
    ) -> RetrieveFromKnowledgeBaseResponseTypeDef:
        """
        API used by agents to retrieve information from knowledge base See also: [AWS
        API
        Documentation](https://docs.aws.amazon.com/goto/WebAPI/transformagents-2018-05-10/RetrieveFromKnowledgeBase).

        [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/transformagenticservice.html#TransformAgenticService.Client.retrieve_from_knowledge_base)
        [Show boto3-stubs documentation](https://youtype.github.io/boto3_stubs_docs/agent_builder_types/client/#retrieve_from_knowledge_base)
        """

    def rollback_metering_event(
        self,
        *,
        requestContext: RequestContextTypeDef,
        entity: EntityTypeDef,
        resourceType: ResourceTypeType,
        resourceId: str,
        amendTime: TimestampTypeDef,
    ) -> Dict[str, Any]:
        """
        See also: [AWS API
        Documentation](https://docs.aws.amazon.com/goto/WebAPI/transformagents-2018-05-10/RollbackMeteringEvent).

        [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/transformagenticservice.html#TransformAgenticService.Client.rollback_metering_event)
        [Show boto3-stubs documentation](https://youtype.github.io/boto3_stubs_docs/agent_builder_types/client/#rollback_metering_event)
        """

    def send_message(
        self,
        *,
        requestContext: RequestContextTypeDef,
        agentInstanceId: str,
        params: Mapping[str, Any] = ...,
    ) -> SendMessageResponseTypeDef:
        """
        This API is modeled similarly to the corresponding A2A protocol method
        https://google-a2a.github.io/A2A/specification/#71-messagesend.

        [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/transformagenticservice.html#TransformAgenticService.Client.send_message)
        [Show boto3-stubs documentation](https://youtype.github.io/boto3_stubs_docs/agent_builder_types/client/#send_message)
        """

    def start_hitl_task(
        self,
        *,
        requestContext: RequestContextTypeDef,
        hitlTaskId: str,
        firstInChain: bool = ...,
        idempotencyToken: str = ...,
    ) -> StartHitlTaskResponseTypeDef:
        """
        See also: [AWS API
        Documentation](https://docs.aws.amazon.com/goto/WebAPI/transformagents-2018-05-10/StartHitlTask).

        [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/transformagenticservice.html#TransformAgenticService.Client.start_hitl_task)
        [Show boto3-stubs documentation](https://youtype.github.io/boto3_stubs_docs/agent_builder_types/client/#start_hitl_task)
        """

    def start_knowledge_base_ingestion(
        self,
        *,
        requestContext: RequestContextTypeDef,
        knowledgeBaseConfigType: Literal["TEXT_TITAN_CONFIG"],
        ingestionScopeMetadata: IngestionScopeMetadataTypeDef,
        ingestionConfiguration: IngestionConfigurationTypeDef = ...,
    ) -> StartKnowledgeBaseIngestionResponseTypeDef:
        """
        API used by agents to start ingestion to knowledge base See also: [AWS API
        Documentation](https://docs.aws.amazon.com/goto/WebAPI/transformagents-2018-05-10/StartKnowledgeBaseIngestion).

        [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/transformagenticservice.html#TransformAgenticService.Client.start_knowledge_base_ingestion)
        [Show boto3-stubs documentation](https://youtype.github.io/boto3_stubs_docs/agent_builder_types/client/#start_knowledge_base_ingestion)
        """

    def stop_agent(
        self,
        *,
        requestContext: RequestContextTypeDef,
        agentInstanceId: str,
        idempotencyToken: str = ...,
    ) -> Dict[str, Any]:
        """
        See also: [AWS API
        Documentation](https://docs.aws.amazon.com/goto/WebAPI/transformagents-2018-05-10/StopAgent).

        [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/transformagenticservice.html#TransformAgenticService.Client.stop_agent)
        [Show boto3-stubs documentation](https://youtype.github.io/boto3_stubs_docs/agent_builder_types/client/#stop_agent)
        """

    def update_agent_instance(
        self,
        *,
        requestContext: RequestContextTypeDef,
        agentInstanceId: str,
        agentInstanceStatus: UpdateAgentInstanceStatusType,
        agentInstanceStatusReason: str = ...,
        agentOutput: AgentOutputPayloadTypeDef = ...,
    ) -> Dict[str, Any]:
        """
        API used to Update details like status, output artifact, etc.

        [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/transformagenticservice.html#TransformAgenticService.Client.update_agent_instance)
        [Show boto3-stubs documentation](https://youtype.github.io/boto3_stubs_docs/agent_builder_types/client/#update_agent_instance)
        """

    def update_job_plan_step(
        self,
        *,
        requestContext: RequestContextTypeDef,
        planStep: PlanStepUpdateTypeDef,
        idempotencyToken: str = ...,
    ) -> Dict[str, Any]:
        """
        API used by agents to update fields of an existing step of the job plan.

        [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/transformagenticservice.html#TransformAgenticService.Client.update_job_plan_step)
        [Show boto3-stubs documentation](https://youtype.github.io/boto3_stubs_docs/agent_builder_types/client/#update_job_plan_step)
        """

    def update_job_status(
        self,
        *,
        requestContext: RequestContextTypeDef,
        status: JobStatusType = ...,
        statusInfo: StatusInfoTypeDef = ...,
        idempotencyToken: str = ...,
        notificationArtifactId: str = ...,
    ) -> Dict[str, Any]:
        """
        API used by agents to update the status of a job they are operating on.

        [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/transformagenticservice.html#TransformAgenticService.Client.update_job_status)
        [Show boto3-stubs documentation](https://youtype.github.io/boto3_stubs_docs/agent_builder_types/client/#update_job_status)
        """

    def update_umr_status(
        self,
        *,
        requestContext: RequestContextTypeDef,
        status: UmrStatusType,
        idempotencyToken: str = ...,
    ) -> UpdateUMRStatusResponseTypeDef:
        """
        Updates the status of a UMR engagement.

        [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/transformagenticservice.html#TransformAgenticService.Client.update_umr_status)
        [Show boto3-stubs documentation](https://youtype.github.io/boto3_stubs_docs/agent_builder_types/client/#update_umr_status)
        """

    @overload
    def get_paginator(
        self, operation_name: Literal["list_agent_instances"]
    ) -> ListAgentInstancesPaginator:
        """
        [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/transformagenticservice.html#TransformAgenticService.Client.get_paginator)
        [Show boto3-stubs documentation](https://youtype.github.io/boto3_stubs_docs/agent_builder_types/client/#get_paginator)
        """

    @overload
    def get_paginator(self, operation_name: Literal["list_artifacts"]) -> ListArtifactsPaginator:
        """
        [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/transformagenticservice.html#TransformAgenticService.Client.get_paginator)
        [Show boto3-stubs documentation](https://youtype.github.io/boto3_stubs_docs/agent_builder_types/client/#get_paginator)
        """

    @overload
    def get_paginator(self, operation_name: Literal["list_hitl_tasks"]) -> ListHitlTasksPaginator:
        """
        [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/transformagenticservice.html#TransformAgenticService.Client.get_paginator)
        [Show boto3-stubs documentation](https://youtype.github.io/boto3_stubs_docs/agent_builder_types/client/#get_paginator)
        """

    @overload
    def get_paginator(
        self, operation_name: Literal["list_job_plan_steps"]
    ) -> ListJobPlanStepsPaginator:
        """
        [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/transformagenticservice.html#TransformAgenticService.Client.get_paginator)
        [Show boto3-stubs documentation](https://youtype.github.io/boto3_stubs_docs/agent_builder_types/client/#get_paginator)
        """
