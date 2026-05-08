import os
import tempfile
from unittest.mock import Mock, patch

import pytest
from strands.agent import AgentResult
from strands.telemetry import EventLoopMetrics
from strands.types.content import ContentBlock, Message

from agent_builder_sdk.custom_types.common_types import A2AErrorCode, InvocationRequest
from agent_builder_sdk.custom_types.extension_types import ExtensionResponse
from agent_builder_sdk.message_queue import QueueResponse
from agent_builder_sdk.util.suggestions_manager import add_suggestions, clear_suggestions
from agent_builder_sdk.utils import (
    A2A_CHAT_SUGGESTIONS_EXT,
    A2A_MESSAGE_TYPE_EXT,
    A2A_SOURCE_INFORMATION_EXT,
    TransformEndpointConfig,
    build_agentic_api_endpoint_from_env,
    build_mcp_args_from_parsed_args,
    combine_tools,
    convert_queue_response_to_send_message_output,
    convert_subagent_response_to_send_message_output,
    extract_text_from_strands_agent_response,
    get_prompt,
    process_extension_handlers,
    write_content_to_file,
)


def test_get_prompt():
    """Test that get_prompt reads the system prompt file correctly."""
    with patch("agent_builder_sdk.utils.read_text") as mock_read_text:
        mock_read_text.return_value = "  Test system prompt  "

        result = get_prompt()

        mock_read_text.assert_called_once_with("agent_builder_sdk.prompts", "system_prompt.md")
        assert result == "Test system prompt"


@pytest.mark.parametrize(
    ("content", "expected"),
    (
        ([], ""),
        ([{}], ""),
        ([{"reasoningContent": {"reasoningText": {"text": "hello"}}}], ""),
        ([{"text": "hello"}], "hello"),
        ([{"text": " hello\n"}], "hello"),
        ([{"text": "hello"}, {"text": "world"}], "hello\nworld"),
        ([{"text": "\nhello "}, {"text": " world\n "}], "hello\nworld"),
        ([{"text": "\n"}, {"text": " "}, {"text": "hello"}], "hello"),
        ([{"text": "hello"}, {"text": ""}, {"text": "world"}], "hello\nworld"),
        ([{"text": "hello"}, {"text": "\n"}, {"text": "world"}], "hello\nworld"),
        ([{}, {"text": "hello"}, {}], "hello"),
        ([{"text": " "}], ""),
        ([{"text": "hello"}, {"reasoningContent": {"reasoningText": {"text": "world"}}}], "hello"),
    ),
)
def test_extract_text_from_strands_agent_response(content: list[ContentBlock], expected: str):
    message = Message(content=content, role="assistant")
    result = AgentResult("end_turn", message, EventLoopMetrics(), state=None)

    actual = extract_text_from_strands_agent_response(result)

    assert actual == expected


class TestTransformEndpointConfig:
    """Tests for the TransformEndpointConfig class."""

    @pytest.mark.parametrize(
        "region,expected_code",
        [
            ("us-east-1", "IAD"),
            ("us-west-2", "PDX"),
            ("eu-central-1", "FRA"),
            ("ap-southeast-1", "SIN"),
        ],
    )
    def test_get_airport_code_for_region_valid(self, region, expected_code):
        """Test that get_airport_code_for_region returns correct airport codes for valid regions."""
        result = TransformEndpointConfig.get_airport_code_for_region(region)
        assert result == expected_code

    @pytest.mark.parametrize(
        "region",
        [
            "invalid-region",
            "us-central-1",
            "eu-east-1",
            "",
            "123456",
        ],
    )
    def test_get_airport_code_for_region_invalid(self, region):
        """Test that get_airport_code_for_region raises ValueError for invalid regions."""
        with pytest.raises(ValueError, match=region):
            TransformEndpointConfig.get_airport_code_for_region(region)

    @pytest.mark.parametrize(
        "stage,region,component,expected_url",
        [
            (
                "prod",
                "us-east-1",
                "agenticapi",
                "https://iad.prod.agenticapi.elastic-gumby.ai.aws.dev",
            ),
            (
                "gamma",
                "eu-central-1",
                "agenticapi",
                "https://fra.gamma.agenticapi.elastic-gumby.ai.aws.dev",
            ),
        ],
    )
    def test_create_endpoint_url(self, stage, region, component, expected_url):
        """Test that create_endpoint_url constructs URLs correctly."""
        result = TransformEndpointConfig.create_endpoint_url(stage, region, component)
        assert result == expected_url

    def test_create_endpoint_url_invalid_region(self):
        """Test that create_endpoint_url raises ValueError for invalid regions."""
        with pytest.raises(ValueError, match="invalid-region"):
            TransformEndpointConfig.create_endpoint_url("prod", "invalid-region", "agenticapi")

    @pytest.mark.parametrize(
        "stage,region,expected_url",
        [
            ("prod", "us-east-1", "https://transform-agents.us-east-1.api.aws"),
            ("gamma", "eu-central-1", "https://transform-agents-gamma.eu-central-1.api.aws"),
        ],
    )
    def test_create_external_agenticapi_endpoint_url(self, stage, region, expected_url):
        """Test that create_external_agenticapi_endpoint_url constructs URLs correctly."""
        result = TransformEndpointConfig.create_external_agenticapi_endpoint_url(stage, region)
        assert result == expected_url


