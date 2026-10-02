# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Type annotations for transformagenticservice service client paginators.

[Open documentation](https://youtype.github.io/boto3_stubs_docs/agent_builder_types/paginators/)

Usage::

    ```python
    from boto3.session import Session

    from agent_builder_types.client import TransformAgenticServiceClient
    from agent_builder_types.paginator import (
        ListAgentInstancesPaginator,
        ListArtifactsPaginator,
        ListHitlTasksPaginator,
        ListJobPlanStepsPaginator,
    )

    session = Session()
    client: TransformAgenticServiceClient = session.client("transformagenticservice")

    list_agent_instances_paginator: ListAgentInstancesPaginator = client.get_paginator("list_agent_instances")
    list_artifacts_paginator: ListArtifactsPaginator = client.get_paginator("list_artifacts")
    list_hitl_tasks_paginator: ListHitlTasksPaginator = client.get_paginator("list_hitl_tasks")
    list_job_plan_steps_paginator: ListJobPlanStepsPaginator = client.get_paginator("list_job_plan_steps")
    ```
"""

from typing import Generic, Iterator, TypeVar

from botocore.paginate import PageIterator, Paginator

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

_ItemTypeDef = TypeVar("_ItemTypeDef")

class _PageIterator(Generic[_ItemTypeDef], PageIterator):
    def __iter__(self) -> Iterator[_ItemTypeDef]:
        """
        Proxy method to specify iterator item type.
        """

class ListAgentInstancesPaginator(Paginator):
    """
    [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/transformagenticservice.html#TransformAgenticService.Paginator.ListAgentInstances)
    [Show boto3-stubs documentation](https://youtype.github.io/boto3_stubs_docs/agent_builder_types/paginators/#listagentinstancespaginator)
    """

    def paginate(
        self,
        *,
        requestContext: RequestContextTypeDef,
        agentFilter: ListAgentFilterTypeDef = ...,
        PaginationConfig: PaginatorConfigTypeDef = ...,
    ) -> _PageIterator[ListAgentInstancesResponseTypeDef]:
        """
        [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/transformagenticservice.html#TransformAgenticService.Paginator.ListAgentInstances.paginate)
        [Show boto3-stubs documentation](https://youtype.github.io/boto3_stubs_docs/agent_builder_types/paginators/#listagentinstancespaginator)
        """

class ListArtifactsPaginator(Paginator):
    """
    [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/transformagenticservice.html#TransformAgenticService.Paginator.ListArtifacts)
    [Show boto3-stubs documentation](https://youtype.github.io/boto3_stubs_docs/agent_builder_types/paginators/#listartifactspaginator)
    """

    def paginate(
        self,
        *,
        requestContext: RequestContextTypeDef,
        artifactFilter: ArtifactFilterTypeDef = ...,
        pathPrefix: str = ...,
        PaginationConfig: PaginatorConfigTypeDef = ...,
    ) -> _PageIterator[ListArtifactsResponseTypeDef]:
        """
        [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/transformagenticservice.html#TransformAgenticService.Paginator.ListArtifacts.paginate)
        [Show boto3-stubs documentation](https://youtype.github.io/boto3_stubs_docs/agent_builder_types/paginators/#listartifactspaginator)
        """

class ListHitlTasksPaginator(Paginator):
    """
    [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/transformagenticservice.html#TransformAgenticService.Paginator.ListHitlTasks)
    [Show boto3-stubs documentation](https://youtype.github.io/boto3_stubs_docs/agent_builder_types/paginators/#listhitltaskspaginator)
    """

    def paginate(
        self,
        *,
        requestContext: RequestContextTypeDef,
        taskType: HitlTaskTypeType,
        taskFilter: HitlTaskFilterTypeDef = ...,
        PaginationConfig: PaginatorConfigTypeDef = ...,
    ) -> _PageIterator[ListHitlTasksResponseTypeDef]:
        """
        [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/transformagenticservice.html#TransformAgenticService.Paginator.ListHitlTasks.paginate)
        [Show boto3-stubs documentation](https://youtype.github.io/boto3_stubs_docs/agent_builder_types/paginators/#listhitltaskspaginator)
        """

class ListJobPlanStepsPaginator(Paginator):
    """
    [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/transformagenticservice.html#TransformAgenticService.Paginator.ListJobPlanSteps)
    [Show boto3-stubs documentation](https://youtype.github.io/boto3_stubs_docs/agent_builder_types/paginators/#listjobplanstepspaginator)
    """

    def paginate(
        self,
        *,
        requestContext: RequestContextTypeDef,
        parentStepId: str = ...,
        PaginationConfig: PaginatorConfigTypeDef = ...,
    ) -> _PageIterator[ListJobPlanStepsResponseTypeDef]:
        """
        [Show boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/transformagenticservice.html#TransformAgenticService.Paginator.ListJobPlanSteps.paginate)
        [Show boto3-stubs documentation](https://youtype.github.io/boto3_stubs_docs/agent_builder_types/paginators/#listjobplanstepspaginator)
        """
