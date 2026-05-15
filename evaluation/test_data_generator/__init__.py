"""Test data generator package for ATX Transform Gym self-improving agents.

This package provides intelligent test data generation based on understanding
of the task domain and teacher test samples.
"""

from .intelligent_generator import IntelligentTestGenerator
from .domain_analyzer import DomainAnalyzer

__all__ = ['IntelligentTestGenerator', 'DomainAnalyzer']