class TestBuildAgenticApiEndpointFromEnv:
    """Tests for the build_agentic_api_endpoint_from_env function."""

    @patch.dict(os.environ, {"STAGE": "prod", "AWS_REGION": "us-east-1"})
    def test_internal_api_endpoint(self):
        """Test building internal agentic API endpoint."""
        result = build_agentic_api_endpoint_from_env()
        assert result == "https://iad.prod.agenticapi.elastic-gumby.ai.aws.dev"

    @patch.dict(
        os.environ, {"STAGE": "prod", "AWS_REGION": "us-east-1", "USE_EXTERNAL_AGENTIC_API": "true"}
    )
    def test_external_api_endpoint(self):
        """Test building external agentic API endpoint."""
        result = build_agentic_api_endpoint_from_env()
        assert result == "https://transform-agents.us-east-1.api.aws"

    @patch.dict(os.environ, {}, clear=True)
    def test_missing_env_vars(self):
        """Test error when environment variables are missing."""
        with pytest.raises(
            ValueError, match="STAGE and AWS_REGION env variables must be non-empty"
        ):
            build_agentic_api_endpoint_from_env()


class TestConvertQueueResponseToSendMessageOutput:
    """Tests for the convert_queue_response_to_send_message_output function."""

    def test_success_with_response(self, a2a_message):
        """Test successful conversion with a response message."""
        response = QueueResponse(
            request_id="req-123", context_id="ctx-456", message="Agent response message"
        )

        result = convert_queue_response_to_send_message_output(response, a2a_message)

        assert result.error is None
        assert result.result is not None
        assert result.result.role == "agent"
        assert result.result.messageId == "msg-123"
        assert result.result.contextId == "ctx-456"
        assert len(result.result.parts) == 1
        assert result.result.parts[0]["text"] == "Agent response message"
        assert result.result.parts[0]["kind"] == "text"
        assert result.result.metadata == {}
        assert result.result.extensions == []

    def test_success_with_structured_ack(self, a2a_message):
        """Test successful conversion with structured acknowledgment metadata."""
        response = QueueResponse(
            request_id="req-123",
            context_id="ctx-456",
            message="I'm working on your request and will get back to you shortly.",
            metadata={
                "https://aws.com/transform/ext/acknowledgement/v1": {
                    "status": "acknowledged",
                    "timestamp": "2025-01-27T10:00:00Z",
                    "correlation_id": "corr-789",
                }
            },
        )

        result = convert_queue_response_to_send_message_output(response, a2a_message)

        assert result.error is None
        assert result.result is not None
        assert result.result.metadata == response.metadata
        assert result.result.extensions == []

    def test_metadata_without_structured_ack(self, a2a_message):
        """Test conversion with metadata that doesn't include structured acknowledgment."""
        response = QueueResponse(
            request_id="req-123",
            context_id="ctx-456",
            message="Regular message",
            metadata={"some_other_key": "some_value"},
        )

        result = convert_queue_response_to_send_message_output(response, a2a_message)

        assert result.error is None
        assert result.result is not None
        assert result.result.metadata == {"some_other_key": "some_value"}
        assert result.result.extensions == []

    def test_convert_queue_response_with_suggestions(self, a2a_message):
        """Test conversion includes suggestions when available."""
        clear_suggestions()  # Clean state
        suggestions = ["suggestion1", "suggestion2"]
        add_suggestions(suggestions)

        response = QueueResponse(request_id="req-123", context_id="ctx-456", message="Test message")

        result = convert_queue_response_to_send_message_output(response, a2a_message)

        assert result.error is None
        assert result.result is not None
        assert A2A_CHAT_SUGGESTIONS_EXT in result.result.metadata
        assert result.result.metadata[A2A_CHAT_SUGGESTIONS_EXT] == suggestions
        assert A2A_CHAT_SUGGESTIONS_EXT in result.result.extensions
        clear_suggestions()

    def test_error_case(self, a2a_message):
        """Test conversion with error message."""
        response = QueueResponse(
            request_id="req-123", context_id="ctx-456", error_message="Something went wrong"
        )

        result = convert_queue_response_to_send_message_output(response, a2a_message)

        assert result.result is None
        assert result.error is not None
        assert result.error.code == A2AErrorCode.INTERNAL_ERROR
        assert result.error.message == "Something went wrong"

    def test_none_response(self, a2a_message):
        """Test conversion with None response."""
        result = convert_queue_response_to_send_message_output(None, a2a_message)

        assert result.error is None
        assert result.result is not None
        assert result.result.parts == []
        assert result.result.contextId is None
        assert result.result.extensions == []

    def test_extensions_from_request_message(self, a2a_message):
        """Test that extensions from request message are not included (only response extensions)."""
        a2a_message.extensions = ["ext1", "ext2"]
        response = QueueResponse(request_id="req-123", context_id="ctx-456", message="Test message")

        result = convert_queue_response_to_send_message_output(response, a2a_message)

        assert result.error is None
        assert result.result is not None
        assert result.result.extensions == []

    def test_extensions_from_response(self, a2a_message):
        """Test that extensions from response are included."""
        response = QueueResponse(
            request_id="req-123",
            context_id="ctx-456",
            message="Test message",
            extensions=["resp_ext1"],
        )

        result = convert_queue_response_to_send_message_output(response, a2a_message)

        assert result.error is None
        assert result.result is not None
        assert result.result.extensions == ["resp_ext1"]

    def test_extensions_combined(self, a2a_message):
        """Test that only response extensions are included."""
        a2a_message.extensions = ["req_ext1", "req_ext2"]
        response = QueueResponse(
            request_id="req-123",
            context_id="ctx-456",
            message="Test message",
            extensions=["resp_ext1"],
        )

        result = convert_queue_response_to_send_message_output(response, a2a_message)

        assert result.error is None
        assert result.result is not None
        assert result.result.extensions == ["resp_ext1"]

    def test_success_with_sender(self, a2a_message):
        sender = "agent-instance-id"
        queue_response = QueueResponse(
            request_id="request-id-1", context_id="context-id-1", message="queue message"
        )

        result = convert_queue_response_to_send_message_output(queue_response, a2a_message, sender)

        assert result.error is None
        assert result.result is not None
        assert result.result.role == "agent"
        assert result.result.messageId == a2a_message.messageId
        assert result.result.contextId == queue_response.context_id
        assert result.result.parts == [{"kind": "text", "text": queue_response.message}]
        assert result.result.extensions == [A2A_SOURCE_INFORMATION_EXT]
        assert result.result.metadata == {
            A2A_SOURCE_INFORMATION_EXT: {"senderAgentInstanceId": sender}
        }

    def test_success_with_sender_and_extensions(self, a2a_message):
        sender = "agent-instance-id"
        queue_response = QueueResponse(
            request_id="request-id-1",
            context_id="context-id-1",
            message="queue message",
            metadata={"resp_ext1": "some_value"},
            extensions=["resp_ext1"],
        )

        result = convert_queue_response_to_send_message_output(queue_response, a2a_message, sender)

        assert result.error is None
        assert result.result is not None
        assert result.result.role == "agent"
        assert result.result.messageId == a2a_message.messageId
        assert result.result.contextId == queue_response.context_id
        assert result.result.parts == [{"kind": "text", "text": queue_response.message}]
        assert result.result.extensions == ["resp_ext1", A2A_SOURCE_INFORMATION_EXT]
        assert result.result.metadata == {
            "resp_ext1": "some_value",
            A2A_SOURCE_INFORMATION_EXT: {"senderAgentInstanceId": sender},
        }

    def test_success_with_sender_preserves_source_info_extension(self, a2a_message):
        sender = "agent-instance-id"
        queue_response = QueueResponse(
            request_id="request-id-1",
            context_id="context-id-1",
            message="queue message",
            metadata={A2A_SOURCE_INFORMATION_EXT: {"senderAgentInstanceId": "preserved"}},
            extensions=[A2A_SOURCE_INFORMATION_EXT],
        )

        result = convert_queue_response_to_send_message_output(queue_response, a2a_message, sender)

        assert result.error is None
        assert result.result is not None
        assert result.result.role == "agent"
        assert result.result.messageId == a2a_message.messageId
        assert result.result.contextId == queue_response.context_id
        assert result.result.parts == [{"kind": "text", "text": queue_response.message}]
        assert result.result.extensions == [A2A_SOURCE_INFORMATION_EXT]
        assert result.result.metadata == {
            A2A_SOURCE_INFORMATION_EXT: {"senderAgentInstanceId": "preserved"}
        }

    def test_success_with_empty_response_message(self, a2a_message):
        queue_response = QueueResponse(
            request_id="request-id-1", context_id="context-id-1", message=""
        )

        result = convert_queue_response_to_send_message_output(queue_response, a2a_message)

        assert result.error is None
        assert result.result is not None
        assert result.result.parts == []

    def test_success_with_task_id(self, a2a_message):
        """Test successful conversion with task_id included."""
        queue_response = QueueResponse(
            request_id="request-id-1",
            context_id="context-id-1",
            task_id="task-123",
            message="Response with task ID",
        )

        result = convert_queue_response_to_send_message_output(queue_response, a2a_message)

        assert result.error is None
        assert result.result.role == "agent"
        assert result.result.parts[0]["text"] == "Response with task ID"


