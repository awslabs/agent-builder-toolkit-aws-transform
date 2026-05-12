# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Verify knowledge/data API files stay in sync with SDK botocore models."""

import pytest

SYNC_PAIRS = [
    (
        "packages/sdk/src/agent_builder_sdk/botocore_models/transformagenticservice/2018-05-10/service-2.json",
        "packages/mcp-server/src/agent_builder_mcp/knowledge/data/agentic_api.json",
    ),
    (
        "packages/sdk/src/agent_builder_sdk/botocore_models/atxagentregistryexternal/2022-07-26/service-2.json",
        "packages/mcp-server/src/agent_builder_mcp/knowledge/data/registry_api.json",
    ),
]


@pytest.mark.parametrize("source,copy", SYNC_PAIRS, ids=["agentic_api", "registry_api"])
def test_knowledge_data_matches_botocore_models(repo_root, source, copy):
    """Knowledge data API files must be identical to their SDK botocore-model source."""
    source_path = repo_root / source
    copy_path = repo_root / copy

    if not source_path.exists():
        pytest.skip(f"Source not found: {source}")
    if not copy_path.exists():
        pytest.skip(f"Copy not found: {copy}")

    source_content = source_path.read_bytes()
    copy_content = copy_path.read_bytes()

    assert source_content == copy_content, (
        f"{copy} is out of sync with {source}. "
        f"Run: cp {source} {copy}"
    )
