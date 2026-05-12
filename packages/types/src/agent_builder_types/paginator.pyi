"""
Type annotations for AWS Transform Agentic service client paginators.

[Open documentation](https://vemel.github.io/boto3_stubs_docs/agent_builder_types/paginators.html)

Usage::

    ```python
    import boto3

    from agent_builder_types import TransformAgenticServiceClient
    from agent_builder_types.paginator import (
        ListAgentInstancesPaginator,
        ListArtifactsPaginator,
        ListHitlTasksPaginator,
        ListJobPlanStepsPaginator,
    )

    client: TransformAgenticServiceClient = boto3.client("awstransformagenticservice")

    list_agent_instances_paginator: ListAgentInstancesPaginator = client.get_paginator("list_agent_instances")
    list_artifacts_paginator: ListArtifactsPaginator = client.get_paginator("list_artifacts")
    list_hitl_tasks_paginator: ListHitlTasksPaginator = client.get_paginator("list_hitl_tasks")
    list_job_plan_steps_paginator: ListJobPlanStepsPaginator = client.get_paginator("list_job_plan_steps")
    ```
"""

from typing import Iterator

from botocore.paginate import Paginator as Boto3Paginator

from .literals import HitlTaskTypeType
from .type_defs import (
    ArtifactFilterTypeDef,
    HitlTaskFilterTypeDef,
    ListAgentFilterTypeDef,
    ListAgentInstancesResponseTypeDef,
    ListArtifactsResponseTypeDef,
    ListHitlTasksResponseTypeDef,
    ListJobPlanStepsResponseTypeDef,
    PaginatorConfigTypeDef,
    RequestContextTypeDef,
)

__all__ = (
    "ListAgentInstancesPaginator",
    "ListArtifactsPaginator",
    "ListHitlTasksPaginator",
    "ListJobPlanStepsPaginator",
)

class ListAgentInstancesPaginator(Boto3Paginator):
    """
    [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/1.42.95/reference/services/awstransformagenticservice.html#Awstransformagenticservice.Paginator.ListAgentInstances)
    [Show boto3-stubs documentation](https://vemel.github.io/boto3_stubs_docs/agent_builder_types/paginators.html#listagentinstancespaginator)
    """

    def paginate(
        self,
        *,
        requestContext: "RequestContextTypeDef",
        agentFilter: "ListAgentFilterTypeDef" = None,
        PaginationConfig: PaginatorConfigTypeDef = None
    ) -> Iterator[ListAgentInstancesResponseTypeDef]:
        """
        [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/1.42.95/reference/services/awstransformagenticservice.html#Awstransformagenticservice.Paginator.ListAgentInstances.paginate)
        [Show boto3-stubs documentation](https://vemel.github.io/boto3_stubs_docs/agent_builder_types/paginators.html#listagentinstancespaginator)
        """

class ListArtifactsPaginator(Boto3Paginator):
    """
    [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/1.42.95/reference/services/awstransformagenticservice.html#Awstransformagenticservice.Paginator.ListArtifacts)
    [Show boto3-stubs documentation](https://vemel.github.io/boto3_stubs_docs/agent_builder_types/paginators.html#listartifactspaginator)
    """

    def paginate(
        self,
        *,
        requestContext: "RequestContextTypeDef",
        artifactFilter: "ArtifactFilterTypeDef" = None,
        pathPrefix: str = None,
        PaginationConfig: PaginatorConfigTypeDef = None
    ) -> Iterator[ListArtifactsResponseTypeDef]:
        """
        [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/1.42.95/reference/services/awstransformagenticservice.html#Awstransformagenticservice.Paginator.ListArtifacts.paginate)
        [Show boto3-stubs documentation](https://vemel.github.io/boto3_stubs_docs/agent_builder_types/paginators.html#listartifactspaginator)
        """

class ListHitlTasksPaginator(Boto3Paginator):
    """
    [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/1.42.95/reference/services/awstransformagenticservice.html#Awstransformagenticservice.Paginator.ListHitlTasks)
    [Show boto3-stubs documentation](https://vemel.github.io/boto3_stubs_docs/agent_builder_types/paginators.html#listhitltaskspaginator)
    """

    def paginate(
        self,
        *,
        requestContext: "RequestContextTypeDef",
        taskType: HitlTaskTypeType,
        taskFilter: "HitlTaskFilterTypeDef" = None,
        PaginationConfig: PaginatorConfigTypeDef = None
    ) -> Iterator[ListHitlTasksResponseTypeDef]:
        """
        [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/1.42.95/reference/services/awstransformagenticservice.html#Awstransformagenticservice.Paginator.ListHitlTasks.paginate)
        [Show boto3-stubs documentation](https://vemel.github.io/boto3_stubs_docs/agent_builder_types/paginators.html#listhitltaskspaginator)
        """

class ListJobPlanStepsPaginator(Boto3Paginator):
    """
    [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/1.42.95/reference/services/awstransformagenticservice.html#Awstransformagenticservice.Paginator.ListJobPlanSteps)
    [Show boto3-stubs documentation](https://vemel.github.io/boto3_stubs_docs/agent_builder_types/paginators.html#listjobplanstepspaginator)
    """

    def paginate(
        self,
        *,
        requestContext: "RequestContextTypeDef",
        parentStepId: str = None,
        PaginationConfig: PaginatorConfigTypeDef = None
    ) -> Iterator[ListJobPlanStepsResponseTypeDef]:
        """
        [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/1.42.95/reference/services/awstransformagenticservice.html#Awstransformagenticservice.Paginator.ListJobPlanSteps.paginate)
        [Show boto3-stubs documentation](https://vemel.github.io/boto3_stubs_docs/agent_builder_types/paginators.html#listjobplanstepspaginator)
        """