class TestA2AMessageTypeExt:
    """Tests for the A2A_MESSAGE_TYPE_EXT constant and its usage in responses."""

    def test_constant_value(self):
        """Test that A2A_MESSAGE_TYPE_EXT has the expected URI value."""
        assert A2A_MESSAGE_TYPE_EXT == "https://aws.com/transform/ext/message_type/v1"

    def test_convert_queue_response_with_message_type_metadata(self, a2a_message):
        """Test conversion preserves A2A_MESSAGE_TYPE_EXT metadata from queue response."""
        response = QueueResponse(
            request_id="req-123",
            context_id="ctx-456",
            message="Thinking...",
            metadata={A2A_MESSAGE_TYPE_EXT: {"messageType": "partial_update"}},
            extensions=[A2A_MESSAGE_TYPE_EXT],
        )

        result = convert_queue_response_to_send_message_output(response, a2a_message)

        assert result.error is None
        assert result.result is not None
        assert A2A_MESSAGE_TYPE_EXT in result.result.metadata
        assert result.result.metadata[A2A_MESSAGE_TYPE_EXT] == {"messageType": "partial_update"}
        assert A2A_MESSAGE_TYPE_EXT in result.result.extensions

    def test_convert_queue_response_with_message_type_and_sender(self, a2a_message):
        """Test conversion with both A2A_MESSAGE_TYPE_EXT and sender information."""
        sender = "agent-instance-id"
        response = QueueResponse(
            request_id="req-123",
            context_id="ctx-456",
            message="Processing...",
            metadata={A2A_MESSAGE_TYPE_EXT: {"messageType": "partial_update"}},
            extensions=[A2A_MESSAGE_TYPE_EXT],
        )

        result = convert_queue_response_to_send_message_output(response, a2a_message, sender)

        assert result.error is None
        assert result.result is not None
        assert A2A_MESSAGE_TYPE_EXT in result.result.metadata
        assert result.result.metadata[A2A_MESSAGE_TYPE_EXT] == {"messageType": "partial_update"}
        assert A2A_SOURCE_INFORMATION_EXT in result.result.metadata
        assert result.result.metadata[A2A_SOURCE_INFORMATION_EXT] == {
            "senderAgentInstanceId": sender
        }
        assert A2A_MESSAGE_TYPE_EXT in result.result.extensions
        assert A2A_SOURCE_INFORMATION_EXT in result.result.extensions

    def test_convert_queue_response_with_message_type_and_suggestions(self, a2a_message):
        """Test conversion with A2A_MESSAGE_TYPE_EXT alongside chat suggestions."""
        clear_suggestions()
        suggestions = ["suggestion1", "suggestion2"]
        add_suggestions(suggestions)

        response = QueueResponse(
            request_id="req-123",
            context_id="ctx-456",
            message="Thinking...",
            metadata={A2A_MESSAGE_TYPE_EXT: {"messageType": "partial_update"}},
            extensions=[A2A_MESSAGE_TYPE_EXT],
        )

        result = convert_queue_response_to_send_message_output(response, a2a_message)

        assert result.error is None
        assert result.result is not None
        assert A2A_MESSAGE_TYPE_EXT in result.result.metadata
        assert A2A_CHAT_SUGGESTIONS_EXT in result.result.metadata
        assert result.result.metadata[A2A_CHAT_SUGGESTIONS_EXT] == suggestions
        assert A2A_MESSAGE_TYPE_EXT in result.result.extensions
        assert A2A_CHAT_SUGGESTIONS_EXT in result.result.extensions
        clear_suggestions()

    def test_message_type_ext_distinct_from_other_constants(self):
        """Test that A2A_MESSAGE_TYPE_EXT is distinct from other A2A extension constants."""
        assert A2A_MESSAGE_TYPE_EXT != A2A_SOURCE_INFORMATION_EXT
        assert A2A_MESSAGE_TYPE_EXT != A2A_CHAT_SUGGESTIONS_EXT


