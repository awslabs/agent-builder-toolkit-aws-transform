#!/usr/bin/env python3
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Example usage of the intelligent test generator."""

import json
import logging
from pathlib import Path

from .intelligent_generator import IntelligentTestGenerator
from .domain_analyzer import DomainAnalyzer

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Curated teacher samples live at the evaluation root:
# src/test_data_generator/ -> src/ -> evaluation/test_samples/
TEST_SAMPLES_DIR = Path(__file__).resolve().parent.parent.parent / "test_samples"


def example_basic_generation():
    """Example: Basic test generation from teacher samples."""
    print("\n" + "=" * 80)
    print("EXAMPLE 1: Basic Test Generation")
    print("=" * 80 + "\n")

    # Load teacher samples
    teacher_sample_file = TEST_SAMPLES_DIR / "onboarding_intermediate.json"

    with open(teacher_sample_file, 'r') as f:
        teacher_samples = json.load(f)

    logger.info(f"Loaded {len(teacher_samples)} teacher samples")

    # Initialize generator
    generator = IntelligentTestGenerator(
        region_name='us-west-2',
        model_id='us.anthropic.claude-opus-4-5-20251101-v1:0',
        temperature=0.8
    )

    # Generate 5 tests
    generated = generator.generate_test_cases(
        teacher_samples=teacher_samples,
        count=5,
        diversity_factor=0.7,
        output_dir="./example_output/basic"
    )

    logger.info(f"\nGenerated {len(generated)} tests")
    for i, test in enumerate(generated, 1):
        logger.info(f"  {i}. {test['name']} (complexity: {test['complexity']})")


def example_with_power_md():
    """Example: Generation with POWER.md context."""
    print("\n" + "=" * 80)
    print("EXAMPLE 2: Generation with POWER.md Context")
    print("=" * 80 + "\n")

    # Load teacher samples
    teacher_sample_file = TEST_SAMPLES_DIR / "onboarding_intermediate.json"

    with open(teacher_sample_file, 'r') as f:
        teacher_samples = json.load(f)

    # Load POWER.md
    power_md_path = Path("/path/to/file")
    power_instructions = None

    if power_md_path.exists():
        with open(power_md_path, 'r') as f:
            power_instructions = f.read()
        logger.info(f"Loaded POWER.md ({len(power_instructions)} chars)")
    else:
        logger.warning("POWER.md not found, proceeding without it")

    # Initialize generator
    generator = IntelligentTestGenerator(
        region_name='us-west-2',
        model_id='us.anthropic.claude-opus-4-5-20251101-v1:0',
        temperature=0.8
    )

    # Generate tests with POWER.md context
    generated = generator.generate_test_cases(
        teacher_samples=teacher_samples,
        count=3,
        context=power_instructions,
        diversity_factor=0.8,
        output_dir="./example_output/with_power"
    )

    logger.info(f"\nGenerated {len(generated)} tests with POWER.md context")


def example_domain_analysis():
    """Example: Domain analysis without generation.

    Note: source_context is required for domain understanding.
    This example uses a placeholder, but in practice you should load
    from POWER.md, source code, or other documentation.
    """
    print("\n" + "=" * 80)
    print("EXAMPLE 3: Domain Analysis Only")
    print("=" * 80 + "\n")

    # Load teacher samples
    teacher_sample_file = TEST_SAMPLES_DIR / "onboarding_intermediate.json"

    with open(teacher_sample_file, 'r') as f:
        teacher_samples = json.load(f)

    # Initialize analyzer
    analyzer = DomainAnalyzer(
        region_name='us-west-2',
        model_id='us.anthropic.claude-opus-4-5-20251101-v1:0'
    )

    # Load source context (required for domain understanding)
    # In real usage, load from POWER.md or source code
    # For this example, we'll use a placeholder
    source_context = """
    # Example Agent Instructions
    This is a placeholder for actual agent instructions, source code, or documentation.
    In practice, you should load this from:
    - POWER.md files with agent instructions
    - Source code documentation
    - Configuration files
    - Any context that describes what the agent should do
    """

    # Analyze domain
    analysis = analyzer.analyze_test_samples(teacher_samples, source_context)

    # Save analysis
    output_path = "./example_output/analysis/domain_analysis.json"
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    analyzer.save_analysis(analysis, output_path)

    # Print summary
    logger.info(f"\nDomain Analysis Summary:")
    logger.info(f"  Domain: {analysis['domain_understanding'].get('domain_description', 'N/A')}")
    logger.info(f"  Core Capabilities: {len(analysis['domain_understanding'].get('core_capabilities', []))}")
    logger.info(f"  User Personas: {len(analysis['domain_understanding'].get('user_personas', []))}")
    logger.info(f"  Assertion Types: {list(analysis['assertion_patterns']['assertion_types'].keys())}")
    logger.info(f"\nAnalysis saved to: {output_path}")


def example_high_diversity():
    """Example: High diversity generation for edge cases."""
    print("\n" + "=" * 80)
    print("EXAMPLE 4: High Diversity Generation")
    print("=" * 80 + "\n")

    # Load teacher samples
    teacher_sample_file = TEST_SAMPLES_DIR / "onboarding_intermediate.json"

    with open(teacher_sample_file, 'r') as f:
        teacher_samples = json.load(f)

    # Initialize generator
    generator = IntelligentTestGenerator(
        region_name='us-west-2',
        model_id='us.anthropic.claude-opus-4-5-20251101-v1:0',
        temperature=0.9  # Higher temperature for more creativity
    )

    # Generate with high diversity
    generated = generator.generate_test_cases(
        teacher_samples=teacher_samples,
        count=5,
        diversity_factor=0.95,  # Very high diversity
        output_dir="./example_output/high_diversity"
    )

    logger.info(f"\nGenerated {len(generated)} highly diverse tests")
    logger.info("\nScenarios covered:")
    for i, test in enumerate(generated, 1):
        logger.info(f"  {i}. {test['name']}")
        logger.info(f"     Complexity: {test['complexity']}, Assertions: {len(test.get('assertions', []))}")


def example_specific_complexity():
    """Example: Generate tests of specific complexity."""
    print("\n" + "=" * 80)
    print("EXAMPLE 5: Specific Complexity Generation")
    print("=" * 80 + "\n")

    # Load teacher samples
    teacher_sample_file = TEST_SAMPLES_DIR / "onboarding_intermediate.json"

    with open(teacher_sample_file, 'r') as f:
        teacher_samples = json.load(f)

    # Initialize generator
    generator = IntelligentTestGenerator(
        region_name='us-west-2',
        model_id='us.anthropic.claude-opus-4-5-20251101-v1:0'
    )

    # Generate only complex tests
    generated = generator.generate_test_cases(
        teacher_samples=teacher_samples,
        count=3,
        complexity='complex',
        diversity_factor=0.8,
        output_dir="./example_output/complex_only"
    )

    logger.info(f"\nGenerated {len(generated)} complex tests")
    for test in generated:
        logger.info(f"  - {test['name']}: {len(test.get('assertions', []))} assertions")


def main():
    """Run all examples."""
    print("\n" + "=" * 80)
    print("INTELLIGENT TEST GENERATOR - EXAMPLES")
    print("=" * 80)

    examples = [
        ("Basic Generation", example_basic_generation),
        ("With POWER.md", example_with_power_md),
        ("Domain Analysis", example_domain_analysis),
        ("High Diversity", example_high_diversity),
        ("Specific Complexity", example_specific_complexity),
    ]

    print("\nAvailable examples:")
    for i, (name, _) in enumerate(examples, 1):
        print(f"  {i}. {name}")

    print("\nRunning Example 3 (Domain Analysis) as it's quickest...")
    print("To run other examples, call them directly from this file.\n")

    # Run domain analysis example (quickest)
    example_domain_analysis()

    print("\n" + "=" * 80)
    print("Example complete! Check ./example_output/ for results")
    print("=" * 80 + "\n")


if __name__ == '__main__':
    main()
