# Evaluation Infrastructure

This directory contains tools and test data for evaluating AWS Transform agents and their capabilities.

## Overview

The evaluation infrastructure consists of:
1. **Test Data Generator** - Intelligent test case generation from teacher samples and source context
2. **Test Samples** - Curated test cases for agent evaluation
3. **Evaluation Framework** *(Coming Soon)* - Automated test execution and scoring

## Directory Structure

```
evaluation/
├── README.md                    # This file
├── pyproject.toml               # Package configuration (setuptools)
├── test_data_generator/         # Intelligent test case generator
│   ├── README.md               # Complete documentation
│   ├── cli.py                  # Command-line interface
│   ├── intelligent_generator.py # Main generation logic
│   ├── domain_analyzer.py      # Domain understanding from samples
│   ├── context_loader.py       # Source context loading strategies
│   ├── deduplicate_tests.py    # Deduplication utilities
│   ├── example.py              # Usage examples
│   ├── test_basic.py           # Smoke tests
│   └── test_units.py           # Unit test suite (22 tests)
├── test_samples/                # Sample test cases
│   └── onboarding_intermediate.json
└── generated_test_data/         # Generated tests (gitignored)
```

## Components

### 1. Test Data Generator

**Purpose:** Generate diverse, high-quality test cases for agent evaluation.

**Key Features:**
- Learns from teacher samples to understand domain patterns
- Analyzes source context (skills, code, documentation)
- Generates tests with controlled diversity
- Ensures complexity distribution (simple, medium, complex)
- Automatic deduplication
- Configurable loading strategies for different domains

**Quick Start:**
```bash
# Generate 20 test cases from source context only
python -m evaluation.test_data_generator.cli \
  --source-context /path/to/agent/code/ \
  --count 20 \
  --output generated_tests/

# Generate with teacher samples + source context
python -m evaluation.test_data_generator.cli \
  --teacher-samples evaluation/test_samples/ \
  --source-context /path/to/agent/code/ \
  --count 20 \
  --output generated_tests/

# High diversity generation for edge cases
python -m evaluation.test_data_generator.cli \
  --source-context /path/to/agent/code/ \
  --count 10 \
  --diversity 0.95 \
  --output edge_cases/
```

**Requirements:**
- Python 3.11+
- AWS credentials with Bedrock access
- boto3 installed

**Documentation:**
- [Generator README](test_data_generator/README.md) - Complete guide (usage, architecture, testing)

**Testing:**
```bash
# Run smoke tests (no AWS required)
python3 evaluation/test_data_generator/test_basic.py

# Run full unit test suite
pytest evaluation/test_data_generator/test_units.py -v
```

### 2. Test Samples

**Purpose:** An example of test cases demonstrating expected agent behavior.

**Current Samples:**
- `test_samples/onboarding_intermediate.json` - Intermediate user onboarding scenario

**Test Case Schema:**
```json
{
  "id": "unique-test-id",
  "name": "Human-readable test name",
  "user_message": "Initial prompt to agent",
  "description": "What this test validates",
  "complexity": "simple|medium|complex",
  "tags": ["category", "type"],
  "max_turns": 12,
  "timeout_seconds": 600,
  "simulated_human_guidance": "Persona and behavior for simulated user",
  "metadata": {
    "domain": "agent_builder",
    "scenario_type": "onboarding"
  },
  "assertions": [
    {
      "name": "assertion_name",
      "type": "llm_judge|tool_called|transcript_contains|transcript_not_contains",
      "description": "What this checks",
      "check": "Evaluation criteria or pattern"
    }
  ]
}
```

**Assertion Types:**
- `llm_judge` - LLM evaluates if behavior meets criteria
- `tool_called` - Verifies specific tool was invoked
- `transcript_contains` - Pattern matching in transcript
- `transcript_not_contains` - Ensure pattern is absent

### 3. Evaluation Framework *(Coming Soon)*

**Planned Features:**
- Automated test execution against agents
- LLM-based assertion evaluation
- Scoring and metrics (pass rate, ...)
- Test result reporting (JSON, HTML, markdown)
- Integration with CI/CD pipelines

```

## Generating Test Data

### For Agent Evaluation
Generate diverse tests covering the agent's capabilities:

```bash
python -m evaluation.test_data_generator.cli \
  --source-context /path/to/agent/source/ \
  --count 50 \
  --diversity 0.8 \
  --output generated_tests/agent_eval/
```

### For Regression Testing
Generate tests with specific complexity:

```bash
python -m evaluation.test_data_generator.cli \
  --teacher-samples evaluation/test_samples/ \
  --source-context /path/to/agent/source/ \
  --count 30 \
  --complexity medium \
  --output generated_tests/regression/