class TestConvertSubagentResponseToSendMessageOutput:
    """Tests for the convert_subagent_response_to_send_message_output function."""

    def test_success_with_response(self, a2a_message):
        """Test successful conversion with a response message."""
        context_id = "test-context-123"
        response_text = "This is the agent response"

        result = convert_subagent_response_to_send_message_output(
            context_id, a2a_message, response=response_text
        )

        assert result.error is None
        assert result.result is not None
        assert result.result.role == "agent"
        assert result.result.messageId == a2a_message.messageId
        assert result.result.contextId == context_id
        assert result.result.parts == [{"kind": "text", "text": response_text}]
        assert result.result.extensions == []
        assert result.result.metadata == {}

    def test_success_with_empty_response(self, a2a_message):
        """Test successful conversion with empty response."""
        context_id = "test-context-123"

        result = convert_subagent_response_to_send_message_output(
            context_id, a2a_message, response=None
        )

        assert result.error is None
        assert result.result is not None
        assert result.result.parts == []

    def test_success_with_sender(self, a2a_message):
        context_id = "test-context-123"
        response_text = "This is the agent response"
        sender = "agent-instance-id"

        result = convert_subagent_response_to_send_message_output(
            context_id, a2a_message, response=response_text, sender=sender
        )

        assert result.error is None
        assert result.result is not None
        assert result.result.role == "agent"
        assert result.result.messageId == a2a_message.messageId
        assert result.result.contextId == context_id
        assert result.result.parts == [{"kind": "text", "text": response_text}]
        assert result.result.extensions == [A2A_SOURCE_INFORMATION_EXT]
        assert result.result.metadata == {
            A2A_SOURCE_INFORMATION_EXT: {"senderAgentInstanceId": sender}
        }

    def test_error_case(self, a2a_message):
        """Test conversion with error message."""
        context_id = "test-context-123"
        error_msg = "Something went wrong"

        result = convert_subagent_response_to_send_message_output(
            context_id, a2a_message, error_message=error_msg
        )

        assert result.result is None
        assert result.error is not None
        assert result.error.code == A2AErrorCode.INTERNAL_ERROR
        assert result.error.message == error_msg


