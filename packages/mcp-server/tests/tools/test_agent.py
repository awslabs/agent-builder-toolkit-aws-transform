# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for agent registry tools.

Focus: ensure orchestrators are registered with `a2aSupported=true` by default.
The AWS Transform webapp only routes chat traffic to orchestrators whose
`jobOrchestratorMetadata.a2aSupported` is true, and the field cannot be
updated post-registration. The tools must default missing values and warn
on explicit `false`.
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from agent_builder_mcp.tools.agent import (
    _ensure_capabilities_a2a,
    _ensure_orchestrator_a2a,
    publish_agent_version,
    register_agent,
)

MODULE = "agent_builder_mcp.tools.agent"


class TestEnsureOrchestratorA2A:
    """Defaults and warnings for `metadata.jobOrchestratorMetadata.a2aSupported`."""

    def test_subagent_metadata_untouched(self) -> None:
        metadata: dict = {
            "type": "SUB_AGENT",
            "description": "x",
            "ownerName": "o",
            "ownerType": "DIRECT_AGENT",
        }
        snapshot = json.loads(json.dumps(metadata))
        warnings = _ensure_orchestrator_a2a(metadata)
        assert warnings == []
        assert metadata == snapshot

    def test_orchestrator_explicit_false_passes_through_with_warning(self) -> None:
        metadata: dict = {
            "jobOrchestrator": True,
            "jobOrchestratorMetadata": {
                "chatUILabel": "x",
                "chatAgentIdentifier": "x",
                "a2aSupported": False,
            },
        }
        warnings = _ensure_orchestrator_a2a(metadata)
        assert metadata["jobOrchestratorMetadata"]["a2aSupported"] is False
        assert len(warnings) == 1
        assert "a2aSupported" in warnings[0]
        assert "false" in warnings[0].lower()

    def test_orchestrator_missing_a2a_defaults_true_with_warning(self) -> None:
        metadata: dict = {
            "jobOrchestrator": True,
            "jobOrchestratorMetadata": {
                "chatUILabel": "x",
                "chatAgentIdentifier": "x",
            },
        }
        warnings = _ensure_orchestrator_a2a(metadata)
        assert metadata["jobOrchestratorMetadata"]["a2aSupported"] is True
        assert len(warnings) == 1
        assert "default" in warnings[0].lower()

    def test_orchestrator_missing_metadata_block_left_alone(self) -> None:
        """Don't synthesize jobOrchestratorMetadata: chatUILabel and
        chatAgentIdentifier are also required, and we have no value for them.
        Better to let the registry surface the validation error."""
        metadata: dict = {"jobOrchestrator": True}
        warnings = _ensure_orchestrator_a2a(metadata)
        assert metadata == {"jobOrchestrator": True}
        assert warnings == []

    @pytest.mark.parametrize("bad_value", [None, "oops", 42, []])
    def test_orchestrator_metadata_not_dict_left_alone(self, bad_value) -> None:
        metadata: dict = {"jobOrchestrator": True, "jobOrchestratorMetadata": bad_value}
        warnings = _ensure_orchestrator_a2a(metadata)
        assert metadata["jobOrchestratorMetadata"] == bad_value
        assert warnings == []

    def test_orchestrator_explicit_none_treated_as_missing(self) -> None:
        """Explicit None on `a2aSupported` is normalized to true (same as missing)."""
        metadata: dict = {
            "jobOrchestrator": True,
            "jobOrchestratorMetadata": {
                "chatUILabel": "x",
                "chatAgentIdentifier": "x",
                "a2aSupported": None,
            },
        }
        warnings = _ensure_orchestrator_a2a(metadata)
        assert metadata["jobOrchestratorMetadata"]["a2aSupported"] is True
        assert len(warnings) == 1
        assert "default" in warnings[0].lower()

    def test_orchestrator_explicit_true_silent(self) -> None:
        metadata: dict = {
            "jobOrchestrator": True,
            "jobOrchestratorMetadata": {
                "chatUILabel": "x",
                "chatAgentIdentifier": "x",
                "a2aSupported": True,
            },
        }
        warnings = _ensure_orchestrator_a2a(metadata)
        assert warnings == []
        assert metadata["jobOrchestratorMetadata"]["a2aSupported"] is True

    def test_warning_mentions_aws_transform_not_atx(self) -> None:
        metadata: dict = {
            "jobOrchestrator": True,
            "jobOrchestratorMetadata": {"chatUILabel": "x", "chatAgentIdentifier": "x"},
        }
        warnings = _ensure_orchestrator_a2a(metadata)
        assert "AWS Transform" in warnings[0]
        assert "ATX" not in warnings[0]


