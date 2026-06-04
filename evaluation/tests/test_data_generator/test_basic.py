# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Basic smoke tests for the intelligent test generator."""

import json
import sys
from pathlib import Path

from test_data_generator.domain_analyzer import DomainAnalyzer

def run_smoke_tests():
    """Run basic smoke tests without AWS credentials."""
    print("Running basic smoke tests (no AWS required)...\n")

    # Test that we can load a test sample (tests/test_data_generator/ → up 2 = evaluation/)
    test_data_dir = Path(__file__).resolve().parent.parent.parent / "test_samples"
    test_file = test_data_dir / "onboarding_intermediate.json"

    if test_file.exists():
        with open(test_file, 'r') as f:
            samples = json.load(f)
        print(f"PASS: Loaded {len(samples)} test samples from {test_file.name}")
    else:
        print(f"FAIL: Test file not found: {test_file}")
        return False

    # Create analyzer with mock credentials (won't make API calls for these methods)
    try:
        analyzer = DomainAnalyzer(
            region_name='us-west-2',
            model_id='us.anthropic.claude-opus-4-5-20251101-v1:0'
        )
        print(f"PASS: DomainAnalyzer initialized")
    except Exception as e:
        print(f"WARN: DomainAnalyzer init warning (may need AWS config): {e}")
        print("   Continuing with structural tests...")

    # Test structural pattern extraction (no API call)
    try:
        patterns = analyzer._extract_structural_patterns(samples)
        print(f"PASS: Structural analysis works")
        print(f"   - Found {len(patterns['fields'])} field types")
        print(f"   - Found {len(patterns['metadata_keys'])} metadata keys")
        print(f"   - Found {len(patterns['assertion_types'])} assertion types")
    except Exception as e:
        print(f"FAIL: Structural analysis failed: {e}")
        import traceback
        traceback.print_exc()
        return False

    # Test complexity analysis (no API call)
    try:
        complexity_analysis = analyzer._analyze_complexity(samples)
        print(f"PASS: Complexity analysis works")
        print(f"   - Distribution: {complexity_analysis['distribution']}")
    except Exception as e:
        print(f"FAIL: Complexity analysis failed: {e}")
        import traceback
        traceback.print_exc()
        return False

    # Test assertion analysis (no API call)
    try:
        assertion_analysis = analyzer._analyze_assertions(samples)
        print(f"PASS: Assertion analysis works")
        print(f"   - Assertion types: {list(assertion_analysis['assertion_types'].keys())}")
    except Exception as e:
        print(f"FAIL: Assertion analysis failed: {e}")
        import traceback
        traceback.print_exc()
        return False

    print("\n" + "=" * 60)
    print("PASS: ALL BASIC SMOKE TESTS PASSED")
    print("=" * 60)
    print("\nThe test data generator is ready to use!")
    print("\nTo generate tests (requires AWS/Bedrock):")
    print("  python -m test_data_generator.cli --help")
    print("\nTo run full unit tests:")
    print("  pytest evaluation/tests/test_data_generator/")
    return True

if __name__ == '__main__':
    success = run_smoke_tests()
    sys.exit(0 if success else 1)