class TestBuildMcpArgsFromParsedArgs:
    """Tests for the build_mcp_args_from_parsed_args function."""

    @pytest.fixture
    def mock_args(self):
        """Set up test fixtures."""
        mock_args = Mock()
        mock_args.binary_location = "/path/to/binary"
        mock_args.workspace_id = "workspace-123"
        mock_args.job_id = "job-456"
        mock_args.agent_instance_id = "agent-789"
        mock_args.agentic_api_endpoint = "https://test.endpoint.com"
        return mock_args

    @patch("agent_builder_sdk.utils.get_default_auth_token_file_path")
    def test_success_with_explicit_endpoint(self, mock_auth_path, mock_args):
        """Test successful MCP args building with explicit endpoint."""
        mock_auth_path.return_value = "/path/to/auth/token"

        result = build_mcp_args_from_parsed_args(mock_args)

        expected = {
            "binaryLocation": "/path/to/binary",
            "workspaceId": "workspace-123",
            "jobId": "job-456",
            "agentInstanceId": "agent-789",
            "agenticApiEndpoint": "https://test.endpoint.com",
            "authTokenFile": "/path/to/auth/token",
        }
        assert result == expected

    @patch("agent_builder_sdk.utils.build_agentic_api_endpoint_from_env")
    @patch("agent_builder_sdk.utils.get_default_auth_token_file_path")
    def test_success_with_env_endpoint(self, mock_auth_path, mock_build_endpoint, mock_args):
        """Test successful MCP args building with endpoint from environment."""
        mock_auth_path.return_value = "/path/to/auth/token"
        mock_build_endpoint.return_value = "https://env.endpoint.com"
        mock_args.agentic_api_endpoint = None

        result = build_mcp_args_from_parsed_args(mock_args)

        expected = {
            "binaryLocation": "/path/to/binary",
            "workspaceId": "workspace-123",
            "jobId": "job-456",
            "agentInstanceId": "agent-789",
            "agenticApiEndpoint": "https://env.endpoint.com",
            "authTokenFile": "/path/to/auth/token",
        }
        assert result == expected
        mock_build_endpoint.assert_called_once()

    def test_missing_required_args(self):
        """Test that missing required arguments raise AttributeError."""

        # Create a mock that doesn't have the required attributes
        class MockArgs:
            def __init__(self):
                self.job_id = "job-456"
                self.agent_instance_id = "agent-789"

        mock_args = MockArgs()

        with pytest.raises(
            AttributeError, match="Missing required arguments.*binary_location.*workspace_id"
        ):
            build_mcp_args_from_parsed_args(mock_args)