```

### For Edge Case Discovery
Use high diversity to find edge cases:

```bash
python -m evaluation.test_data_generator.cli \
  --source-context /path/to/agent/source/ \
  --count 20 \
  --diversity 0.95 \
  --temperature 0.9 \
  --output generated_tests/edge_cases/
```

## Test Data Quality

The generator includes built-in quality controls:

✅ **Domain Understanding** - Analyzes source context to understand capabilities
✅ **Diversity Control** - `--diversity` parameter (0.0-1.0) controls novelty
✅ **Complexity Distribution** - Ensures mix of simple/medium/complex tests
✅ **Automatic Deduplication** - Removes duplicate test names
✅ **Structural Validation** - Ensures all required fields present
✅ **Assertion Quality** - Generates testable, specific assertions

## Configuration

### Loading Strategies

The context loader supports different strategies for different tasks:

- `agent_evaluation` (default) - Focus on instructions, capabilities, rules
- `api_analysis` - Prioritize API schemas, endpoints
- `code_understanding` - Focus on source code
- `architecture_review` - Prioritize design docs
- `configuration_audit` - Focus on config files
- `generic` - Balanced loading

```bash
python -m evaluation.test_data_generator.cli \
  --source-context /path/to/code/ \
  --loading-strategy code_understanding \
  --output generated_tests/
```

### Deduplication Strategies

When using `deduplicate_tests.py`:

- `keep_first` - Keep first occurrence of each name
- `keep_best` - Keep test with most assertions
- `keep_all_unique` - Rename duplicates to make unique

```bash
python -m evaluation.test_data_generator.deduplicate_tests \
  --input generated_tests/all.json \
  --output generated_tests/unique.json \
  --strategy keep_best
```

## Development

### Running Tests

```bash
# Test data generator smoke tests
python3 evaluation/test_data_generator/test_basic.py

# Full unit test suite
pytest evaluation/test_data_generator/test_units.py -v

# With coverage
pytest evaluation/test_data_generator/test_units.py \
  --cov=evaluation.test_data_generator \
  --cov-report=term-missing
```

### Adding New Test Samples

1. Create a new JSON file in `test_samples/`
2. Follow the test case schema (see above)
3. Include diverse assertion types
4. Add simulated_human_guidance for reproducibility
5. Validate JSON syntax: `python -m json.tool test_samples/new_test.json`

## Common Workflows

### Workflow 1: Bootstrap Test Suite
Generate initial test suite from source code:

```bash
# 1. Generate diverse tests
python -m evaluation.test_data_generator.cli \
  --source-context /path/to/agent/ \
  --count 50 \
  --diversity 0.8 \
  --output bootstrap_tests/

# 2. Review and curate
# Manually review generated_tests/all_generated_tests.json
# Move high-quality tests to test_samples/

# 3. Use curated tests as teacher samples for refinement
python -m evaluation.test_data_generator.cli \
  --teacher-samples test_samples/ \
  --source-context /path/to/agent/ \
  --count 30 \
  --output refined_tests/
```


```bash
# Generate stable, deterministic tests
python -m evaluation.test_data_generator.cli \
  --teacher-samples test_samples/ \
  --source-context /path/to/agent/ \
  --count 40 \
  --diversity 0.5 \
  --temperature 0.7 \
  --output regression_suite/
```

## Roadmap

- [x] Intelligent test data generator
- [x] Context-aware test generation
- [x] Deduplication utilities
- [x] Comprehensive unit tests
- [ ] **Evaluation framework** - Automated test execution
- [ ] **Test runner** - Parallel test execution
- [ ] **Scoring engine** - Pass/fail with metrics
- [ ] **Results dashboard** - Visualization and reporting
- [ ] **CI/CD integration** - GitHub Actions workflow
- [ ] **Regression tracking** - Historical comparison

## Installation

Install the evaluation package:

```bash
# From agent-builder-toolkit-aws-transform/
cd evaluation
pip install -e .

# Or with test dependencies
pip install -e ".[test]"
```

**Requirements:**
- Python 3.11+
- boto3>=1.28.0 (AWS Bedrock access)
- AWS credentials configured
- pytest>=7.0.0 (for testing, optional)

## Contributing

When adding new capabilities:

1. **Document in source code** - Clear docstrings and comments
2. **Add unit tests** - Cover deterministic logic without AWS calls
3. **Update examples** - Add usage examples to `example.py`
4. **Update README** - Document new features and workflows

## Resources

- [Test Data Generator README](test_data_generator/README.md) - Complete documentation
- [Example Usage](test_data_generator/example.py) - Code examples

## Support

For issues or questions:
1. Check existing documentation in `test_data_generator/`
2. Run smoke tests to validate setup: `python3 evaluation/test_data_generator/test_basic.py`
3. Review examples: `evaluation/test_data_generator/example.py`

---

**Status:** Test data generation is complete and production-ready. Evaluation framework is planned for future development.
