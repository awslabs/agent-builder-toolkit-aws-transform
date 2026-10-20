# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Type annotations for AWS Transform Agentic service client.

[Open documentation](https://vemel.github.io/boto3_stubs_docs/agent_builder_types/client.html)

Usage::

    ```python
    import boto3
    from agent_builder_types import TransformAgenticServiceClient

    client: TransformAgenticServiceClient = boto3.client("transformagenticservice")
    ```
"""

import sys
from datetime import datetime
from typing import Any, Dict, List, Type, Union, overload

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
    PutJobPlanModeTypeDef,
    PutJobPlanResponseTypeDef,
    RefreshAuthTokenResponseTypeDef,
    RequestContextTypeDef,
    RetrievalConfigurationTypeDef,
    RetrievalQueryTypeDef,
    RetrieveFromKnowledgeBaseResponseTypeDef,
    SendMessageResponseTypeDef,
    StartHitlTaskResponseTypeDef,
    StartKnowledgeBaseIngestionResponseTypeDef,
    StatusInfoTypeDef,
    WorklogFilterTypeDef,
    WorklogTypeDef,
)

if sys.version_info >= (3, 8):
    from typing import Literal
else:
    from typing_extensions import Literal


__all__ = ("TransformAgenticServiceClient",)


class BotocoreClientError(BaseException):
    MSG_TEMPLATE: str

    def __init__(self, error_response: Dict[str, Any], operation_name: str) -> None:
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
    [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/1.42.95/reference/services/transformagenticservice.html#TransformAgenticService.Client)
    [Show boto3-stubs documentation](https://vemel.github.io/boto3_stubs_docs/agent_builder_types/client.html)
    """

    meta: ClientMeta

    @property
    def exceptions(self) -> Exceptions:
        """
        TransformAgenticServiceClient exceptions.
        """

    def acknowledge_deletion(
        self, *, requestContext: "RequestContextTypeDef", deletionAcknowledgementToken: str
    ) -> Dict[str, Any]:
        """
        API used by agents to acknowledge they have completed the data cleanup for the
        corresponding job See also: `AWS API Documentation <https://docs.aws.amazon.com/
        goto/WebAPI/transformagents-2018-05-10/AcknowledgeDeletion>`_ **Request Syntax**
        response = client.acknowledge_deletion( ...

        [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/1.42.95/reference/services/transformagenticservice.html#TransformAgenticService.Client.acknowledge_deletion)
        [Show boto3-stubs documentation](https://vemel.github.io/boto3_stubs_docs/agent_builder_types/client.html#acknowledge_deletion)
        """

    def can_paginate(self, operation_name: str) -> bool:
        """
        Check if an operation can be paginated.

        [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/1.42.95/reference/services/transformagenticservice.html#TransformAgenticService.Client.can_paginate)
        [Show boto3-stubs documentation](https://vemel.github.io/boto3_stubs_docs/agent_builder_types/client.html#can_paginate)
        """

    def close(self) -> None:
        """
        Closes underlying endpoint connections.

        [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/1.42.95/reference/services/transformagenticservice.html#TransformAgenticService.Client.close)
        [Show boto3-stubs documentation](https://vemel.github.io/boto3_stubs_docs/agent_builder_types/client.html#close)
        """

    def close_hitl_task(
        self,
        *,
        requestContext: "RequestContextTypeDef",
        hitlTaskId: str,
        closureType: ClosureTypeType = None,
        idempotencyToken: str = None,
    ) -> CloseHitlTaskResponseTypeDef:
        """
        See also: `AWS API Documentation <https://docs.aws.amazon.com/goto/WebAPI/transf
        ormagents-2018-05-10/CloseHitlTask>`_ **Request Syntax** response =
        client.close_hitl_task( requestContext={ 'jobMetadata': { 'jobId': 'string',
        'workspaceId': 'stri...

        [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/1.42.95/reference/services/transformagenticservice.html#TransformAgenticService.Client.close_hitl_task)
        [Show boto3-stubs documentation](https://vemel.github.io/boto3_stubs_docs/agent_builder_types/client.html#close_hitl_task)
        """

    def complete_artifact_upload(
        self, *, requestContext: "RequestContextTypeDef", artifactId: str
    ) -> CompleteArtifactUploadResponseTypeDef:
        """
        API used by agents to let ATX Foundation know that upload is complete.

        [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/1.42.95/reference/services/transformagenticservice.html#TransformAgenticService.Client.complete_artifact_upload)
        [Show boto3-stubs documentation](https://vemel.github.io/boto3_stubs_docs/agent_builder_types/client.html#complete_artifact_upload)
        """

    def copy_artifact(
        self, *, requestContext: "RequestContextTypeDef", artifactId: str, idempotencyToken: str = None
    ) -> CopyArtifactResponseTypeDef:
        """
        API used by agents to copy artifacts from artifact store bucket to public bucket
        See also: `AWS API Documentation <https://docs.aws.amazon.com/goto/WebAPI/transf
        ormagents-2018-05-10/CopyArtifact>`_ **Request Syntax** response =
        client.copy_artifact( requestContext={ 'jo...

        [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/1.42.95/reference/services/transformagenticservice.html#TransformAgenticService.Client.copy_artifact)
        [Show boto3-stubs documentation](https://vemel.github.io/boto3_stubs_docs/agent_builder_types/client.html#copy_artifact)
        """

    def create_artifact_download_url(
        self, *, requestContext: "RequestContextTypeDef", artifactId: str, visibility: VisibilityType = None
    ) -> CreateArtifactDownloadUrlResponseTypeDef:
        """
        API used by agents to generate an S3 presigned URL for downloading an artifact.

        [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/1.42.95/reference/services/transformagenticservice.html#TransformAgenticService.Client.create_artifact_download_url)
        [Show boto3-stubs documentation](https://vemel.github.io/boto3_stubs_docs/agent_builder_types/client.html#create_artifact_download_url)
        """

    def create_artifact_upload_url(
        self,
        *,
        requestContext: "RequestContextTypeDef",
        contentDigest: "ContentDigestTypeDef",
        artifactReference: "ArtifactReferenceTypeDef",
        label: str = None,
        planStepId: str = None,
        visibility: VisibilityType = None,
        fileMetadata: "FileMetadataTypeDef" = None,
    ) -> CreateArtifactUploadUrlResponseTypeDef:
        """
        API used by agents to generate an S3 presigned URL for uploading an artifact.

        [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/1.42.95/reference/services/transformagenticservice.html#TransformAgenticService.Client.create_artifact_upload_url)
        [Show boto3-stubs documentation](https://vemel.github.io/boto3_stubs_docs/agent_builder_types/client.html#create_artifact_upload_url)
        """

    def create_hitl_task(
        self,
        *,
        requestContext: "RequestContextTypeDef",
        uxComponentId: str,
        description: str,
        title: str,
        severity: SeverityType = None,
        hitlTaskType: HitlTaskTypeType = None,
        stepId: str = None,
        blockingType: BlockingTypeType = None,
        hitlRequestArtifact: "HitlTaskArtifactTypeDef" = None,
        expiredAt: Union[datetime, str] = None,
        tag: str = None,
        idempotencyToken: str = None,
        category: CategoryType = None,
    ) -> CreateHitlTaskResponseTypeDef:
        """
        API used by agents to trigger a Human-In-The-Loop request.

        [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/1.42.95/reference/services/transformagenticservice.html#TransformAgenticService.Client.create_hitl_task)
        [Show boto3-stubs documentation](https://vemel.github.io/boto3_stubs_docs/agent_builder_types/client.html#create_hitl_task)
        """

    def create_skill_download_url(
        self,
        *,
        requestContext: "RequestContextTypeDef",
        skillName: str,
        idempotencyToken: str = None,
        version: str = None,
    ) -> CreateSkillDownloadUrlResponseTypeDef:
        """
        See also: `AWS API Documentation <https://docs.aws.amazon.com/goto/WebAPI/transf
        ormagents-2018-05-10/CreateSkillDownloadUrl>`_ **Request Syntax** response =
        client.create_skill_download_url( requestContext={ 'jobMetadata': { 'jobId':
        'string', '...

        [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/1.42.95/reference/services/transformagenticservice.html#TransformAgenticService.Client.create_skill_download_url)
        [Show boto3-stubs documentation](https://vemel.github.io/boto3_stubs_docs/agent_builder_types/client.html#create_skill_download_url)
        """

    def create_worklog(
        self, *, requestContext: "RequestContextTypeDef", worklog: "WorklogTypeDef", idempotencyToken: str = None
    ) -> Dict[str, Any]:
        """
        API to allow ingestion of agent/ HITL/ job level worklogs See also: `AWS API
        Documentation <https://docs.aws.amazon.com/goto/WebAPI/transformagents-2018-05-
        10/CreateWorklog>`_ **Request Syntax** response = client.create_worklog(
        requestContext={ 'jobMetadata': { ...

        [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/1.42.95/reference/services/transformagenticservice.html#TransformAgenticService.Client.create_worklog)
        [Show boto3-stubs documentation](https://vemel.github.io/boto3_stubs_docs/agent_builder_types/client.html#create_worklog)
        """

    def delete_job_plan_step(
        self, *, requestContext: "RequestContextTypeDef", stepId: str, idempotencyToken: str = None
    ) -> Dict[str, Any]:
        """
        API used by agents to delete an existing step of the job plan.

        [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/1.42.95/reference/services/transformagenticservice.html#TransformAgenticService.Client.delete_job_plan_step)
        [Show boto3-stubs documentation](https://vemel.github.io/boto3_stubs_docs/agent_builder_types/client.html#delete_job_plan_step)
        """

    def deregister_knowledge_base_document(
        self,
        *,
        requestContext: "RequestContextTypeDef",
        artifactId: str,
        knowledgeBaseConfigType: Literal["TEXT_TITAN_CONFIG"],
    ) -> Dict[str, Any]:
        """
        API used by agents to deregister a document from knowledge base See also: `AWS
        API Documentation <https://docs.aws.amazon.com/goto/WebAPI/transformagents-2018-
        05-10/DeregisterKnowledgeBaseDocument>`_ **Request Syntax** response =
        client.deregister_knowledge_base_document( request...

        [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/1.42.95/reference/services/transformagenticservice.html#TransformAgenticService.Client.deregister_knowledge_base_document)
        [Show boto3-stubs documentation](https://vemel.github.io/boto3_stubs_docs/agent_builder_types/client.html#deregister_knowledge_base_document)
        """

    def generate_presigned_url(
        self,
        ClientMethod: str,
        Params: Dict[str, Any] = None,
        ExpiresIn: int = 3600,
        HttpMethod: str = None,
    ) -> str:
        """
        Generate a presigned url given a client, its method, and arguments.

        [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/1.42.95/reference/services/transformagenticservice.html#TransformAgenticService.Client.generate_presigned_url)
        [Show boto3-stubs documentation](https://vemel.github.io/boto3_stubs_docs/agent_builder_types/client.html#generate_presigned_url)
        """

    def get_agent_instance(
        self, *, requestContext: "RequestContextTypeDef", agentInstanceId: str
    ) -> GetAgentInstanceResponseTypeDef:
        """
        API used to Get details about a specific agent's invocation See also: `AWS API
        Documentation <https://docs.aws.amazon.com/goto/WebAPI/transformagents-2018-05-
        10/GetAgentInstance>`_ **Request Syntax** response = client.get_agent_instance(
        requestContext={ 'jobMetadata': ...

        [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/1.42.95/reference/services/transformagenticservice.html#TransformAgenticService.Client.get_agent_instance)
        [Show boto3-stubs documentation](https://vemel.github.io/boto3_stubs_docs/agent_builder_types/client.html#get_agent_instance)
        """

    def get_agent_version(
        self, *, requestContext: "RequestContextTypeDef", name: str, version: str = None
    ) -> GetAgentVersionResponseTypeDef:
        """
        See also: `AWS API Documentation <https://docs.aws.amazon.com/goto/WebAPI/transf
        ormagents-2018-05-10/GetAgentVersion>`_ **Request Syntax** response =
        client.get_agent_version( requestContext={ 'jobMetadata': { 'jobId': 'string',
        'workspaceId': '...

        [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/1.42.95/reference/services/transformagenticservice.html#TransformAgenticService.Client.get_agent_version)
        [Show boto3-stubs documentation](https://vemel.github.io/boto3_stubs_docs/agent_builder_types/client.html#get_agent_version)
        """

    def get_artifact_metadata(
        self, *, requestContext: "RequestContextTypeDef", artifactId: str
    ) -> GetArtifactMetadataResponseTypeDef:
        """
        This API is used to retrieve metadata about an artifact See also: `AWS API
        Documentation <https://docs.aws.amazon.com/goto/WebAPI/transformagents-2018-05-
        10/GetArtifactMetadata>`_ **Request Syntax** response =
        client.get_artifact_metadata( requestContext={ 'jobMetadata'...

        [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/1.42.95/reference/services/transformagenticservice.html#TransformAgenticService.Client.get_artifact_metadata)
        [Show boto3-stubs documentation](https://vemel.github.io/boto3_stubs_docs/agent_builder_types/client.html#get_artifact_metadata)
        """

    def get_connector(
        self, *, requestContext: "RequestContextTypeDef", connectorId: str
    ) -> GetConnectorResponseTypeDef:
        """
        API used by agents to get resource level details of connector by connectorId See
        also: `AWS API Documentation <https://docs.aws.amazon.com/goto/WebAPI/transforma
        gents-2018-05-10/GetConnector>`_ **Request Syntax** response =
        client.get_connector( requestContext={ 'jobMet...

        [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/1.42.95/reference/services/transformagenticservice.html#TransformAgenticService.Client.get_connector)
        [Show boto3-stubs documentation](https://vemel.github.io/boto3_stubs_docs/agent_builder_types/client.html#get_connector)
        """

    def get_hitl_task(self, *, requestContext: "RequestContextTypeDef", hitlTaskId: str) -> GetHitlTaskResponseTypeDef:
        """
        API used by agents to Get the status for a Human-In-The-Loop request.

        [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/1.42.95/reference/services/transformagenticservice.html#TransformAgenticService.Client.get_hitl_task)
        [Show boto3-stubs documentation](https://vemel.github.io/boto3_stubs_docs/agent_builder_types/client.html#get_hitl_task)
        """

    def get_job(
        self, *, requestContext: "RequestContextTypeDef", includeObjective: bool = None
    ) -> GetJobResponseTypeDef:
        """
        API used by agents to Get details about a Transformation Job See also: `AWS API
        Documentation
        <https://docs.aws.amazon.com/goto/WebAPI/transformagents-2018-05-10/GetJob>`_
        **Request Syntax** response = client.get_job( requestContext={ 'jobMetadata': {
        'job...

        [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/1.42.95/reference/services/transformagenticservice.html#TransformAgenticService.Client.get_job)
        [Show boto3-stubs documentation](https://vemel.github.io/boto3_stubs_docs/agent_builder_types/client.html#get_job)
        """

    def get_knowledge_base_ingestion(
        self, *, requestContext: "RequestContextTypeDef", ingestionId: str
    ) -> GetKnowledgeBaseIngestionResponseTypeDef:
        """
        API used by agents to get ingestion details See also: `AWS API Documentation <ht
        tps://docs.aws.amazon.com/goto/WebAPI/transformagents-2018-05-
        10/GetKnowledgeBaseIngestion>`_ **Request Syntax** response =
        client.get_knowledge_base_ingestion( requestContext={ 'jobMetadata...

        [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/1.42.95/reference/services/transformagenticservice.html#TransformAgenticService.Client.get_knowledge_base_ingestion)
        [Show boto3-stubs documentation](https://vemel.github.io/boto3_stubs_docs/agent_builder_types/client.html#get_knowledge_base_ingestion)
        """

    def get_task(
        self, *, requestContext: "RequestContextTypeDef", agentInstanceId: str, params: Dict[str, Any] = None
    ) -> GetTaskResponseTypeDef:
        """
        This API is modeled similarly to the corresponding A2A protocol method
        (https://a2a-protocol.org/latest/specification/#73-tasksget).

        [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/1.42.95/reference/services/transformagenticservice.html#TransformAgenticService.Client.get_task)
        [Show boto3-stubs documentation](https://vemel.github.io/boto3_stubs_docs/agent_builder_types/client.html#get_task)
        """

    def get_temporary_credentials_for_connector(
        self, *, requestContext: "RequestContextTypeDef", connectorId: str, targetRegion: str = None
    ) -> GetTemporaryCredentialsForConnectorResponseTypeDef:
        """
        API used by agents to get temporary credentials and details related to data
        source See also: `AWS API Documentation <https://docs.aws.amazon.com/goto/WebAPI
        /transformagents-2018-05-10/GetTemporaryCredentialsForConnector>`_ **Request
        Syntax** response = client.get_temporary_credentials_...

        [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/1.42.95/reference/services/transformagenticservice.html#TransformAgenticService.Client.get_temporary_credentials_for_connector)
        [Show boto3-stubs documentation](https://vemel.github.io/boto3_stubs_docs/agent_builder_types/client.html#get_temporary_credentials_for_connector)
        """

    def get_usage(
        self, *, requestContext: "RequestContextTypeDef", resourceTypes: List[ResourceTypeType]
    ) -> GetUsageResponseTypeDef:
        """
        API used to get a customers usage of a resource type See also: `AWS API
        Documentation
        <https://docs.aws.amazon.com/goto/WebAPI/transformagents-2018-05-10/GetUsage>`_
        **Request Syntax** response = client.get_usage( requestContext={ 'jobMetadata':
        { 'jobId':...

        [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/1.42.95/reference/services/transformagenticservice.html#TransformAgenticService.Client.get_usage)
        [Show boto3-stubs documentation](https://vemel.github.io/boto3_stubs_docs/agent_builder_types/client.html#get_usage)
        """

    def invoke_agent(
        self,
        *,
        requestContext: "RequestContextTypeDef",
        agentId: str,
        inputPayload: "AgentInputPayloadTypeDef" = None,
        idempotencyToken: str = None,
        agentVersion: str = None,
        agentInstanceId: str = None,
        agentType: AgentTypeType = None,
    ) -> InvokeAgentResponseTypeDef:
        """
        API used to Invoke Agents See also: `AWS API Documentation <https://docs.aws.ama
        zon.com/goto/WebAPI/transformagents-2018-05-10/InvokeAgent>`_ **Request Syntax**
        response = client.invoke_agent( requestContext={ 'jobMetadata': { 'jobId':
        'string', ...

        [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/1.42.95/reference/services/transformagenticservice.html#TransformAgenticService.Client.invoke_agent)
        [Show boto3-stubs documentation](https://vemel.github.io/boto3_stubs_docs/agent_builder_types/client.html#invoke_agent)
        """

    def list_agent_instances(
        self,
        *,
        requestContext: "RequestContextTypeDef",
        nextToken: str = None,
        agentFilter: "ListAgentFilterTypeDef" = None,
        maxResults: int = None,
    ) -> ListAgentInstancesResponseTypeDef:
        """
        API used to List all agent invocations for a specific transformation job See
        also: `AWS API Documentation <https://docs.aws.amazon.com/goto/WebAPI/transforma
        gents-2018-05-10/ListAgentInstances>`_ **Request Syntax** response =
        client.list_agent_instances( requestContext={ ...

        [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/1.42.95/reference/services/transformagenticservice.html#TransformAgenticService.Client.list_agent_instances)
        [Show boto3-stubs documentation](https://vemel.github.io/boto3_stubs_docs/agent_builder_types/client.html#list_agent_instances)
        """

    def list_agents(
        self,
        *,
        requestContext: "RequestContextTypeDef",
        agentFilter: "ListAgentsFilterTypeDef" = None,
        nextToken: str = None,
        maxResults: int = None,
    ) -> ListAgentsResponseTypeDef:
        """
        See also: `AWS API Documentation <https://docs.aws.amazon.com/goto/WebAPI/transf
        ormagents-2018-05-10/ListAgents>`_ **Request Syntax** response =
        client.list_agents( requestContext={ 'jobMetadata': { 'jobId': 'string',
        'workspaceId': 'string' ...

        [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/1.42.95/reference/services/transformagenticservice.html#TransformAgenticService.Client.list_agents)
        [Show boto3-stubs documentation](https://vemel.github.io/boto3_stubs_docs/agent_builder_types/client.html#list_agents)
        """

    def list_artifacts(
        self,
        *,
        requestContext: "RequestContextTypeDef",
        artifactFilter: "ArtifactFilterTypeDef" = None,
        nextToken: str = None,
        pathPrefix: str = None,
        maxResults: int = None,
    ) -> ListArtifactsResponseTypeDef:
        """
        API used by agents to list artifacts for a transformation job See also: `AWS API
        Documentation <https://docs.aws.amazon.com/goto/WebAPI/transformagents-2018-05-
        10/ListArtifacts>`_ **Request Syntax** response = client.list_artifacts(
        requestContext={ 'jobMetadata': { ...

        [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/1.42.95/reference/services/transformagenticservice.html#TransformAgenticService.Client.list_artifacts)
        [Show boto3-stubs documentation](https://vemel.github.io/boto3_stubs_docs/agent_builder_types/client.html#list_artifacts)
        """

    def list_connectors(
        self, *, requestContext: "RequestContextTypeDef", maxResults: int = None, nextToken: str = None
    ) -> ListConnectorsResponseTypeDef:
        """
        API used by agents to get list of all the connectors available based on the
        agent Type See also: `AWS API Documentation <https://docs.aws.amazon.com/goto/We
        bAPI/transformagents-2018-05-10/ListConnectors>`_ **Request Syntax** response =
        client.list_connectors( requestContext={ ...

        [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/1.42.95/reference/services/transformagenticservice.html#TransformAgenticService.Client.list_connectors)
        [Show boto3-stubs documentation](https://vemel.github.io/boto3_stubs_docs/agent_builder_types/client.html#list_connectors)
        """

    def list_hitl_tasks(
        self,
        *,
        requestContext: "RequestContextTypeDef",
        taskType: HitlTaskTypeType,
        taskFilter: "HitlTaskFilterTypeDef" = None,
        nextToken: str = None,
        maxResults: int = None,
    ) -> ListHitlTasksResponseTypeDef:
        """
        See also: `AWS API Documentation <https://docs.aws.amazon.com/goto/WebAPI/transf
        ormagents-2018-05-10/ListHitlTasks>`_ **Request Syntax** response =
        client.list_hitl_tasks( requestContext={ 'jobMetadata': { 'jobId': 'string',
        'workspaceId': 'stri...

        [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/1.42.95/reference/services/transformagenticservice.html#TransformAgenticService.Client.list_hitl_tasks)
        [Show boto3-stubs documentation](https://vemel.github.io/boto3_stubs_docs/agent_builder_types/client.html#list_hitl_tasks)
        """

    def list_job_plan_steps(
        self,
        *,
        requestContext: "RequestContextTypeDef",
        parentStepId: str = None,
        maxResults: int = None,
        nextToken: str = None,
    ) -> ListJobPlanStepsResponseTypeDef:
        """
        API used by agents to list the plan steps for a job See also: `AWS API
        Documentation <https://docs.aws.amazon.com/goto/WebAPI/transformagents-2018-05-
        10/ListJobPlanSteps>`_ **Request Syntax** response = client.list_job_plan_steps(
        requestContext={ 'jobMetadata': { ...

        [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/1.42.95/reference/services/transformagenticservice.html#TransformAgenticService.Client.list_job_plan_steps)
        [Show boto3-stubs documentation](https://vemel.github.io/boto3_stubs_docs/agent_builder_types/client.html#list_job_plan_steps)
        """

    def list_worklogs(
        self,
        *,
        requestContext: "RequestContextTypeDef",
        worklogFilter: "WorklogFilterTypeDef" = None,
        nextToken: str = None,
    ) -> ListWorklogsResponseTypeDef:
        """
        API to allow retrieval of worklogs for a specific job.

        [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/1.42.95/reference/services/transformagenticservice.html#TransformAgenticService.Client.list_worklogs)
        [Show boto3-stubs documentation](https://vemel.github.io/boto3_stubs_docs/agent_builder_types/client.html#list_worklogs)
        """

    def publish_metering_event(
        self,
        *,
        requestContext: "RequestContextTypeDef",
        entity: "EntityTypeDef",
        resourceType: ResourceTypeType,
        resourceId: str,
        startTime: Union[datetime, str],
        amount: "MeteredAmountTypeDef" = None,
        idempotencyToken: str = None,
        attributes: List["MeteringAttributeTypeDef"] = None,
    ) -> Dict[str, Any]:
        """
        See also: `AWS API Documentation <https://docs.aws.amazon.com/goto/WebAPI/transf
        ormagents-2018-05-10/PublishMeteringEvent>`_ **Request Syntax** response =
        client.publish_metering_event( requestContext={ 'jobMetadata': { 'jobId':
        'string', 'works...

        [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/1.42.95/reference/services/transformagenticservice.html#TransformAgenticService.Client.publish_metering_event)
        [Show boto3-stubs documentation](https://vemel.github.io/boto3_stubs_docs/agent_builder_types/client.html#publish_metering_event)
        """

    def put_job_plan(
        self,
        *,
        requestContext: "RequestContextTypeDef",
        plan: "JobPlanTreeTypeDef",
        mode: "PutJobPlanModeTypeDef",
        idempotencyToken: str = None,
    ) -> PutJobPlanResponseTypeDef:
        """
        API used by agents to put a job plan See also: `AWS API Documentation <https://d
        ocs.aws.amazon.com/goto/WebAPI/transformagents-2018-05-10/PutJobPlan>`_
        **Request Syntax** response = client.put_job_plan( requestContext={
        'jobMetadata': { 'jobId': 'string', ...

        [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/1.42.95/reference/services/transformagenticservice.html#TransformAgenticService.Client.put_job_plan)
        [Show boto3-stubs documentation](https://vemel.github.io/boto3_stubs_docs/agent_builder_types/client.html#put_job_plan)
        """

    def refresh_auth_token(
        self, *, requestContext: "RequestContextTypeDef", sessionDuration: int
    ) -> RefreshAuthTokenResponseTypeDef:
        """
        API used to generate a new agent authorization token with a later expiration
        time See also: `AWS API Documentation <https://docs.aws.amazon.com/goto/WebAPI/t
        ransformagents-2018-05-10/RefreshAuthToken>`_ **Request Syntax** response =
        client.refresh_auth_token( requestContext={ ...

        [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/1.42.95/reference/services/transformagenticservice.html#TransformAgenticService.Client.refresh_auth_token)
        [Show boto3-stubs documentation](https://vemel.github.io/boto3_stubs_docs/agent_builder_types/client.html#refresh_auth_token)
        """

    def register_knowledge_base_document(
        self,
        *,
        requestContext: "RequestContextTypeDef",
        artifactId: str,
        knowledgeBaseConfigType: Literal["TEXT_TITAN_CONFIG"],
        indexingMetadata: Dict[str, str] = None,
    ) -> Dict[str, Any]:
        """
        API used by agents to register a document to knowledge base See also: `AWS API
        Documentation <https://docs.aws.amazon.com/goto/WebAPI/transformagents-2018-05-
        10/RegisterKnowledgeBaseDocument>`_ **Request Syntax** response =
        client.register_knowledge_base_document( requestContext=...

        [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/1.42.95/reference/services/transformagenticservice.html#TransformAgenticService.Client.register_knowledge_base_document)
        [Show boto3-stubs documentation](https://vemel.github.io/boto3_stubs_docs/agent_builder_types/client.html#register_knowledge_base_document)
        """

    def restore_agent(
        self,
        *,
        requestContext: "RequestContextTypeDef",
        agentId: str,
        agentInstanceId: str,
        agentType: AgentTypeType,
        agentVersion: str = None,
        idempotencyToken: str = None,
    ) -> Dict[str, Any]:
        """
        API used to restore an agent instance, supporting session chaining when an agent
        is approaching the max session lifetime See also: `AWS API Documentation <https:
        //docs.aws.amazon.com/goto/WebAPI/transformagents-2018-05-10/RestoreAgent>`_
        **Request Syntax** response = client.restore_age...

        [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/1.42.95/reference/services/transformagenticservice.html#TransformAgenticService.Client.restore_agent)
        [Show boto3-stubs documentation](https://vemel.github.io/boto3_stubs_docs/agent_builder_types/client.html#restore_agent)
        """

    def retrieve_from_knowledge_base(
        self,
        *,
        requestContext: "RequestContextTypeDef",
        retrievalQuery: "RetrievalQueryTypeDef",
        retrievalScope: RetrievalScopeType,
        retrievalConfiguration: "RetrievalConfigurationTypeDef" = None,
        nextToken: str = None,
    ) -> RetrieveFromKnowledgeBaseResponseTypeDef:
        """
        API used by agents to retrieve information from knowledge base See also: `AWS
        API Documentation <https://docs.aws.amazon.com/goto/WebAPI/transformagents-2018-
        05-10/RetrieveFromKnowledgeBase>`_ **Request Syntax** response =
        client.retrieve_from_knowledge_base( requestContext={ ...

        [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/1.42.95/reference/services/transformagenticservice.html#TransformAgenticService.Client.retrieve_from_knowledge_base)
        [Show boto3-stubs documentation](https://vemel.github.io/boto3_stubs_docs/agent_builder_types/client.html#retrieve_from_knowledge_base)
        """

    def rollback_metering_event(
        self,
        *,
        requestContext: "RequestContextTypeDef",
        entity: "EntityTypeDef",
        resourceType: ResourceTypeType,
        resourceId: str,
        amendTime: Union[datetime, str],
    ) -> Dict[str, Any]:
        """
        See also: `AWS API Documentation <https://docs.aws.amazon.com/goto/WebAPI/transf
        ormagents-2018-05-10/RollbackMeteringEvent>`_ **Request Syntax** response =
        client.rollback_metering_event( requestContext={ 'jobMetadata': { 'jobId':
        'string', 'wor...

        [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/1.42.95/reference/services/transformagenticservice.html#TransformAgenticService.Client.rollback_metering_event)
        [Show boto3-stubs documentation](https://vemel.github.io/boto3_stubs_docs/agent_builder_types/client.html#rollback_metering_event)
        """

    def send_message(
        self, *, requestContext: "RequestContextTypeDef", agentInstanceId: str, params: Dict[str, Any] = None
    ) -> SendMessageResponseTypeDef:
        """
        This API is modeled similarly to the corresponding A2A protocol method
        https://google-a2a.github.io/A2A/specification/#71-messagesend.

        [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/1.42.95/reference/services/transformagenticservice.html#TransformAgenticService.Client.send_message)
        [Show boto3-stubs documentation](https://vemel.github.io/boto3_stubs_docs/agent_builder_types/client.html#send_message)
        """

    def start_hitl_task(
        self,
        *,
        requestContext: "RequestContextTypeDef",
        hitlTaskId: str,
        firstInChain: bool = None,
        idempotencyToken: str = None,
    ) -> StartHitlTaskResponseTypeDef:
        """
        See also: `AWS API Documentation <https://docs.aws.amazon.com/goto/WebAPI/transf
        ormagents-2018-05-10/StartHitlTask>`_ **Request Syntax** response =
        client.start_hitl_task( requestContext={ 'jobMetadata': { 'jobId': 'string',
        'workspaceId': 'stri...

        [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/1.42.95/reference/services/transformagenticservice.html#TransformAgenticService.Client.start_hitl_task)
        [Show boto3-stubs documentation](https://vemel.github.io/boto3_stubs_docs/agent_builder_types/client.html#start_hitl_task)
        """

    def start_knowledge_base_ingestion(
        self,
        *,
        requestContext: "RequestContextTypeDef",
        knowledgeBaseConfigType: Literal["TEXT_TITAN_CONFIG"],
        ingestionScopeMetadata: "IngestionScopeMetadataTypeDef",
        ingestionConfiguration: "IngestionConfigurationTypeDef" = None,
    ) -> StartKnowledgeBaseIngestionResponseTypeDef:
        """
        API used by agents to start ingestion to knowledge base See also: `AWS API
        Documentation <https://docs.aws.amazon.com/goto/WebAPI/transformagents-2018-05-
        10/StartKnowledgeBaseIngestion>`_ **Request Syntax** response =
        client.start_knowledge_base_ingestion( requestContext={ ...

        [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/1.42.95/reference/services/transformagenticservice.html#TransformAgenticService.Client.start_knowledge_base_ingestion)
        [Show boto3-stubs documentation](https://vemel.github.io/boto3_stubs_docs/agent_builder_types/client.html#start_knowledge_base_ingestion)
        """

    def stop_agent(
        self, *, requestContext: "RequestContextTypeDef", agentInstanceId: str, idempotencyToken: str = None
    ) -> Dict[str, Any]:
        """
        See also: `AWS API Documentation
        <https://docs.aws.amazon.com/goto/WebAPI/transformagents-2018-05-10/StopAgent>`_
        **Request Syntax** response = client.stop_agent( requestContext={ 'jobMetadata':
        { 'jobId': 'string', 'workspaceId': 'string' ...

        [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/1.42.95/reference/services/transformagenticservice.html#TransformAgenticService.Client.stop_agent)
        [Show boto3-stubs documentation](https://vemel.github.io/boto3_stubs_docs/agent_builder_types/client.html#stop_agent)
        """

    def update_agent_instance(
        self,
        *,
        requestContext: "RequestContextTypeDef",
        agentInstanceId: str,
        agentInstanceStatus: UpdateAgentInstanceStatusType,
        agentInstanceStatusReason: str = None,
        agentOutput: "AgentOutputPayloadTypeDef" = None,
    ) -> Dict[str, Any]:
        """
        API used to Update details like status, output artifact, etc.

        [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/1.42.95/reference/services/transformagenticservice.html#TransformAgenticService.Client.update_agent_instance)
        [Show boto3-stubs documentation](https://vemel.github.io/boto3_stubs_docs/agent_builder_types/client.html#update_agent_instance)
        """

    def update_job_plan_step(
        self,
        *,
        requestContext: "RequestContextTypeDef",
        planStep: "PlanStepUpdateTypeDef",
        idempotencyToken: str = None,
    ) -> Dict[str, Any]:
        """
        API used by agents to update fields of an existing step of the job plan.

        [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/1.42.95/reference/services/transformagenticservice.html#TransformAgenticService.Client.update_job_plan_step)
        [Show boto3-stubs documentation](https://vemel.github.io/boto3_stubs_docs/agent_builder_types/client.html#update_job_plan_step)
        """

    def update_job_status(
        self,
        *,
        requestContext: "RequestContextTypeDef",
        status: JobStatusType = None,
        statusInfo: "StatusInfoTypeDef" = None,
        idempotencyToken: str = None,
        notificationArtifactId: str = None,
    ) -> Dict[str, Any]:
        """
        API used by agents to update the status of a job they are operating on.

        [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/1.42.95/reference/services/transformagenticservice.html#TransformAgenticService.Client.update_job_status)
        [Show boto3-stubs documentation](https://vemel.github.io/boto3_stubs_docs/agent_builder_types/client.html#update_job_status)
        """

    @overload
    def get_paginator(self, operation_name: Literal["list_agent_instances"]) -> ListAgentInstancesPaginator:
        """
        [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/1.42.95/reference/services/transformagenticservice.html#TransformAgenticService.Paginator.ListAgentInstances)
        [Show boto3-stubs documentation](https://vemel.github.io/boto3_stubs_docs/agent_builder_types/paginators.html#listagentinstancespaginator)
        """

    @overload
    def get_paginator(self, operation_name: Literal["list_artifacts"]) -> ListArtifactsPaginator:
        """
        [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/1.42.95/reference/services/transformagenticservice.html#TransformAgenticService.Paginator.ListArtifacts)
        [Show boto3-stubs documentation](https://vemel.github.io/boto3_stubs_docs/agent_builder_types/paginators.html#listartifactspaginator)
        """

    @overload
    def get_paginator(self, operation_name: Literal["list_hitl_tasks"]) -> ListHitlTasksPaginator:
        """
        [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/1.42.95/reference/services/transformagenticservice.html#TransformAgenticService.Paginator.ListHitlTasks)
        [Show boto3-stubs documentation](https://vemel.github.io/boto3_stubs_docs/agent_builder_types/paginators.html#listhitltaskspaginator)
        """

    @overload
    def get_paginator(self, operation_name: Literal["list_job_plan_steps"]) -> ListJobPlanStepsPaginator:
        """
        [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/1.42.95/reference/services/transformagenticservice.html#TransformAgenticService.Paginator.ListJobPlanSteps)
        [Show boto3-stubs documentation](https://vemel.github.io/boto3_stubs_docs/agent_builder_types/paginators.html#listjobplanstepspaginator)
        """