class TestCombineTools:
    """Tests for the combine_tools function."""

    def test_combine_tools_no_tools(self):
        """Test combine_tools with no tools."""
        result = combine_tools()
        assert result == []

    def test_combine_tools_mcp_only(self):
        """Test combine_tools with only MCP clients."""
        mock_tool = Mock()
        mock_tool.tool_name = "test_tool"

        mock_client = Mock()
        mock_client.__enter__ = Mock(return_value=mock_client)
        mock_client.__exit__ = Mock(return_value=None)
        mock_client.list_tools_sync.return_value = [mock_tool]

        result = combine_tools(mcp_clients=[mock_client])
        assert len(result) == 1
        assert result[0] == mock_tool

    def test_combine_tools_custom_only(self):
        """Test combine_tools with only custom tools."""
        mock_tool = Mock()
        mock_tool.tool_name = "custom_tool"

        result = combine_tools(custom_tools=[mock_tool])
        assert len(result) == 1
        assert result[0] == mock_tool

    def test_combine_tools_with_exclusions(self):
        """Test combine_tools with excluded tool names."""
        mock_tool1 = Mock()
        mock_tool1.tool_name = "included_tool"
        mock_tool2 = Mock()
        mock_tool2.tool_name = "excluded_tool"

        result = combine_tools(
            custom_tools=[mock_tool1, mock_tool2], excluded_tool_names={"excluded_tool"}
        )
        assert len(result) == 1
        assert result[0] == mock_tool1

    def test_combine_tools_duplicate_error(self):
        """Test combine_tools raises error for duplicate tool names."""
        mock_tool1 = Mock()
        mock_tool1.tool_name = "duplicate_tool"
        mock_tool2 = Mock()
        mock_tool2.tool_name = "duplicate_tool"

        with pytest.raises(ValueError, match="Duplicate tool name found: 'duplicate_tool'"):
            combine_tools(custom_tools=[mock_tool1, mock_tool2])

    def test_combine_tools_with_excluded_mcp_tools(self):
        """Test combine_tools with excluded MCP tool names."""
        mock_mcp_tool1 = Mock()
        mock_mcp_tool1.tool_name = "mcp_included"
        mock_mcp_tool2 = Mock()
        mock_mcp_tool2.tool_name = "mcp_excluded"

        mock_client = Mock()
        mock_client.__enter__ = Mock(return_value=mock_client)
        mock_client.__exit__ = Mock(return_value=None)
        mock_client.list_tools_sync.return_value = [mock_mcp_tool1, mock_mcp_tool2]

        result = combine_tools(mcp_clients=[mock_client], excluded_mcp_tool_names={"mcp_excluded"})
        assert len(result) == 1
        assert result[0] == mock_mcp_tool1

    def test_combine_tools_with_both_exclusion_types(self):
        """Test combine_tools with both excluded_tool_names and excluded_mcp_tool_names."""
        mock_mcp_tool = Mock()
        mock_mcp_tool.tool_name = "mcp_excluded"
        mock_custom_tool = Mock()
        mock_custom_tool.tool_name = "custom_excluded"

        mock_client = Mock()
        mock_client.__enter__ = Mock(return_value=mock_client)
        mock_client.__exit__ = Mock(return_value=None)
        mock_client.list_tools_sync.return_value = [mock_mcp_tool]

        result = combine_tools(
            mcp_clients=[mock_client],
            custom_tools=[mock_custom_tool],
            excluded_tool_names={"custom_excluded"},
            excluded_mcp_tool_names={"mcp_excluded"},
        )
        assert len(result) == 0


