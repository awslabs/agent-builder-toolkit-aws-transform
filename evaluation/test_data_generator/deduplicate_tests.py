#!/usr/bin/env python3
"""Deduplicate generated test cases based on name similarity."""

import json
import argparse
import sys
from pathlib import Path
from collections import defaultdict

def deduplicate_tests(input_file: str, output_file: str, strategy: str = "keep_first"):
    """Deduplicate tests based on name.

    Args:
        input_file: Input JSON file with all tests
        output_file: Output JSON file with deduplicated tests
        strategy: "keep_first", "keep_best", or "keep_all_unique"
    """
    # Load tests
    with open(input_file, 'r') as f:
        tests = json.load(f)

    print(f"Loaded {len(tests)} tests")

    # Group by name
    by_name = defaultdict(list)
    for test in tests:
        by_name[test['name']].append(test)

    # Find duplicates
    duplicates = {name: tests for name, tests in by_name.items() if len(tests) > 1}
    unique_names = {name: tests for name, tests in by_name.items() if len(tests) == 1}

    print(f"\nFound:")
    print(f"  - {len(unique_names)} unique test names")
    print(f"  - {len(duplicates)} duplicate test names")
    print(f"  - {sum(len(tests) for tests in duplicates.values())} total duplicate tests")

    # Deduplicate
    deduplicated = []

    # Add unique tests
    for tests in unique_names.values():
        deduplicated.append(tests[0])

    # Handle duplicates based on strategy
    if strategy == "keep_first":
        print(f"\nStrategy: Keep first instance of each duplicate")
        for name, tests in duplicates.items():
            deduplicated.append(tests[0])
            print(f"  - '{name}': keeping 1 of {len(tests)}")

    elif strategy == "keep_best":
        print(f"\nStrategy: Keep test with most assertions")
        for name, tests in duplicates.items():
            # Sort by number of assertions (descending)
            sorted_tests = sorted(tests, key=lambda t: len(t.get('assertions', [])), reverse=True)
            best = sorted_tests[0]
            deduplicated.append(best)
            print(f"  - '{name}': keeping test with {len(best.get('assertions', []))} assertions (had {len(tests)} duplicates)")

    elif strategy == "keep_all_unique":
        print(f"\nStrategy: Keep all tests but rename duplicates")
        for name, tests in duplicates.items():
            for i, test in enumerate(tests):
                if i == 0:
                    deduplicated.append(test)
                else:
                    # Rename to make unique
                    test['name'] = f"{name} (variant {i+1})"
                    test['id'] = f"{test['id']}_v{i+1}"
                    deduplicated.append(test)
            print(f"  - '{name}': kept all {len(tests)} with unique names")

    # Sort by ID for consistency
    deduplicated.sort(key=lambda t: t['id'])

    # Save
    with open(output_file, 'w') as f:
        json.dump(deduplicated, f, indent=2)

    print(f"\nSaved {len(deduplicated)} deduplicated tests to {output_file}")
    print(f"Reduction: {len(tests)} → {len(deduplicated)} ({len(tests) - len(deduplicated)} removed)")

    # Print summary
    print(f"\n{'='*60}")
    print("Deduplication Summary")
    print(f"{'='*60}")
    print(f"Original tests:       {len(tests)}")
    print(f"Unique tests:         {len(deduplicated)}")
    print(f"Tests removed:        {len(tests) - len(deduplicated)}")
    print(f"Reduction:            {(len(tests) - len(deduplicated)) / len(tests) * 100:.1f}%")

    # Complexity distribution
    complexity_dist = {}
    for test in deduplicated:
        comp = test.get('complexity', 'unknown')
        complexity_dist[comp] = complexity_dist.get(comp, 0) + 1

    print(f"\nComplexity distribution:")
    for comp, count in sorted(complexity_dist.items()):
        print(f"  - {comp}: {count}")

    return deduplicated


def main():
    parser = argparse.ArgumentParser(
        description="Deduplicate generated test cases",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Keep first instance of each duplicate (default)
  python deduplicate_tests.py --input all_generated_tests.json --output deduplicated_tests.json

  # Keep test with most assertions
  python deduplicate_tests.py --input all_generated_tests.json --output deduplicated_tests.json --strategy keep_best

  # Keep all tests but rename duplicates
  python deduplicate_tests.py --input all_generated_tests.json --output deduplicated_tests.json --strategy keep_all_unique
        """
    )

    parser.add_argument(
        '--input',
        required=True,
        help='Input JSON file with all generated tests'
    )

    parser.add_argument(
        '--output',
        required=True,
        help='Output JSON file for deduplicated tests'
    )

    parser.add_argument(
        '--strategy',
        choices=['keep_first', 'keep_best', 'keep_all_unique'],
        default='keep_first',
        help='Deduplication strategy (default: keep_first)'
    )

    args = parser.parse_args()

    # Validate input exists
    if not Path(args.input).exists():
        print(f"Error: Input file not found: {args.input}")
        return 1

    # Deduplicate
    deduplicate_tests(args.input, args.output, args.strategy)

    return 0


if __name__ == '__main__':
    sys.exit(main())
