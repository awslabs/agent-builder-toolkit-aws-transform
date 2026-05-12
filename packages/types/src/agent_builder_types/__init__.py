# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Main interface for AWS Transform Agentic service.

Usage::

    ```python
    import boto3
    from agent_builder_types import (
        Client,
        TransformAgenticServiceClient,
        ListAgentInstancesPaginator,
        ListArtifactsPaginator,
        ListHitlTasksPaginator,
        ListJobPlanStepsPaginator,
    )

    session = boto3.Session()

    client: TransformAgenticServiceClient = boto3.client("awstransformagenticservice")
    session_client: TransformAgenticServiceClient = session.client("awstransformagenticservice")

    list_agent_instances_paginator: ListAgentInstancesPaginator = client.get_paginator("list_agent_instances")
    list_artifacts_paginator: ListArtifactsPaginator = client.get_paginator("list_artifacts")
    list_hitl_tasks_paginator: ListHitlTasksPaginator = client.get_paginator("list_hitl_tasks")
    list_job_plan_steps_paginator: ListJobPlanStepsPaginator = client.get_paginator("list_job_plan_steps")
    ```
"""

from .client import TransformAgenticServiceClient
from .paginator import (
    ListAgentInstancesPaginator,
    ListArtifactsPaginator,
    ListHitlTasksPaginator,
    ListJobPlanStepsPaginator,
)

Client = TransformAgenticServiceClient


__all__ = (
    "Client",
    "TransformAgenticServiceClient",
    "ListAgentInstancesPaginator",
    "ListArtifactsPaginator",
    "ListHitlTasksPaginator",
    "ListJobPlanStepsPaginator",
)