class TestCleanupProcessSafely:
    """Tests for the cleanup_process_safely function."""

    @patch("agent_builder_sdk.utils.logger")
    def test_cleanup_process_safely_terminate_exception(self, mock_logger):
        """Test cleanup_process_safely handles terminate exception and force kills."""
        from agent_builder_sdk.utils import cleanup_process_safely

        mock_process = Mock()
        mock_process.is_alive.side_effect = [
            True,
            True,
            False,
        ]  # Alive, still alive after terminate, dead after kill
        mock_process.terminate.side_effect = Exception("Terminate failed")

        cleanup_process_safely(mock_process, "TestProcess", timeout=1)

        # Verify terminate was attempted
        mock_process.terminate.assert_called_once()
        # Verify force kill was attempted
        mock_process.kill.assert_called_once()
        # Verify error was logged
        mock_logger.error.assert_called_with(
            "Error cleaning up TestProcess process: Terminate failed"
        )

    @patch("agent_builder_sdk.utils.logger")
    def test_cleanup_process_safely_force_kill_exception(self, mock_logger):
        """Test cleanup_process_safely handles force kill exception."""
        from agent_builder_sdk.utils import cleanup_process_safely

        mock_process = Mock()
        mock_process.is_alive.side_effect = [True, True, True]  # Always alive
        mock_process.terminate.side_effect = Exception("Terminate failed")
        mock_process.kill.side_effect = Exception("Kill failed")

        cleanup_process_safely(mock_process, "TestProcess", timeout=1)

        # Verify both terminate and kill were attempted
        mock_process.terminate.assert_called_once()
        mock_process.kill.assert_called_once()
        # Verify both errors were logged
        mock_logger.error.assert_any_call("Error cleaning up TestProcess process: Terminate failed")
        mock_logger.error.assert_any_call("Failed to force kill TestProcess process: Kill failed")


class TestProcessExtensionHandlers:
    """Tests for the process_extension_handlers function."""

    @pytest.fixture
    def mock_request(self):
        """Create a mock invocation request."""
        request = Mock(spec=InvocationRequest)
        request.message = Mock()
        request.message.extensions = []
        return request

    def test_no_extensions(self, mock_request):
        """Test with no extensions in message."""
        result = process_extension_handlers(
            request=mock_request,
            request_id="req-123",
            context_id="ctx-456",
            sender="ATX_CHAT",
            user_id="user-789",
            extension_handlers=None,
        )
        assert result is None

    def test_no_handlers(self, mock_request):
        """Test with extensions but no handlers."""
        mock_request.message.extensions = ["ext1", "ext2"]
        result = process_extension_handlers(
            request=mock_request,
            request_id="req-123",
            context_id="ctx-456",
            sender="ATX_CHAT",
            user_id="user-789",
            extension_handlers=None,
        )
        assert result is None

    @patch("agent_builder_sdk.utils.logger")
    def test_unsupported_extension(self, mock_logger, mock_request):
        """Test with unsupported extension."""
        mock_request.message.extensions = ["unsupported-ext"]
        mock_handler = Mock()
        mock_handler.uri = "supported-ext"

        result = process_extension_handlers(
            request=mock_request,
            request_id="req-123",
            context_id="ctx-456",
            sender="ATX_CHAT",
            user_id="user-789",
            extension_handlers=[mock_handler],
        )

        assert result is None
        mock_logger.info.assert_called_with("Ignoring unsupported extension: unsupported-ext")

    @patch("agent_builder_sdk.utils.logger")
    def test_supported_extension_should_not_process(self, mock_logger, mock_request):
        """Test with supported extension that should not be processed."""
        mock_request.message.extensions = ["test-ext"]
        mock_handler = Mock()
        mock_handler.uri = "test-ext"
        mock_handler.should_process.return_value = False

        result = process_extension_handlers(
            request=mock_request,
            request_id="req-123",
            context_id="ctx-456",
            sender="OTHER_SENDER",
            user_id="user-789",
            extension_handlers=[mock_handler],
        )

        assert result is None
        mock_handler.should_process.assert_called_once()
        mock_logger.info.assert_called_with("Ignoring unsupported extension: test-ext")

    @patch("agent_builder_sdk.utils.logger")
    def test_supported_extension_processes(self, mock_logger, mock_request):
        """Test with supported extension that processes successfully."""
        mock_request.message.extensions = ["test-ext"]
        mock_handler = Mock()
        mock_handler.uri = "test-ext"
        mock_handler.should_process.return_value = True
        mock_response = ExtensionResponse(message="test", metadata={}, extensions=[])
        mock_handler.process_request.return_value = mock_response

        result = process_extension_handlers(
            request=mock_request,
            request_id="req-123",
            context_id="ctx-456",
            sender="ATX_CHAT",
            user_id="user-789",
            extension_handlers=[mock_handler],
        )

        assert result == mock_response
        mock_handler.should_process.assert_called_once_with(
            request=mock_request, sender="ATX_CHAT", user_id="user-789", context_id="ctx-456"
        )
        mock_handler.process_request.assert_called_once_with(
            request=mock_request,
            request_id="req-123",
            context_id="ctx-456",
            sender="ATX_CHAT",
            user_id="user-789",
        )
        mock_logger.info.assert_called_with("Processing supported extension: test-ext")

    @patch("agent_builder_sdk.utils.logger")
    def test_multiple_extensions_returns_last(self, mock_logger, mock_request):
        """Test with multiple extensions returns last processed response."""
        mock_request.message.extensions = ["ext1", "ext2"]

        mock_handler1 = Mock()
        mock_handler1.uri = "ext1"
        mock_handler1.should_process.return_value = True
        mock_response1 = ExtensionResponse(message="response1", metadata={}, extensions=[])
        mock_handler1.process_request.return_value = mock_response1

        mock_handler2 = Mock()
        mock_handler2.uri = "ext2"
        mock_handler2.should_process.return_value = True
        mock_response2 = ExtensionResponse(message="response2", metadata={}, extensions=[])
        mock_handler2.process_request.return_value = mock_response2

        result = process_extension_handlers(
            request=mock_request,
            request_id="req-123",
            context_id="ctx-456",
            sender="ATX_CHAT",
            user_id="user-789",
            extension_handlers=[mock_handler1, mock_handler2],
        )

        assert result == mock_response2
        assert mock_handler1.process_request.called
        assert mock_handler2.process_request.called