class TestEnsureCapabilitiesA2A:
    """Defaults and warnings for `agentCard.capabilities.a2aSupported`."""

    def test_no_agent_card_skipped(self) -> None:
        configuration: dict = {"shortDescription": "x"}
        warnings = _ensure_capabilities_a2a(configuration)
        assert warnings == []
        assert configuration == {"shortDescription": "x"}

    def test_agent_card_without_capabilities_skipped(self) -> None:
        configuration: dict = {"agentCard": {"id": "x"}}
        warnings = _ensure_capabilities_a2a(configuration)
        assert warnings == []

    def test_capabilities_missing_a2a_defaults_true_with_warning(self) -> None:
        configuration: dict = {"agentCard": {"capabilities": {"restartable": True}}}
        warnings = _ensure_capabilities_a2a(configuration)
        assert configuration["agentCard"]["capabilities"]["a2aSupported"] is True
        assert len(warnings) == 1
        assert "default" in warnings[0].lower()

    def test_capabilities_explicit_false_passes_through_with_warning(self) -> None:
        configuration: dict = {
            "agentCard": {"capabilities": {"a2aSupported": False, "restartable": True}}
        }
        warnings = _ensure_capabilities_a2a(configuration)
        assert configuration["agentCard"]["capabilities"]["a2aSupported"] is False
        assert len(warnings) == 1
        assert "false" in warnings[0].lower()

    def test_capabilities_explicit_true_silent(self) -> None:
        configuration: dict = {
            "agentCard": {"capabilities": {"a2aSupported": True, "restartable": True}}
        }
        warnings = _ensure_capabilities_a2a(configuration)
        assert warnings == []

    def test_warning_mentions_aws_transform_not_atx(self) -> None:
        configuration: dict = {"agentCard": {"capabilities": {"restartable": True}}}
        warnings = _ensure_capabilities_a2a(configuration)
        assert "AWS Transform" in warnings[0]
        assert "ATX" not in warnings[0]


class TestRegisterAgentTool:
    """Tool-level integration: warnings reach the JSON response, registry sees defaults."""

    def test_orchestrator_defaults_a2a_in_call_to_registry(self) -> None:
        client = MagicMock()
        client.register_agent.return_value = {"agentArn": "arn:..."}
        with patch(f"{MODULE}.registry_client", return_value=client):
            result = json.loads(
                register_agent(
                    name="my-orch",
                    metadata={
                        "jobOrchestrator": True,
                        "jobOrchestratorMetadata": {
                            "chatUILabel": "x",
                            "chatAgentIdentifier": "x",
                        },
                    },
                )
            )
        sent_metadata = client.register_agent.call_args.kwargs["metadata"]
        assert sent_metadata["jobOrchestratorMetadata"]["a2aSupported"] is True
        assert "_warnings" in result
        assert any("a2aSupported" in w for w in result["_warnings"])

    def test_orchestrator_explicit_false_warns_but_passes_through(self) -> None:
        client = MagicMock()
        client.register_agent.return_value = {"agentArn": "arn:..."}
        with patch(f"{MODULE}.registry_client", return_value=client):
            result = json.loads(
                register_agent(
                    name="my-orch",
                    metadata={
                        "jobOrchestrator": True,
                        "jobOrchestratorMetadata": {
                            "chatUILabel": "x",
                            "chatAgentIdentifier": "x",
                            "a2aSupported": False,
                        },
                    },
                )
            )
        sent_metadata = client.register_agent.call_args.kwargs["metadata"]
        assert sent_metadata["jobOrchestratorMetadata"]["a2aSupported"] is False
        assert "_warnings" in result
        assert any("false" in w.lower() for w in result["_warnings"])

    def test_subagent_no_warnings(self) -> None:
        client = MagicMock()
        client.register_agent.return_value = {"agentArn": "arn:..."}
        with patch(f"{MODULE}.registry_client", return_value=client):
            result = json.loads(register_agent(name="my-sub", metadata={"type": "SUB_AGENT"}))
        assert "_warnings" not in result

    def test_warnings_do_not_clobber_registry_response_fields(self) -> None:
        """If the registry response ever uses `_warnings`, our merge must preserve it."""
        client = MagicMock()
        client.register_agent.return_value = {"agentArn": "arn:...", "_warnings": ["from-server"]}
        with patch(f"{MODULE}.registry_client", return_value=client):
            result = json.loads(
                register_agent(
                    name="my-orch",
                    metadata={
                        "jobOrchestrator": True,
                        "jobOrchestratorMetadata": {
                            "chatUILabel": "x",
                            "chatAgentIdentifier": "x",
                        },
                    },
                )
            )
        assert "from-server" in result["_warnings"]
        assert any("a2aSupported" in w for w in result["_warnings"])

    def test_warnings_surface_on_registry_error(self) -> None:
        """If the registry rejects the call, the user still needs to see warnings."""
        client = MagicMock()
        client.register_agent.side_effect = RuntimeError("validation failed")
        with patch(f"{MODULE}.registry_client", return_value=client):
            result = json.loads(
                register_agent(
                    name="my-orch",
                    metadata={
                        "jobOrchestrator": True,
                        "jobOrchestratorMetadata": {
                            "chatUILabel": "x",
                            "chatAgentIdentifier": "x",
                            "a2aSupported": False,
                        },
                    },
                )
            )
        assert "error" in result
        assert any("a2aSupported" in w for w in result["_warnings"])

    def test_orchestrator_with_correct_a2a_no_warnings(self) -> None:
        client = MagicMock()
        client.register_agent.return_value = {"agentArn": "arn:..."}
        with patch(f"{MODULE}.registry_client", return_value=client):
            result = json.loads(
                register_agent(
                    name="my-orch",
                    metadata={
                        "jobOrchestrator": True,
                        "jobOrchestratorMetadata": {
                            "chatUILabel": "x",
                            "chatAgentIdentifier": "x",
                            "a2aSupported": True,
                        },
                    },
                )
            )
        assert "_warnings" not in result


