#!/usr/bin/env python3
"""Command-line interface for intelligent test data generation."""

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import List, Dict, Any

from .intelligent_generator import IntelligentTestGenerator
from .domain_analyzer import DomainAnalyzer
from .context_loader import ContextLoader, LOADING_STRATEGIES

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def load_teacher_samples(path: str) -> List[Dict[str, Any]]:
    """Load teacher samples from path (file or directory)."""
    path_obj = Path(path)

    if not path_obj.exists():
        raise FileNotFoundError(f"Path not found: {path}")

    samples = []

    if path_obj.is_file():
        with open(path_obj, 'r') as f:
            data = json.load(f)
            if isinstance(data, list):
                samples.extend(data)
            elif isinstance(data, dict) and 'test_cases' in data:
                samples.extend(data['test_cases'])
            else:
                # Assume it's a single test case wrapped in array
                samples.append(data)

    elif path_obj.is_dir():
        for json_file in path_obj.glob("*.json"):
            try:
                with open(json_file, 'r') as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        samples.extend(data)
                    else:
                        samples.append(data)
            except Exception as e:
                logger.warning(f"Failed to load {json_file}: {e}")

    logger.info(f"Loaded {len(samples)} teacher samples from {path}")
    return samples


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Intelligent Test Data Generator - Generate diverse test cases from teacher samples",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Generate from source context only (no teacher samples)
  python -m test_data_generator.cli \\
    --source-context /path/to/source/folder/ \\
    --count 20 \\
    --output generated_tests/

  # Generate with teacher samples + source context
  python -m test_data_generator.cli \\
    --teacher-samples test_samples/ \\
    --source-context /path/to/source/folder/ \\
    --count 20 \\
    --output generated_tests/

  # Generate with specific complexity and high diversity
  python -m test_data_generator.cli \\
    --teacher-samples test_samples/onboarding_intermediate.json \\
    --source-context /path/to/source/folder/ \\
    --count 10 \\
    --complexity medium \\
    --diversity 0.9 \\
    --output generated_tests/

  # Just analyze domain without generating
  python -m test_data_generator.cli \\
    --teacher-samples test_samples/ \\
    --source-context /path/to/source/folder/ \\
    --analyze-only \\
    --output analysis/
        """
    )

    parser.add_argument(
        '--teacher-samples',
        required=False,
        help='Path to teacher test samples (file or directory with JSON files). Optional - can generate from source context only.'
    )

    parser.add_argument(
        '--count',
        type=int,
        default=10,
        help='Number of test cases to generate (default: 10)'
    )

    parser.add_argument(
        '--output',
        required=True,
        help='Output directory for generated tests'
    )

    parser.add_argument(
        '--source-context',
        dest='source_context',
        required=True,
        help='Path to source context file or directory (loads all source/config/doc files recursively). REQUIRED for domain understanding.'
    )

    parser.add_argument(
        '--complexity',
        choices=['simple', 'medium', 'complex'],
        help='Generate tests of specific complexity (default: mixed)'
    )

    parser.add_argument(
        '--diversity',
        type=float,
        default=0.8,
        help='Diversity factor (0-1): 0=similar to teachers, 1=very diverse (default: 0.8)'
    )

    parser.add_argument(
        '--region',
        default='us-west-2',
        help='AWS region for Bedrock (default: us-west-2)'
    )

    parser.add_argument(
        '--model-id',
        default='us.anthropic.claude-opus-4-5-20251101-v1:0',
        help='Bedrock model ID (default: Claude Opus 4.5)'
    )

    parser.add_argument(
        '--temperature',
        type=float,
        default=0.8,
        help='Generation temperature (0-1, default: 0.8)'
    )

    parser.add_argument(
        '--analyze-only',
        action='store_true',
        help='Only analyze domain, do not generate tests'
    )

    parser.add_argument(
        '--no-deduplicate',
        action='store_true',
        help='Disable automatic deduplication of test names (default: deduplicate enabled)'
    )

    parser.add_argument(
        '--no-ensure-complex',
        action='store_true',
        help='Disable ensuring 20%% complex tests (default: ensure enabled)'
    )

    parser.add_argument(
        '--use-two-pass-analysis',
        action='store_true',
        help='Use two-pass analysis for large source context (more comprehensive but slower)'
    )

    parser.add_argument(
        '--loading-strategy',
        choices=list(LOADING_STRATEGIES.keys()),
        default='agent_evaluation',
        help='Strategy for loading source context files (default: agent_evaluation)'
    )

    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Enable verbose logging'
    )

    args = parser.parse_args()

    # Set log level
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    try:
        # Load teacher samples
        logger.info("=" * 80)
        logger.info("INTELLIGENT TEST DATA GENERATOR")
        logger.info("=" * 80)

        teacher_samples = []
        if args.teacher_samples:
            logger.info(f"\nStep 1a: Loading teacher samples from {args.teacher_samples}")
            teacher_samples = load_teacher_samples(args.teacher_samples)
            if not teacher_samples:
                logger.error("No teacher samples found!")
                sys.exit(1)
        else:
            logger.info("\nStep 1a: No teacher samples provided - will generate from source context only")

        # Load source context (always required)
        logger.info(f"\nStep 1b: Loading source context from {args.source_context}")
        loader = ContextLoader(strategy=args.loading_strategy)
        source_context = loader.load(args.source_context)

        if not source_context:
            logger.error("ERROR: Failed to load source context!")
            logger.error("  Source context is required for domain understanding.")
            sys.exit(1)

        # Create output directory
        output_path = Path(args.output)
        output_path.mkdir(parents=True, exist_ok=True)
        logger.info(f"Output directory: {output_path}")

        # Initialize generator
        generator = IntelligentTestGenerator(
            region_name=args.region,
            model_id=args.model_id,
            temperature=args.temperature
        )

        if args.analyze_only:
            # Just analyze and save
            logger.info("\nAnalyzing domain (analysis-only mode)...")
            analyzer = DomainAnalyzer(
                args.region,
                args.model_id,
                use_two_pass_analysis=args.use_two_pass_analysis
            )
            analysis = analyzer.analyze_test_samples(teacher_samples, source_context)

            analysis_file = output_path / "domain_analysis.json"
            analyzer.save_analysis(analysis, str(analysis_file))

            logger.info(f"\n{'=' * 80}")
            logger.info("ANALYSIS COMPLETE")
            logger.info(f"{'=' * 80}")
            logger.info(f"\nDomain Analysis saved to: {analysis_file}")
            logger.info(f"\nKey Findings:")
            logger.info(f"  - Domain: {analysis['domain_understanding'].get('domain_description', 'N/A')}")
            logger.info(f"  - Capabilities: {len(analysis['domain_understanding'].get('core_capabilities', []))}")
            logger.info(f"  - User Personas: {len(analysis['domain_understanding'].get('user_personas', []))}")
            logger.info(f"  - Complexity Levels: {list(analysis['complexity_distribution']['distribution'].keys())}")

        else:
            # Generate tests
            logger.info(f"\nGenerating {args.count} test cases...")
            logger.info(f"  - Complexity: {args.complexity or 'mixed'}")
            logger.info(f"  - Diversity: {args.diversity}")
            logger.info(f"  - Deduplication: {'disabled' if args.no_deduplicate else 'enabled'}")
            logger.info(f"  - Ensure complex: {'disabled' if args.no_ensure_complex else 'enabled (20%)'}")
            logger.info(f"  - Model: {args.model_id}")

            generated_tests = generator.generate_test_cases(
                teacher_samples=teacher_samples,
                count=args.count,
                source_context=source_context,
                complexity=args.complexity,
                diversity_factor=args.diversity,
                output_dir=str(output_path),
                deduplicate=not args.no_deduplicate,
                ensure_complex_tests=not args.no_ensure_complex
            )

            logger.info(f"\n{'=' * 80}")
            logger.info("GENERATION COMPLETE")
            logger.info(f"{'=' * 80}")
            logger.info(f"\nGenerated {len(generated_tests)} test cases")
            logger.info(f"Output directory: {output_path}")
            logger.info(f"\nFiles created:")
            logger.info(f"  - domain_analysis.json (domain understanding)")
            logger.info(f"  - all_generated_tests.json (all tests in one file)")
            logger.info(f"  - generated_test_001.json, ... (individual test files)")

            # Print summary
            complexity_counts = {}
            for test in generated_tests:
                comp = test.get('complexity', 'unknown')
                complexity_counts[comp] = complexity_counts.get(comp, 0) + 1

            logger.info(f"\nComplexity distribution:")
            for comp, count in sorted(complexity_counts.items()):
                logger.info(f"  - {comp}: {count}")

            # Print some example test names
            logger.info(f"\nExample test names:")
            for i, test in enumerate(generated_tests[:5]):
                logger.info(f"  {i+1}. {test.get('name', 'Unnamed')}")

        logger.info(f"\n{'=' * 80}")
        logger.info("SUCCESS")
        logger.info(f"{'=' * 80}\n")

    except KeyboardInterrupt:
        logger.info("\nWARN: Interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.exception("FAIL: Generation failed")
        sys.exit(1)


if __name__ == '__main__':
    main()