class TestWriteContentToFile:
    """Test cases for write_content_to_file function."""

    def test_write_content_to_file_success(self):
        """Test successful file writing."""
        content = "test content"
        with tempfile.TemporaryDirectory() as temp_dir:
            file_path = os.path.join(temp_dir, "test_file.txt")
            write_content_to_file(content, file_path)
            with open(file_path, "r") as f:
                assert f.read() == content

    def test_write_content_to_file_creates_nested_directories(self):
        """Test that nested directories are created."""
        content = "test content"
        with tempfile.TemporaryDirectory() as temp_dir:
            file_path = os.path.join(temp_dir, "nested", "deep", "path", "test_file.txt")
            write_content_to_file(content, file_path)
            assert os.path.exists(file_path)
            with open(file_path, "r") as f:
                assert f.read() == content

    def test_write_content_to_file_handles_makedirs_error(self):
        """Test that makedirs errors are propagated."""
        content = "test content"
        file_path = "/tmp/test_file.txt"

        with patch("os.makedirs", side_effect=PermissionError("Permission denied")):
            with pytest.raises(PermissionError):
                write_content_to_file(content, file_path)

    def test_write_content_to_file_handles_write_error(self):
        """Test that file write errors are propagated."""
        content = "test content"
        with tempfile.TemporaryDirectory() as temp_dir:
            file_path = os.path.join(temp_dir, "test_file.txt")
            with patch("tempfile.NamedTemporaryFile", side_effect=IOError("Disk full")):
                with pytest.raises(IOError):
                    write_content_to_file(content, file_path)

    def test_write_content_to_file_with_empty_content(self):
        """Test writing empty content."""
        with tempfile.TemporaryDirectory() as temp_dir:
            file_path = os.path.join(temp_dir, "empty_file.txt")
            write_content_to_file("", file_path)
            with open(file_path, "r") as f:
                assert f.read() == ""

    def test_write_content_to_file_overwrites_existing(self):
        """Test that existing file is atomically replaced."""
        with tempfile.TemporaryDirectory() as temp_dir:
            file_path = os.path.join(temp_dir, "test_file.txt")
            write_content_to_file("original", file_path)
            write_content_to_file("updated", file_path)
            with open(file_path, "r") as f:
                assert f.read() == "updated"

    def test_write_content_to_file_cleans_up_temp_on_failure(self):
        """Test that temp file is cleaned up when os.replace fails."""
        with tempfile.TemporaryDirectory() as temp_dir, patch(
            "os.replace", side_effect=OSError("replace failed")
        ):
            file_path = os.path.join(temp_dir, "test_file.txt")
            with pytest.raises(OSError):
                write_content_to_file("content", file_path)
            # Verify no temp files left behind
            remaining_files = os.listdir(temp_dir)
            assert len(remaining_files) == 0, f"Temp files left behind: {remaining_files}"

    def test_write_content_to_file_filename_only(self):
        """Test writing to filename without directory component."""
        original_cwd = os.getcwd()
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                os.chdir(temp_dir)
                write_content_to_file("content", "file.txt")
                with open("file.txt", "r") as f:
                    assert f.read() == "content"
        finally:
            os.chdir(original_cwd)

    def test_write_content_to_file_integration(self):
        """Integration test with real file system."""
        content = "integration test content"

        with tempfile.TemporaryDirectory() as temp_dir:
            file_path = os.path.join(temp_dir, "nested", "test_file.txt")

            # Should not raise any exceptions
            write_content_to_file(content, file_path)

            # Verify file was created and content is correct
            assert os.path.exists(file_path)
            with open(file_path, "r") as f:
                assert f.read() == content

            # Verify directory was created
            assert os.path.exists(os.path.dirname(file_path))
