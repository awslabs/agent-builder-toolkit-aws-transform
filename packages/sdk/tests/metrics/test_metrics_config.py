"""Tests for MetricsConfig."""

import pytest

from agent_builder_sdk.metrics.metrics_config import MetricsConfig


class TestMetricsConfig:
    """Test cases for MetricsConfig."""

    def test_default_config(self):
        """Test default MetricsConfig values."""
        config = MetricsConfig()

        assert not config.enabled
        assert config.namespace == "StrandsAgentMetrics"
        assert config.custom_dimensions == {}

    def test_custom_config(self):
        """Test MetricsConfig with custom values."""
        custom_dimensions = {"env": "test", "team": "platform"}
        config = MetricsConfig(
            enabled=True, namespace="CustomNamespace", custom_dimensions=custom_dimensions
        )

        assert config.enabled
        assert config.namespace == "CustomNamespace"
        assert config.custom_dimensions == custom_dimensions

    def test_config_immutable(self):
        """Test that MetricsConfig is immutable (frozen dataclass)."""
        config = MetricsConfig(enabled=True)

        with pytest.raises(AttributeError):
            config.enabled = False

    def test_config_equality(self):
        """Test MetricsConfig equality comparison."""
        config1 = MetricsConfig(enabled=True, namespace="Test")
        config2 = MetricsConfig(enabled=True, namespace="Test")
        config3 = MetricsConfig(enabled=False, namespace="Test")

        assert config1 == config2
        assert config1 != config3

    def test_config_with_empty_custom_dimensions(self):
        """Test MetricsConfig with empty custom dimensions."""
        config = MetricsConfig(custom_dimensions={})

        assert config.custom_dimensions == {}
        assert not config.enabled

    def test_config_with_none_custom_dimensions(self):
        """Test MetricsConfig behavior with None custom dimensions."""
        # Should use default factory
        config = MetricsConfig()

        assert config.custom_dimensions == {}

    def test_config_custom_dimensions_isolation(self):
        """Test that custom_dimensions are properly isolated between instances."""
        dims1 = {"key1": "value1"}
        dims2 = {"key2": "value2"}

        config1 = MetricsConfig(custom_dimensions=dims1)
        config2 = MetricsConfig(custom_dimensions=dims2)

        assert config1.custom_dimensions != config2.custom_dimensions
        assert config1.custom_dimensions == dims1
        assert config2.custom_dimensions == dims2

    def test_config_repr(self):
        """Test MetricsConfig string representation."""
        config = MetricsConfig(enabled=True, namespace="TestNS")
        repr_str = repr(config)

        assert "MetricsConfig" in repr_str
        assert "enabled=True" in repr_str
        assert "namespace='TestNS'" in repr_str
