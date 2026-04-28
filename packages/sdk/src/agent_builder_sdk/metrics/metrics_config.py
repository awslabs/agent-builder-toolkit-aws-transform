"""Metrics configuration for agents."""

from dataclasses import dataclass, field
from typing import Dict


@dataclass(frozen=True)
class MetricsConfig:
    """Configuration for agent metrics emission."""

    enabled: bool = False
    namespace: str = "StrandsAgentMetrics"
    custom_dimensions: Dict[str, str] = field(default_factory=dict)
