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


def load_source_context(path: str) -> str:
    """Load source context file(s) if provided.

    Supports:
    - Single file: /path/to/POWER.md (any readable text file)
    - Directory: /path/to/context_dir/ (loads all text files recursively)

    Uses inverse filtering: loads all text files except known binaries.
    This automatically handles any source code format (new languages, DSLs, steering files).
    """
    if not path:
        return None

    path_obj = Path(path)
    if not path_obj.exists():
        logger.warning(f"Source context not found at {path}, proceeding without it")
        return None

    def is_text_file(filepath: Path) -> bool:
        """Check if file is text by checking for null bytes."""
        try:
            with open(filepath, 'rb') as f:
                sample = f.read(512)
            return b'\x00' not in sample  # Null byte indicates binary
        except Exception:
            return False

    contents = []

    if path_obj.is_file():
        # Single file - try to read it as text
        try:
            with open(path_obj, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            logger.info(f"Loaded source context from {path_obj.name} ({len(content)} chars)")
            return content
        except Exception as e:
            logger.warning(f"Failed to load {path_obj}: {e}")
            return None

    elif path_obj.is_dir():
        # Directory - load all text files with smart prioritization

        # Skip these directories
        SKIP_DIRS = {
            '.git', '__pycache__', 'node_modules', '.venv', 'venv',
            'build', 'dist', 'target', '.pytest_cache', '.mypy_cache',
            'coverage', '.tox', '.eggs', '*.egg-info'
        }

        # Skip known binary extensions
        BINARY_EXTS = {
            '.pyc', '.so', '.dll', '.exe', '.bin', '.obj', '.o', '.a',
            '.zip', '.tar', '.gz', '.bz2', '.xz', '.7z', '.rar',
            '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.ico', '.svg',
            '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx',
            '.mp3', '.mp4', '.avi', '.mov', '.wav', '.whl', '.jar'
        }

        # Known important filenames (entry points, documentation)
        IMPORTANT_FILES = {
            # Entry points
            'main.py', 'main.js', 'main.ts', 'index.py', 'index.js', 'index.ts',
            '__init__.py', '__main__.py', 'app.py', 'server.py',
            # Documentation/steering
            'power.md', 'readme.md', 'claude.md', 'instructions.md',
            # Package definitions
            'package.json', 'setup.py', 'pyproject.toml', 'cargo.toml',
            'go.mod', 'composer.json', 'pom.xml'
        }

        # Collect all text files with priority scoring
        file_priorities = []

        for file_path in path_obj.rglob('*'):
            # Skip if not a file
            if not file_path.is_file():
                continue

            # Skip if in excluded directory
            if any(skip_dir in file_path.parts for skip_dir in SKIP_DIRS):
                continue

            # Skip if known binary extension
            if file_path.suffix.lower() in BINARY_EXTS:
                continue

            # Skip very large files (>100KB)
            try:
                file_size = file_path.stat().st_size
                if file_size > 100 * 1024:
                    logger.debug(f"  - Skipped {file_path.name} (too large: {file_size} bytes)")
                    continue
            except Exception:
                continue

            # Check if it's text content
            if not is_text_file(file_path):
                continue

            # Calculate priority using objective signals (not keyword guessing)
            filename_lower = file_path.name.lower()
            suffix_lower = file_path.suffix.lower()
            rel_path = file_path.relative_to(path_obj)
            depth = len(rel_path.parts) - 1

            # Start with neutral score
            priority = 0

            # Signal 1: Known important files (explicit list)
            if filename_lower in IMPORTANT_FILES:
                priority += 1000

            # Signal 2: File type (objective categorization)
            if suffix_lower in {'.md', '.txt', '.rst', '.adoc', '.asciidoc'}:
                priority += 100  # Documentation
            elif suffix_lower in {'.yaml', '.yml', '.json', '.toml', '.ini'}:
                priority += 80   # Configuration
            else:
                priority += 60   # Source code

            # Signal 3: Depth (root files are architectural)
            priority -= depth * 30

            # Signal 4: Size (smaller = higher signal/noise ratio)
            try:
                if file_size < 2 * 1024:      # <2KB: likely config/import
                    priority += 40
                elif file_size < 10 * 1024:   # <10KB: concise, focused
                    priority += 20
                elif file_size > 50 * 1024:   # >50KB: verbose, may be generated
                    priority -= 20
            except Exception as e:
                # Best-effort scoring: if size-based adjustment fails, keep base priority.
                logger.debug(f"Failed to apply size-based priority adjustment for {file_path}: {e}")

            # Signal 5: Directory name hints (objective, not filename guessing)
            path_parts_str = str(rel_path).lower()
            if any(d in path_parts_str for d in ['test', 'tests', '__test__', 'spec']):
                priority -= 50  # Tests are verbose
            elif any(d in path_parts_str for d in ['example', 'examples', 'demo', 'sample']):
                priority -= 30  # Examples can be noisy
            elif any(d in path_parts_str for d in ['vendor', 'third_party', 'external']):
                priority -= 100  # Dependencies are irrelevant

            file_priorities.append((priority, file_path))

        # Sort by priority (highest first)
        file_priorities.sort(key=lambda x: x[0], reverse=True)
        text_files = [fp for _, fp in file_priorities]

        if not text_files:
            logger.warning(f"No text files found in {path}")
            return None

        # Load all files
        current_size = 0
        files_loaded = 0

        for text_file in text_files:
            try:
                with open(text_file, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()

                # Skip empty files
                if not content.strip():
                    continue

                # Use relative path from base directory for clarity
                rel_path = text_file.relative_to(path_obj)
                contents.append(f"# File: {rel_path}\n\n{content}")
                logger.info(f"  - Loaded {rel_path} ({len(content)} chars)")

                current_size += len(content)
                files_loaded += 1

            except Exception as e:
                logger.warning(f"Failed to load {text_file}: {e}")

        if not contents:
            logger.warning(f"No files successfully loaded from {path}")
            return None

        combined = "\n\n" + "="*80 + "\n\n".join(contents)
        logger.info(f"Loaded {len(contents)} context files from {path} ({len(combined)} total chars)")

        # Info about truncation (happens in domain analyzer)
        if len(combined) > DomainAnalyzer.MAX_INSTRUCTION_CHARS:
            logger.info(
                f"Source context is comprehensive ({len(combined)} chars, ~{len(combined)//4} tokens). "
                f"Will be intelligently truncated to {DomainAnalyzer.MAX_INSTRUCTION_CHARS} chars (~{DomainAnalyzer.MAX_INSTRUCTION_CHARS//4} tokens) for analysis. "
                f"This is normal and ensures all files are considered during prioritization."
            )

        return combined

    else:
        logger.warning(f"Path {path} is neither file nor directory")
        return None


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
    --teacher-samples test_data/ \\
    --source-context /path/to/source/folder/ \\
    --count 20 \\
    --output generated_tests/

  # Generate with specific complexity and high diversity
  python -m test_data_generator.cli \\
    --teacher-samples test_data/onboarding_intermediate.json \\
    --source-context /path/to/source/folder/ \\
    --count 10 \\
    --complexity medium \\
    --diversity 0.9 \\
    --output generated_tests/

  # Just analyze domain without generating
  python -m test_data_generator.cli \\
    --teacher-samples test_data/ \\
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
        logger.info("✅ SUCCESS")
        logger.info(f"{'=' * 80}\n")

    except KeyboardInterrupt:
        logger.info("\n⚠️  Interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.exception("❌ Generation failed")
        sys.exit(1)


if __name__ == '__main__':
    main()
