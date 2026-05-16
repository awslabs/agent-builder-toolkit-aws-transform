# Test Data Generator - Testing Guide

## Test Overview

The test data generator now has comprehensive unit test coverage (22 tests) covering core functionality without requiring AWS credentials.

## Running Tests

### Quick Smoke Test (No Dependencies)
```bash
# Run basic smoke tests - validates core functionality
python3 evaluation/test_data_generator/test_basic.py
```

### Full Unit Test Suite
```bash
# Run all unit tests with pytest
pytest evaluation/test_data_generator/test_units.py -v

# Run with coverage report
pytest evaluation/test_data_generator/test_units.py --cov=evaluation.test_data_generator --cov-report=term-missing
```

### Run Specific Test Classes
```bash
# Test only ContextLoader
pytest evaluation/test_data_generator/test_units.py::TestContextLoader -v

# Test only Deduplication
pytest evaluation/test_data_generator/test_units.py::TestDeduplication -v

# Test only DomainAnalyzer
pytest evaluation/test_data_generator/test_units.py::TestDomainAnalyzer -v
```

## Test Coverage Summary

### TestContextLoader (10 tests)
Tests the configurable context loading system:
- Strategy initialization and fallback behavior
- Binary file detection
- Single file and directory loading
- Skip patterns (directories, large files)
- Custom strategy creation
- Predefined strategy availability

### TestDeduplication (4 tests)
Tests the deduplication algorithms:
- `keep_first` - Keep first occurrence of duplicates
- `keep_best` - Keep test with most assertions
- `keep_all_unique` - Rename duplicates to make unique
- No duplicates case

### TestDomainAnalyzer (5 tests)
Tests structural analysis (no API calls):
- Structural pattern extraction from test samples
- Complexity distribution analysis
- Assertion pattern analysis
- Default structure generation
- Empty sample handling

### TestCustomStrategyCreation (3 tests)
Tests custom strategy helper functions:
- Basic custom strategy creation
- Priority pattern configuration
- File size limits

## Test Structure

```
test_data_generator/
├── test_basic.py       # Smoke tests (can run as script)
├── test_units.py       # Comprehensive unit tests (pytest)
└── TEST_README.md      # This file
```

## What's Tested

✅ **Context Loading** (~200 lines)
- File discovery and filtering
- Priority-based file selection
- Strategy configuration
- Binary file detection

✅ **Deduplication** (~100 lines)
- Name-based duplicate detection
- Multiple deduplication strategies
- Assertion merging logic

✅ **Domain Analysis** (structural parts)
- Pattern extraction from test samples
- Complexity distribution calculation
- Assertion type cataloging
- Field and metadata analysis

## What's NOT Tested (Requires AWS/Bedrock)

❌ **LLM API Calls**
- Domain understanding generation (requires Bedrock)
- Test case generation (requires Bedrock)
- Two-pass analysis (requires Bedrock)

These are integration-level features that require actual AWS Bedrock API access and are validated through end-to-end testing.

## Writing New Tests

When adding new testable functionality:

1. Add unit tests to `test_units.py` if the logic is **deterministic** (no API calls, no randomness)
2. Use mocking (`unittest.mock`) for external dependencies (boto3, file system)
3. Use temp directories for file I/O tests (see `TestDeduplication` for examples)
4. Keep tests **fast** - all 22 tests run in ~0.1 seconds

Example test structure:
```python
class TestNewFeature(unittest.TestCase):
    def setUp(self):
        """Set up test fixtures."""
        # Create temp files, mock dependencies, etc.
        
    def tearDown(self):
        """Clean up after tests."""
        # Remove temp files, stop patches, etc.
        
    def test_feature_works(self):
        """Test that feature behaves correctly."""
        # Arrange, Act, Assert
```

## CI/CD Integration

To integrate into CI/CD pipelines:

```bash
# Run tests and fail on any failures
pytest evaluation/test_data_generator/test_units.py --tb=short || exit 1

# Run with coverage threshold
pytest evaluation/test_data_generator/test_units.py \
    --cov=evaluation.test_data_generator \
    --cov-fail-under=70
```

## Common Issues

**Import errors when running test_basic.py directly:**
- Ensure you run from the package root: `cd agent-builder-toolkit-aws-transform && python3 evaluation/test_data_generator/test_basic.py`

**boto3 errors in test_units.py:**
- The tests mock boto3, but ensure the import path matches your code structure
- Check that the patch decorator targets the correct module path

**File system race conditions:**
- Tests use temp directories that are cleaned up automatically
- If tests fail mid-run, temp files may remain in `/tmp/tmp*`