class TestPublishAgentVersionTool:
    """Tool-level integration for publish_agent_version."""

    def test_capabilities_defaults_a2a_in_call_to_registry(self) -> None:
        client = MagicMock()
        client.publish_agent_version.return_value = {"versionArn": "arn:..."}
        with patch(f"{MODULE}.registry_client", return_value=client):
            result = json.loads(
                publish_agent_version(
                    name="my-orch",
                    version="1.0.0",
                    configuration={
                        "agentCard": {
                            "id": "x",
                            "capabilities": {"restartable": True},
                        }
                    },
                )
            )
        sent_config = client.publish_agent_version.call_args.kwargs["configuration"]
        assert sent_config["agentCard"]["capabilities"]["a2aSupported"] is True
        assert "_warnings" in result

    def test_capabilities_explicit_false_warns_but_passes_through(self) -> None:
        client = MagicMock()
        client.publish_agent_version.return_value = {"versionArn": "arn:..."}
        with patch(f"{MODULE}.registry_client", return_value=client):
            result = json.loads(
                publish_agent_version(
                    name="my-orch",
                    version="1.0.0",
                    configuration={
                        "agentCard": {"capabilities": {"a2aSupported": False}},
                    },
                )
            )
        sent_config = client.publish_agent_version.call_args.kwargs["configuration"]
        assert sent_config["agentCard"]["capabilities"]["a2aSupported"] is False
        assert "_warnings" in result
        assert any("false" in w.lower() for w in result["_warnings"])

    def test_no_agent_card_no_warnings(self) -> None:
        client = MagicMock()
        client.publish_agent_version.return_value = {"versionArn": "arn:..."}
        with patch(f"{MODULE}.registry_client", return_value=client):
            result = json.loads(
                publish_agent_version(
                    name="my-orch", version="1.0.0", configuration={"shortDescription": "x"}
                )
            )
        assert "_warnings" not in result

    def test_warnings_do_not_clobber_registry_response_fields(self) -> None:
        client = MagicMock()
        client.publish_agent_version.return_value = {
            "versionArn": "arn:...",
            "_warnings": ["from-server"],
        }
        with patch(f"{MODULE}.registry_client", return_value=client):
            result = json.loads(
                publish_agent_version(
                    name="my-orch",
                    version="1.0.0",
                    configuration={"agentCard": {"capabilities": {"restartable": True}}},
                )
            )
        assert "from-server" in result["_warnings"]
        assert any("a2aSupported" in w for w in result["_warnings"])

    def test_correct_a2a_no_warnings(self) -> None:
        client = MagicMock()
        client.publish_agent_version.return_value = {"versionArn": "arn:..."}
        with patch(f"{MODULE}.registry_client", return_value=client):
            result = json.loads(
                publish_agent_version(
                    name="my-orch",
                    version="1.0.0",
                    configuration={
                        "agentCard": {"capabilities": {"a2aSupported": True}},
                    },
                )
            )
        assert "_warnings" not in result
