# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
# flake8: noqa: N815
# disabling mixedCaseNaming rule since this schema is trying to match Google's A2A

from typing import Literal, Union

from pydantic import BaseModel, Field


class JobCreatorA2AMsgTarget(BaseModel):
    """Target the job creator."""

    userSelection: Literal["jobCreator"] = Field(..., description="Target the job creator")


class HitlSubmitterA2AMsgTarget(BaseModel):
    """Target the HITL task submitter."""

    userSelection: Literal["hitlSubmitter"] = Field(..., description="Target the HITL submitter")
    hitlTaskId: str = Field(..., description="HITL task ID")


class SpecificUserA2AMsgTarget(BaseModel):
    """Target a specific user."""

    userSelection: Literal["specificUser"] = Field(..., description="Target a specific user")
    userId: str = Field(..., description="User ID to target")


A2AMessageTarget = Union[
    JobCreatorA2AMsgTarget
    # , HitlSubmitterA2AMsgTarget, SpecificUserA2AMsgTarget only open send message to the job creator
]
