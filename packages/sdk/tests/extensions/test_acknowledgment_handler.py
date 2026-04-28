from agent_builder_sdk.custom_types.extension_types import ExtensionResponse
from agent_builder_sdk.extensions.acknowledgments.acknowledgment_handler import (
    AcknowledgmentHandler,
)


class TestAcknowledgmentHandler:
    """Test cases for AcknowledgmentHandler."""

    def test_init(self):
        """Test handler initialization."""
        handler = AcknowledgmentHandler(
            required=True,
            description="Test handler",
            params={"key": "value"},
        )

        assert handler.uri == "https://aws.com/transform/ext/acknowledgment/v1"
        assert handler.required is True
        assert handler.description == "Test handler"
        assert handler.params == {"key": "value"}

    def test_init_defaults(self):
        """Test handler initialization with defaults."""
        handler = AcknowledgmentHandler()

        assert handler.uri == "https://aws.com/transform/ext/acknowledgment/v1"
        assert handler.required is False
        assert handler.description is None
        assert handler.params is None

    def test_should_acknowledge_atx_chat(self):
        """Test acknowledgment for ATX_CHAT sender."""
        handler = AcknowledgmentHandler()

        assert handler.should_process(sender="ATX_CHAT") is True

    def test_should_acknowledge_other_sender(self):
        """Test no acknowledgment for other senders."""
        handler = AcknowledgmentHandler()

        assert handler.should_process(sender="OTHER_SENDER") is False
        assert handler.should_process(sender="") is False
        assert handler.should_process(sender="atx_chat") is False

    def test_create_acknowledgment(self):
        """Test acknowledgment creation."""
        handler = AcknowledgmentHandler()

        response = handler.process_request(request_id="req-123", context_id="ctx-456")

        assert isinstance(response, ExtensionResponse)
        assert response.message == "I'm working on your request and will get back to you shortly."
        assert response.metadata == {"https://aws.com/transform/ext/acknowledgment/v1": True}
        assert response.extensions == ["https://aws.com/transform/ext/acknowledgment/v1"]

    def test_create_acknowledgment_with_default_values(self):
        """Test acknowledgment creation with default values for missing kwargs."""
        handler = AcknowledgmentHandler()

        response = handler.process_request()

        assert response.message == "I'm working on your request and will get back to you shortly."
        assert response.metadata == {"https://aws.com/transform/ext/acknowledgment/v1": True}
        assert response.extensions == ["https://aws.com/transform/ext/acknowledgment/v1"]
