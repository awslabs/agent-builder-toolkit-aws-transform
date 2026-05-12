"""
Type annotations for AWS Transform Agentic service client.

[Open documentation](https://vemel.github.io/boto3_stubs_docs/agent_builder_types/client.html)

Usage::

    ```python
    import boto3
    from agent_builder_types import TransformAgenticServiceClient

    client: TransformAgenticServiceClient = boto3.client("awstransformagenticservice")
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
    GetTemporaryCredentialsForRoleResponseTypeDef,
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
    MetadataContextTypeDef,
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
    StartJobResponseTypeDef,
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
    [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/1.42.95/reference/services/awstransformagenticservice.html#Elasticgumbyagenticservice.Client)
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
        See also: `AWS API Documentation <https://docs.aws.amazon.com/goto/WebAPI/elasti
        cgumbyagentic-2018-05-10/AcknowledgeDeletion>`_ **Request Syntax** response =
        client.acknowledge_deletion( requestContext={ 'jobMetadata': { 'jobId':
        'string', 'work...

        [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/1.42.95/reference/services/awstransformagenticservice.html#Elasticgumbyagenticservice.Client.acknowledge_deletion)
        [Show boto3-stubs documentation](https://vemel.github.io/boto3_stubs_docs/agent_builder_types/client.html#acknowledge_deletion)
        """

    def can_paginate(self, operation_name: str) -> bool:
        """
        Check if an operation can be paginated.

        [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/1.42.95/reference/services/awstransformagenticservice.html#Elasticgumbyagenticservice.Client.can_paginate)
        [Show boto3-stubs documentation](https://vemel.github.io/boto3_stubs_docs/agent_builder_types/client.html#can_paginate)
        """

    def close(self) -> None:
        """
        Closes underlying endpoint connections.

        [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/1.42.95/reference/services/awstransformagenticservice.html#Elasticgumbyagenticservice.Client.close)
        [Show boto3-stubs documentation](https://vemel.github.io/boto3_stubs_docs/agent_builder_types/client.html#close)
        """

    def close_hitl_task(
        self,
        *,
        requestContext: "RequestContextTypeDef",
        hitlTaskId: str,
        closureType: ClosureTypeType = None,
        idempotencyToken: str = None
    ) -> CloseHitlTaskResponseTypeDef:
        """
        See also: `AWS API Documentation <https://docs.aws.amazon.com/goto/WebAPI/elasti
        cgumbyagentic-2018-05-10/CloseHitlTask>`_ **Request Syntax** response =
        client.close_hitl_task( requestContext={ 'jobMetadata': { 'jobId': 'string',
        'workspaceId': '...

        [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/1.42.95/reference/services/awstransformagenticservice.html#Elasticgumbyagenticservice.Client.close_hitl_task)
        [Show boto3-stubs documentation](https://vemel.github.io/boto3_stubs_docs/agent_builder_types/client.html#close_hitl_task)
        """

    def complete_artifact_upload(
        self, *, requestContext: "RequestContextTypeDef", artifactId: str
    ) -> CompleteArtifactUploadResponseTypeDef:
        """
        See also: `AWS API Documentation <https://docs.aws.amazon.com/goto/WebAPI/elasti
        cgumbyagentic-2018-05-10/CompleteArtifactUpload>`_ **Request Syntax** response =
        client.complete_artifact_upload( requestContext={ 'jobMetadata': { 'jobId':
        'string', ...

        [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/1.42.95/reference/services/awstransformagenticservice.html#Elasticgumbyagenticservice.Client.complete_artifact_upload)
        [Show boto3-stubs documentation](https://vemel.github.io/boto3_stubs_docs/agent_builder_types/client.html#complete_artifact_upload)
        """

    def copy_artifact(
        self,
        *,
        requestContext: "RequestContextTypeDef",
        artifactId: str,
        idempotencyToken: str = None
    ) -> CopyArtifactResponseTypeDef:
        """
        See also: `AWS API Documentation <https://docs.aws.amazon.com/goto/WebAPI/elasti
        cgumbyagentic-2018-05-10/CopyArtifact>`_ **Request Syntax** response =
        client.copy_artifact( requestContext={ 'jobMetadata': { 'jobId': 'string',
        'workspaceId': 'str...

        [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/1.42.95/reference/services/awstransformagenticservice.html#Elasticgumbyagenticservice.Client.copy_artifact)
        [Show boto3-stubs documentation](https://vemel.github.io/boto3_stubs_docs/agent_builder_types/client.html#copy_artifact)
        """

    def create_artifact_download_url(
        self,
        *,
        requestContext: "RequestContextTypeDef",
        artifactId: str,
        visibility: VisibilityType = None
    ) -> CreateArtifactDownloadUrlResponseTypeDef:
        """
        See also: `AWS API Documentation <https://docs.aws.amazon.com/goto/WebAPI/elasti
        cgumbyagentic-2018-05-10/CreateArtifactDownloadUrl>`_ **Request Syntax**
        response = client.create_artifact_download_url( requestContext={ 'jobMetadata':
        { 'jobId': 'string', ...

        [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/1.42.95/reference/services/awstransformagenticservice.html#Elasticgumbyagenticservice.Client.create_artifact_download_url)
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
        metadata: "MetadataContextTypeDef" = None,
        fileMetadata: "FileMetadataTypeDef" = None
    ) -> CreateArtifactUploadUrlResponseTypeDef:
        """
        See also: `AWS API Documentation <https://docs.aws.amazon.com/goto/WebAPI/elasti
        cgumbyagentic-2018-05-10/CreateArtifactUploadUrl>`_ **Request Syntax** response
        = client.create_artifact_upload_url( requestContext={ 'jobMetadata': { 'jobId':
        'string', ...

        [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/1.42.95/reference/services/awstransformagenticservice.html#Elasticgumbyagenticservice.Client.create_artifact_upload_url)
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
        category: CategoryType = None
    ) -> CreateHitlTaskResponseTypeDef:
        """
        See also: `AWS API Documentation <https://docs.aws.amazon.com/goto/WebAPI/elasti
        cgumbyagentic-2018-05-10/CreateHitlTask>`_ **Request Syntax** response =
        client.create_hitl_task( requestContext={ 'jobMetadata': { 'jobId': 'string',
        'workspaceId':...

        [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/1.42.95/reference/services/awstransformagenticservice.html#Elasticgumbyagenticservice.Client.create_hitl_task)
        [Show boto3-stubs documentation](https://vemel.github.io/boto3_stubs_docs/agent_builder_types/client.html#create_hitl_task)
        """

    def create_skill_download_url(
        self,
        *,
        requestContext: "RequestContextTypeDef",
        skillName: str,
        idempotencyToken: str = None,
        version: str = None
    ) -> CreateSkillDownloadUrlResponseTypeDef:
        """
        See also: `AWS API Documentation <https://docs.aws.amazon.com/goto/WebAPI/elasti
        cgumbyagentic-2018-05-10/CreateSkillDownloadUrl>`_ **Request Syntax** response =
        client.create_skill_download_url( requestContext={ 'jobMetadata': { 'jobId':
        'string', ...

        [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/1.42.95/reference/services/awstransformagenticservice.html#Elasticgumbyagenticservice.Client.create_skill_download_url)
        [Show boto3-stubs documentation](https://vemel.github.io/boto3_stubs_docs/agent_builder_types/client.html#create_skill_download_url)
        """

    def create_worklog(
        self,
        *,
        requestContext: "RequestContextTypeDef",
        worklog: "WorklogTypeDef",
        idempotencyToken: str = None
    ) -> Dict[str, Any]:
        """
        See also: `AWS API Documentation <https://docs.aws.amazon.com/goto/WebAPI/elasti
        cgumbyagentic-2018-05-10/CreateWorklog>`_ **Request Syntax** response =
        client.create_worklog( requestContext={ 'jobMetadata': { 'jobId': 'string',
        'workspaceId': 's...

        [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/1.42.95/reference/services/awstransformagenticservice.html#Elasticgumbyagenticservice.Client.create_worklog)
        [Show boto3-stubs documentation](https://vemel.github.io/boto3_stubs_docs/agent_builder_types/client.html#create_worklog)
        """

    def delete_job_plan_step(
        self, *, requestContext: "RequestContextTypeDef", stepId: str, idempotencyToken: str = None
    ) -> Dict[str, Any]:
        """
        See also: `AWS API Documentation <https://docs.aws.amazon.com/goto/WebAPI/elasti
        cgumbyagentic-2018-05-10/DeleteJobPlanStep>`_ **Request Syntax** response =
        client.delete_job_plan_step( requestContext={ 'jobMetadata': { 'jobId':
        'string', 'worksp...

        [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/1.42.95/reference/services/awstransformagenticservice.html#Elasticgumbyagenticservice.Client.delete_job_plan_step)
        [Show boto3-stubs documentation](https://vemel.github.io/boto3_stubs_docs/agent_builder_types/client.html#delete_job_plan_step)
        """

    def deregister_knowledge_base_document(
        self,
        *,
        requestContext: "RequestContextTypeDef",
        artifactId: str,
        knowledgeBaseConfigType: Literal["TEXT_TITAN_CONFIG"]
    ) -> Dict[str, Any]:
        """
        See also: `AWS API Documentation <https://docs.aws.amazon.com/goto/WebAPI/elasti
        cgumbyagentic-2018-05-10/DeregisterKnowledgeBaseDocument>`_ **Request Syntax**
        response = client.deregister_knowledge_base_document( requestContext={
        'jobMetadata': { 'jobId': 'st...

        [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/1.42.95/reference/services/awstransformagenticservice.html#Elasticgumbyagenticservice.Client.deregister_knowledge_base_document)
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

        [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/1.42.95/reference/services/awstransformagenticservice.html#Elasticgumbyagenticservice.Client.generate_presigned_url)
        [Show boto3-stubs documentation](https://vemel.github.io/boto3_stubs_docs/agent_builder_types/client.html#generate_presigned_url)
        """

    def get_agent_instance(
        self, *, requestContext: "RequestContextTypeDef", agentInstanceId: str
    ) -> GetAgentInstanceResponseTypeDef:
        """
        See also: `AWS API Documentation <https://docs.aws.amazon.com/goto/WebAPI/elasti
        cgumbyagentic-2018-05-10/GetAgentInstance>`_ **Request Syntax** response =
        client.get_agent_instance( requestContext={ 'jobMetadata': { 'jobId': 'string',
        'workspace...

        [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/1.42.95/reference/services/awstransformagenticservice.html#Elasticgumbyagenticservice.Client.get_agent_instance)
        [Show boto3-stubs documentation](https://vemel.github.io/boto3_stubs_docs/agent_builder_types/client.html#get_agent_instance)
        """

    def get_agent_version(
        self, *, requestContext: "RequestContextTypeDef", name: str, version: str = None
    ) -> GetAgentVersionResponseTypeDef:
        """
        See also: `AWS API Documentation <https://docs.aws.amazon.com/goto/WebAPI/elasti
        cgumbyagentic-2018-05-10/GetAgentVersion>`_ **Request Syntax** response =
        client.get_agent_version( requestContext={ 'jobMetadata': { 'jobId': 'string',
        'workspaceId...

        [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/1.42.95/reference/services/awstransformagenticservice.html#Elasticgumbyagenticservice.Client.get_agent_version)
        [Show boto3-stubs documentation](https://vemel.github.io/boto3_stubs_docs/agent_builder_types/client.html#get_agent_version)
        """

    def get_artifact_metadata(
        self, *, requestContext: "RequestContextTypeDef", artifactId: str
    ) -> GetArtifactMetadataResponseTypeDef:
        """
        See also: `AWS API Documentation <https://docs.aws.amazon.com/goto/WebAPI/elasti
        cgumbyagentic-2018-05-10/GetArtifactMetadata>`_ **Request Syntax** response =
        client.get_artifact_metadata( requestContext={ 'jobMetadata': { 'jobId':
        'string', 'wor...

        [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/1.42.95/reference/services/awstransformagenticservice.html#Elasticgumbyagenticservice.Client.get_artifact_metadata)
        [Show boto3-stubs documentation](https://vemel.github.io/boto3_stubs_docs/agent_builder_types/client.html#get_artifact_metadata)
        """

    def get_connector(
        self, *, requestContext: "RequestContextTypeDef", connectorId: str
    ) -> GetConnectorResponseTypeDef:
        """
        See also: `AWS API Documentation <https://docs.aws.amazon.com/goto/WebAPI/elasti
        cgumbyagentic-2018-05-10/GetConnector>`_ **Request Syntax** response =
        client.get_connector( requestContext={ 'jobMetadata': { 'jobId': 'string',
        'workspaceId': 'str...

        [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/1.42.95/reference/services/awstransformagenticservice.html#Elasticgumbyagenticservice.Client.get_connector)
        [Show boto3-stubs documentation](https://vemel.github.io/boto3_stubs_docs/agent_builder_types/client.html#get_connector)
        """

    def get_hitl_task(
        self, *, requestContext: "RequestContextTypeDef", hitlTaskId: str
    ) -> GetHitlTaskResponseTypeDef:
        """
        See also: `AWS API Documentation <https://docs.aws.amazon.com/goto/WebAPI/elasti
        cgumbyagentic-2018-05-10/GetHitlTask>`_ **Request Syntax** response =
        client.get_hitl_task( requestContext={ 'jobMetadata': { 'jobId': 'string',
        'workspaceId': 'stri...

        [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/1.42.95/reference/services/awstransformagenticservice.html#Elasticgumbyagenticservice.Client.get_hitl_task)
        [Show boto3-stubs documentation](https://vemel.github.io/boto3_stubs_docs/agent_builder_types/client.html#get_hitl_task)
        """

    def get_job(
        self, *, requestContext: "RequestContextTypeDef", includeObjective: bool = None
    ) -> GetJobResponseTypeDef:
        """
        See also: `AWS API Documentation <https://docs.aws.amazon.com/goto/WebAPI/elasti
        cgumbyagentic-2018-05-10/GetJob>`_ **Request Syntax** response = client.get_job(
        requestContext={ 'jobMetadata': { 'jobId': 'string', 'workspaceId': 'string' ...

        [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/1.42.95/reference/services/awstransformagenticservice.html#Elasticgumbyagenticservice.Client.get_job)
        [Show boto3-stubs documentation](https://vemel.github.io/boto3_stubs_docs/agent_builder_types/client.html#get_job)
        """

    def get_knowledge_base_ingestion(
        self, *, requestContext: "RequestContextTypeDef", ingestionId: str
    ) -> GetKnowledgeBaseIngestionResponseTypeDef:
        """
        See also: `AWS API Documentation <https://docs.aws.amazon.com/goto/WebAPI/elasti
        cgumbyagentic-2018-05-10/GetKnowledgeBaseIngestion>`_ **Request Syntax**
        response = client.get_knowledge_base_ingestion( requestContext={ 'jobMetadata':
        { 'jobId': 'string', ...

        [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/1.42.95/reference/services/awstransformagenticservice.html#Elasticgumbyagenticservice.Client.get_knowledge_base_ingestion)
        [Show boto3-stubs documentation](https://vemel.github.io/boto3_stubs_docs/agent_builder_types/client.html#get_knowledge_base_ingestion)
        """

    def get_task(
        self,
        *,
        requestContext: "RequestContextTypeDef",
        agentInstanceId: str,
        params: Dict[str, Any] = None
    ) -> GetTaskResponseTypeDef:
        """
        See also: `AWS API Documentation <https://docs.aws.amazon.com/goto/WebAPI/elasti
        cgumbyagentic-2018-05-10/GetTask>`_ **Request Syntax** response =
        client.get_task( requestContext={ 'jobMetadata': { 'jobId': 'string',
        'workspaceId': 'string' ...

        [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/1.42.95/reference/services/awstransformagenticservice.html#Elasticgumbyagenticservice.Client.get_task)
        [Show boto3-stubs documentation](https://vemel.github.io/boto3_stubs_docs/agent_builder_types/client.html#get_task)
        """

    def get_temporary_credentials_for_connector(
        self, *, requestContext: "RequestContextTypeDef", connectorId: str, targetRegion: str = None
    ) -> GetTemporaryCredentialsForConnectorResponseTypeDef:
        """
        See also: `AWS API Documentation <https://docs.aws.amazon.com/goto/WebAPI/elasti
        cgumbyagentic-2018-05-10/GetTemporaryCredentialsForConnector>`_ **Request
        Syntax** response = client.get_temporary_credentials_for_connector(
        requestContext={ 'jobMetadata': { 'jo...

        [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/1.42.95/reference/services/awstransformagenticservice.html#Elasticgumbyagenticservice.Client.get_temporary_credentials_for_connector)
        [Show boto3-stubs documentation](https://vemel.github.io/boto3_stubs_docs/agent_builder_types/client.html#get_temporary_credentials_for_connector)
        """

    def get_temporary_credentials_for_role(
        self, *, requestContext: "RequestContextTypeDef", hitlTaskId: str
    ) -> GetTemporaryCredentialsForRoleResponseTypeDef:
        """
        See also: `AWS API Documentation <https://docs.aws.amazon.com/goto/WebAPI/elasti
        cgumbyagentic-2018-05-10/GetTemporaryCredentialsForRole>`_ **Request Syntax**
        response = client.get_temporary_credentials_for_role( requestContext={
        'jobMetadata': { 'jobId': 'str...

        [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/1.42.95/reference/services/awstransformagenticservice.html#Elasticgumbyagenticservice.Client.get_temporary_credentials_for_role)
        [Show boto3-stubs documentation](https://vemel.github.io/boto3_stubs_docs/agent_builder_types/client.html#get_temporary_credentials_for_role)
        """

    def get_usage(
        self, *, requestContext: "RequestContextTypeDef", resourceTypes: List[ResourceTypeType]
    ) -> GetUsageResponseTypeDef:
        """
        See also: `AWS API Documentation <https://docs.aws.amazon.com/goto/WebAPI/elasti
        cgumbyagentic-2018-05-10/GetUsage>`_ **Request Syntax** response =
        client.get_usage( requestContext={ 'jobMetadata': { 'jobId': 'string',
        'workspaceId': 'string' ...

        [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/1.42.95/reference/services/awstransformagenticservice.html#Elasticgumbyagenticservice.Client.get_usage)
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
        agentType: AgentTypeType = None
    ) -> InvokeAgentResponseTypeDef:
        """
        See also: `AWS API Documentation <https://docs.aws.amazon.com/goto/WebAPI/elasti
        cgumbyagentic-2018-05-10/InvokeAgent>`_ **Request Syntax** response =
        client.invoke_agent( requestContext={ 'jobMetadata': { 'jobId': 'string',
        'workspaceId': 'strin...

        [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/1.42.95/reference/services/awstransformagenticservice.html#Elasticgumbyagenticservice.Client.invoke_agent)
        [Show boto3-stubs documentation](https://vemel.github.io/boto3_stubs_docs/agent_builder_types/client.html#invoke_agent)
        """

    def list_agent_instances(
        self,
        *,
        requestContext: "RequestContextTypeDef",
        nextToken: str = None,
        agentFilter: "ListAgentFilterTypeDef" = None,
        maxResults: int = None
    ) -> ListAgentInstancesResponseTypeDef:
        """
        See also: `AWS API Documentation <https://docs.aws.amazon.com/goto/WebAPI/elasti
        cgumbyagentic-2018-05-10/ListAgentInstances>`_ **Request Syntax** response =
        client.list_agent_instances( requestContext={ 'jobMetadata': { 'jobId':
        'string', 'works...

        [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/1.42.95/reference/services/awstransformagenticservice.html#Elasticgumbyagenticservice.Client.list_agent_instances)
        [Show boto3-stubs documentation](https://vemel.github.io/boto3_stubs_docs/agent_builder_types/client.html#list_agent_instances)
        """

    def list_agents(
        self,
        *,
        requestContext: "RequestContextTypeDef",
        agentFilter: "ListAgentsFilterTypeDef" = None,
        nextToken: str = None,
        maxResults: int = None
    ) -> ListAgentsResponseTypeDef:
        """
        See also: `AWS API Documentation <https://docs.aws.amazon.com/goto/WebAPI/elasti
        cgumbyagentic-2018-05-10/ListAgents>`_ **Request Syntax** response =
        client.list_agents( requestContext={ 'jobMetadata': { 'jobId': 'string',
        'workspaceId': 'string'...

        [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/1.42.95/reference/services/awstransformagenticservice.html#Elasticgumbyagenticservice.Client.list_agents)
        [Show boto3-stubs documentation](https://vemel.github.io/boto3_stubs_docs/agent_builder_types/client.html#list_agents)
        """

    def list_artifacts(
        self,
        *,
        requestContext: "RequestContextTypeDef",
        artifactFilter: "ArtifactFilterTypeDef" = None,
        nextToken: str = None,
        pathPrefix: str = None,
        maxResults: int = None
    ) -> ListArtifactsResponseTypeDef:
        """
        See also: `AWS API Documentation <https://docs.aws.amazon.com/goto/WebAPI/elasti
        cgumbyagentic-2018-05-10/ListArtifacts>`_ **Request Syntax** response =
        client.list_artifacts( requestContext={ 'jobMetadata': { 'jobId': 'string',
        'workspaceId': 's...

        [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/1.42.95/reference/services/awstransformagenticservice.html#Elasticgumbyagenticservice.Client.list_artifacts)
        [Show boto3-stubs documentation](https://vemel.github.io/boto3_stubs_docs/agent_builder_types/client.html#list_artifacts)
        """

    def list_connectors(
        self,
        *,
        requestContext: "RequestContextTypeDef",
        maxResults: int = None,
        nextToken: str = None
    ) -> ListConnectorsResponseTypeDef:
        """
        See also: `AWS API Documentation <https://docs.aws.amazon.com/goto/WebAPI/elasti
        cgumbyagentic-2018-05-10/ListConnectors>`_ **Request Syntax** response =
        client.list_connectors( requestContext={ 'jobMetadata': { 'jobId': 'string',
        'workspaceId': ...

        [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/1.42.95/reference/services/awstransformagenticservice.html#Elasticgumbyagenticservice.Client.list_connectors)
        [Show boto3-stubs documentation](https://vemel.github.io/boto3_stubs_docs/agent_builder_types/client.html#list_connectors)
        """

    def list_hitl_tasks(
        self,
        *,
        requestContext: "RequestContextTypeDef",
        taskType: HitlTaskTypeType,
        taskFilter: "HitlTaskFilterTypeDef" = None,
        nextToken: str = None,
        maxResults: int = None
    ) -> ListHitlTasksResponseTypeDef:
        """
        See also: `AWS API Documentation <https://docs.aws.amazon.com/goto/WebAPI/elasti
        cgumbyagentic-2018-05-10/ListHitlTasks>`_ **Request Syntax** response =
        client.list_hitl_tasks( requestContext={ 'jobMetadata': { 'jobId': 'string',
        'workspaceId': '...

        [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/1.42.95/reference/services/awstransformagenticservice.html#Elasticgumbyagenticservice.Client.list_hitl_tasks)
        [Show boto3-stubs documentation](https://vemel.github.io/boto3_stubs_docs/agent_builder_types/client.html#list_hitl_tasks)
        """

    def list_job_plan_steps(
        self,
        *,
        requestContext: "RequestContextTypeDef",
        parentStepId: str = None,
        maxResults: int = None,
        nextToken: str = None
    ) -> ListJobPlanStepsResponseTypeDef:
        """
        See also: `AWS API Documentation <https://docs.aws.amazon.com/goto/WebAPI/elasti
        cgumbyagentic-2018-05-10/ListJobPlanSteps>`_ **Request Syntax** response =
        client.list_job_plan_steps( requestContext={ 'jobMetadata': { 'jobId': 'string',
        'workspac...

        [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/1.42.95/reference/services/awstransformagenticservice.html#Elasticgumbyagenticservice.Client.list_job_plan_steps)
        [Show boto3-stubs documentation](https://vemel.github.io/boto3_stubs_docs/agent_builder_types/client.html#list_job_plan_steps)
        """

    def list_worklogs(
        self,
        *,
        requestContext: "RequestContextTypeDef",
        worklogFilter: "WorklogFilterTypeDef" = None,
        nextToken: str = None
    ) -> ListWorklogsResponseTypeDef:
        """
        See also: `AWS API Documentation <https://docs.aws.amazon.com/goto/WebAPI/elasti
        cgumbyagentic-2018-05-10/ListWorklogs>`_ **Request Syntax** response =
        client.list_worklogs( requestContext={ 'jobMetadata': { 'jobId': 'string',
        'workspaceId': 'str...

        [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/1.42.95/reference/services/awstransformagenticservice.html#Elasticgumbyagenticservice.Client.list_worklogs)
        [Show boto3-stubs documentation](https://vemel.github.io/boto3_stubs_docs/agent_builder_types/client.html#list_worklogs)
        """

    def pre_prod_test_operation(self, *, requestContext: "RequestContextTypeDef") -> Dict[str, Any]:
        """
        See also: `AWS API Documentation <https://docs.aws.amazon.com/goto/WebAPI/elasti
        cgumbyagentic-2018-05-10/PreProdTestOperation>`_ **Request Syntax** response =
        client.pre_prod_test_operation( requestContext={ 'jobMetadata': { 'jobId':
        'string', '...

        [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/1.42.95/reference/services/awstransformagenticservice.html#Elasticgumbyagenticservice.Client.pre_prod_test_operation)
        [Show boto3-stubs documentation](https://vemel.github.io/boto3_stubs_docs/agent_builder_types/client.html#pre_prod_test_operation)
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
        attributes: List["MeteringAttributeTypeDef"] = None
    ) -> Dict[str, Any]:
        """
        See also: `AWS API Documentation <https://docs.aws.amazon.com/goto/WebAPI/elasti
        cgumbyagentic-2018-05-10/PublishMeteringEvent>`_ **Request Syntax** response =
        client.publish_metering_event( requestContext={ 'jobMetadata': { 'jobId':
        'string', 'w...

        [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/1.42.95/reference/services/awstransformagenticservice.html#Elasticgumbyagenticservice.Client.publish_metering_event)
        [Show boto3-stubs documentation](https://vemel.github.io/boto3_stubs_docs/agent_builder_types/client.html#publish_metering_event)
        """

    def put_job_plan(
        self,
        *,
        requestContext: "RequestContextTypeDef",
        plan: "JobPlanTreeTypeDef",
        mode: "PutJobPlanModeTypeDef",
        idempotencyToken: str = None
    ) -> PutJobPlanResponseTypeDef:
        """
        See also: `AWS API Documentation <https://docs.aws.amazon.com/goto/WebAPI/elasti
        cgumbyagentic-2018-05-10/PutJobPlan>`_ **Request Syntax** response =
        client.put_job_plan( requestContext={ 'jobMetadata': { 'jobId': 'string',
        'workspaceId': 'string...

        [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/1.42.95/reference/services/awstransformagenticservice.html#Elasticgumbyagenticservice.Client.put_job_plan)
        [Show boto3-stubs documentation](https://vemel.github.io/boto3_stubs_docs/agent_builder_types/client.html#put_job_plan)
        """

    def refresh_auth_token(
        self, *, requestContext: "RequestContextTypeDef", sessionDuration: int
    ) -> RefreshAuthTokenResponseTypeDef:
        """
        See also: `AWS API Documentation <https://docs.aws.amazon.com/goto/WebAPI/elasti
        cgumbyagentic-2018-05-10/RefreshAuthToken>`_ **Request Syntax** response =
        client.refresh_auth_token( requestContext={ 'jobMetadata': { 'jobId': 'string',
        'workspace...

        [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/1.42.95/reference/services/awstransformagenticservice.html#Elasticgumbyagenticservice.Client.refresh_auth_token)
        [Show boto3-stubs documentation](https://vemel.github.io/boto3_stubs_docs/agent_builder_types/client.html#refresh_auth_token)
        """

    def register_knowledge_base_document(
        self,
        *,
        requestContext: "RequestContextTypeDef",
        artifactId: str,
        knowledgeBaseConfigType: Literal["TEXT_TITAN_CONFIG"],
        indexingMetadata: Dict[str, str] = None
    ) -> Dict[str, Any]:
        """
        See also: `AWS API Documentation <https://docs.aws.amazon.com/goto/WebAPI/elasti
        cgumbyagentic-2018-05-10/RegisterKnowledgeBaseDocument>`_ **Request Syntax**
        response = client.register_knowledge_base_document( requestContext={
        'jobMetadata': { 'jobId': 'string...

        [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/1.42.95/reference/services/awstransformagenticservice.html#Elasticgumbyagenticservice.Client.register_knowledge_base_document)
        [Show boto3-stubs documentation](https://vemel.github.io/boto3_stubs_docs/agent_builder_types/client.html#register_knowledge_base_document)
        """

    def retrieve_from_knowledge_base(
        self,
        *,
        requestContext: "RequestContextTypeDef",
        retrievalQuery: "RetrievalQueryTypeDef",
        retrievalScope: RetrievalScopeType,
        retrievalConfiguration: "RetrievalConfigurationTypeDef" = None,
        nextToken: str = None
    ) -> RetrieveFromKnowledgeBaseResponseTypeDef:
        """
        See also: `AWS API Documentation <https://docs.aws.amazon.com/goto/WebAPI/elasti
        cgumbyagentic-2018-05-10/RetrieveFromKnowledgeBase>`_ **Request Syntax**
        response = client.retrieve_from_knowledge_base( requestContext={ 'jobMetadata':
        { 'jobId': 'string', ...

        [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/1.42.95/reference/services/awstransformagenticservice.html#Elasticgumbyagenticservice.Client.retrieve_from_knowledge_base)
        [Show boto3-stubs documentation](https://vemel.github.io/boto3_stubs_docs/agent_builder_types/client.html#retrieve_from_knowledge_base)
        """

    def rollback_metering_event(
        self,
        *,
        requestContext: "RequestContextTypeDef",
        entity: "EntityTypeDef",
        resourceType: ResourceTypeType,
        resourceId: str,
        amendTime: Union[datetime, str]
    ) -> Dict[str, Any]:
        """
        See also: `AWS API Documentation <https://docs.aws.amazon.com/goto/WebAPI/elasti
        cgumbyagentic-2018-05-10/RollbackMeteringEvent>`_ **Request Syntax** response =
        client.rollback_metering_event( requestContext={ 'jobMetadata': { 'jobId':
        'string', ...

        [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/1.42.95/reference/services/awstransformagenticservice.html#Elasticgumbyagenticservice.Client.rollback_metering_event)
        [Show boto3-stubs documentation](https://vemel.github.io/boto3_stubs_docs/agent_builder_types/client.html#rollback_metering_event)
        """

    def send_message(
        self,
        *,
        requestContext: "RequestContextTypeDef",
        agentInstanceId: str,
        params: Dict[str, Any] = None
    ) -> SendMessageResponseTypeDef:
        """
        See also: `AWS API Documentation <https://docs.aws.amazon.com/goto/WebAPI/elasti
        cgumbyagentic-2018-05-10/SendMessage>`_ **Request Syntax** response =
        client.send_message( requestContext={ 'jobMetadata': { 'jobId': 'string',
        'workspaceId': 'strin...

        [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/1.42.95/reference/services/awstransformagenticservice.html#Elasticgumbyagenticservice.Client.send_message)
        [Show boto3-stubs documentation](https://vemel.github.io/boto3_stubs_docs/agent_builder_types/client.html#send_message)
        """

    def start_hitl_task(
        self,
        *,
        requestContext: "RequestContextTypeDef",
        hitlTaskId: str,
        firstInChain: bool = None,
        idempotencyToken: str = None
    ) -> StartHitlTaskResponseTypeDef:
        """
        See also: `AWS API Documentation <https://docs.aws.amazon.com/goto/WebAPI/elasti
        cgumbyagentic-2018-05-10/StartHitlTask>`_ **Request Syntax** response =
        client.start_hitl_task( requestContext={ 'jobMetadata': { 'jobId': 'string',
        'workspaceId': '...

        [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/1.42.95/reference/services/awstransformagenticservice.html#Elasticgumbyagenticservice.Client.start_hitl_task)
        [Show boto3-stubs documentation](https://vemel.github.io/boto3_stubs_docs/agent_builder_types/client.html#start_hitl_task)
        """

    def start_job(
        self, *, requestContext: "RequestContextTypeDef", idempotencyToken: str = None
    ) -> StartJobResponseTypeDef:
        """
        See also: `AWS API Documentation <https://docs.aws.amazon.com/goto/WebAPI/elasti
        cgumbyagentic-2018-05-10/StartJob>`_ **Request Syntax** response =
        client.start_job( requestContext={ 'jobMetadata': { 'jobId': 'string',
        'workspaceId': 'string' ...

        [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/1.42.95/reference/services/awstransformagenticservice.html#Elasticgumbyagenticservice.Client.start_job)
        [Show boto3-stubs documentation](https://vemel.github.io/boto3_stubs_docs/agent_builder_types/client.html#start_job)
        """

    def start_knowledge_base_ingestion(
        self,
        *,
        requestContext: "RequestContextTypeDef",
        knowledgeBaseConfigType: Literal["TEXT_TITAN_CONFIG"],
        ingestionScopeMetadata: "IngestionScopeMetadataTypeDef",
        ingestionConfiguration: "IngestionConfigurationTypeDef" = None
    ) -> StartKnowledgeBaseIngestionResponseTypeDef:
        """
        See also: `AWS API Documentation <https://docs.aws.amazon.com/goto/WebAPI/elasti
        cgumbyagentic-2018-05-10/StartKnowledgeBaseIngestion>`_ **Request Syntax**
        response = client.start_knowledge_base_ingestion( requestContext={
        'jobMetadata': { 'jobId': 'string', ...

        [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/1.42.95/reference/services/awstransformagenticservice.html#Elasticgumbyagenticservice.Client.start_knowledge_base_ingestion)
        [Show boto3-stubs documentation](https://vemel.github.io/boto3_stubs_docs/agent_builder_types/client.html#start_knowledge_base_ingestion)
        """

    def stop_agent(
        self,
        *,
        requestContext: "RequestContextTypeDef",
        agentInstanceId: str,
        idempotencyToken: str = None
    ) -> Dict[str, Any]:
        """
        See also: `AWS API Documentation <https://docs.aws.amazon.com/goto/WebAPI/elasti
        cgumbyagentic-2018-05-10/StopAgent>`_ **Request Syntax** response =
        client.stop_agent( requestContext={ 'jobMetadata': { 'jobId': 'string',
        'workspaceId': 'string' ...

        [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/1.42.95/reference/services/awstransformagenticservice.html#Elasticgumbyagenticservice.Client.stop_agent)
        [Show boto3-stubs documentation](https://vemel.github.io/boto3_stubs_docs/agent_builder_types/client.html#stop_agent)
        """

    def test_operation(self, *, requestContext: "RequestContextTypeDef") -> Dict[str, Any]:
        """
        See also: `AWS API Documentation <https://docs.aws.amazon.com/goto/WebAPI/elasti
        cgumbyagentic-2018-05-10/TestOperation>`_ **Request Syntax** response =
        client.test_operation( requestContext={ 'jobMetadata': { 'jobId': 'string',
        'workspaceId': 's...

        [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/1.42.95/reference/services/awstransformagenticservice.html#Elasticgumbyagenticservice.Client.test_operation)
        [Show boto3-stubs documentation](https://vemel.github.io/boto3_stubs_docs/agent_builder_types/client.html#test_operation)
        """

    def update_agent_instance(
        self,
        *,
        requestContext: "RequestContextTypeDef",
        agentInstanceId: str,
        agentInstanceStatus: UpdateAgentInstanceStatusType,
        agentInstanceStatusReason: str = None,
        agentOutput: "AgentOutputPayloadTypeDef" = None
    ) -> Dict[str, Any]:
        """
        See also: `AWS API Documentation <https://docs.aws.amazon.com/goto/WebAPI/elasti
        cgumbyagentic-2018-05-10/UpdateAgentInstance>`_ **Request Syntax** response =
        client.update_agent_instance( requestContext={ 'jobMetadata': { 'jobId':
        'string', 'wor...

        [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/1.42.95/reference/services/awstransformagenticservice.html#Elasticgumbyagenticservice.Client.update_agent_instance)
        [Show boto3-stubs documentation](https://vemel.github.io/boto3_stubs_docs/agent_builder_types/client.html#update_agent_instance)
        """

    def update_job_plan_step(
        self,
        *,
        requestContext: "RequestContextTypeDef",
        planStep: "PlanStepUpdateTypeDef",
        idempotencyToken: str = None
    ) -> Dict[str, Any]:
        """
        See also: `AWS API Documentation <https://docs.aws.amazon.com/goto/WebAPI/elasti
        cgumbyagentic-2018-05-10/UpdateJobPlanStep>`_ **Request Syntax** response =
        client.update_job_plan_step( requestContext={ 'jobMetadata': { 'jobId':
        'string', 'worksp...

        [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/1.42.95/reference/services/awstransformagenticservice.html#Elasticgumbyagenticservice.Client.update_job_plan_step)
        [Show boto3-stubs documentation](https://vemel.github.io/boto3_stubs_docs/agent_builder_types/client.html#update_job_plan_step)
        """

    def update_job_status(
        self,
        *,
        requestContext: "RequestContextTypeDef",
        status: JobStatusType = None,
        statusInfo: "StatusInfoTypeDef" = None,
        idempotencyToken: str = None,
        notificationArtifactId: str = None
    ) -> Dict[str, Any]:
        """
        See also: `AWS API Documentation <https://docs.aws.amazon.com/goto/WebAPI/elasti
        cgumbyagentic-2018-05-10/UpdateJobStatus>`_ **Request Syntax** response =
        client.update_job_status( requestContext={ 'jobMetadata': { 'jobId': 'string',
        'workspaceId...

        [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/1.42.95/reference/services/awstransformagenticservice.html#Elasticgumbyagenticservice.Client.update_job_status)
        [Show boto3-stubs documentation](https://vemel.github.io/boto3_stubs_docs/agent_builder_types/client.html#update_job_status)
        """

    @overload
    def get_paginator(
        self, operation_name: Literal["list_agent_instances"]
    ) -> ListAgentInstancesPaginator:
        """
        [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/1.42.95/reference/services/awstransformagenticservice.html#Elasticgumbyagenticservice.Paginator.ListAgentInstances)
        [Show boto3-stubs documentation](https://vemel.github.io/boto3_stubs_docs/agent_builder_types/paginators.html#listagentinstancespaginator)
        """

    @overload
    def get_paginator(self, operation_name: Literal["list_artifacts"]) -> ListArtifactsPaginator:
        """
        [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/1.42.95/reference/services/awstransformagenticservice.html#Elasticgumbyagenticservice.Paginator.ListArtifacts)
        [Show boto3-stubs documentation](https://vemel.github.io/boto3_stubs_docs/agent_builder_types/paginators.html#listartifactspaginator)
        """

    @overload
    def get_paginator(self, operation_name: Literal["list_hitl_tasks"]) -> ListHitlTasksPaginator:
        """
        [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/1.42.95/reference/services/awstransformagenticservice.html#Elasticgumbyagenticservice.Paginator.ListHitlTasks)
        [Show boto3-stubs documentation](https://vemel.github.io/boto3_stubs_docs/agent_builder_types/paginators.html#listhitltaskspaginator)
        """

    @overload
    def get_paginator(
        self, operation_name: Literal["list_job_plan_steps"]
    ) -> ListJobPlanStepsPaginator:
        """
        [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/1.42.95/reference/services/awstransformagenticservice.html#Elasticgumbyagenticservice.Paginator.ListJobPlanSteps)
        [Show boto3-stubs documentation](https://vemel.github.io/boto3_stubs_docs/agent_builder_types/paginators.html#listjobplanstepspaginator)
        """
