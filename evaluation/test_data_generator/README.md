# Intelligent Test Data Generator

Generate diverse, high-quality test cases by understanding your task domain and learning from teacher samples.

## Table of Contents

- [Overview](#overview)
- [Quick Start](#quick-start)
- [Command-Line Options](#command-line-options)
- [How It Works](#how-it-works)
- [Programmatic Usage](#programmatic-usage)
- [Best Practices](#best-practices)
- [Troubleshooting](#troubleshooting)
- [Architecture](#architecture)
- [Testing](#testing)
- [Contributing](#contributing)

## Overview

This intelligent test generator solves the problem of limited test data by:

1. **Understanding your domain** - Analyzes source code/documentation and optional teacher test samples using LLM to extract domain patterns, capabilities, user personas, and success criteria
2. **Generating diverse tests** - Creates new test cases that explore different scenarios, edge cases, and complexity levels
3. **Maintaining quality** - Ensures generated tests follow proper structure and quality standards

**Key Feature**: Source context (code/docs) is **always required** for domain understanding. Teacher samples are optional - you can bootstrap from source code alone!

**Why Use This?**

- **Problem**: You need more test samples for agent evolution, but manually creating test cases is time-consuming
- **Solution**: This generator learns from a small set of teacher samples and generates diverse, realistic test cases automatically

## Quick Start

### 1. Bootstrap from Source Context (No Teacher Samples)

Generate tests directly from your source code without any teacher samples:

```bash
python -m test_data_generator.cli \
  --source-context /path/to/your/source/code/ \
  --count 20 \
  --output generated_tests/
```

### 2. Generate with Teacher Samples + Source Context

For best results, combine teacher samples with source context:

```bash
python -m test_data_generator.cli \
  --teacher-samples test_samples/ \
  --source-context /path/to/your/source/code/ \
  --count 20 \
  --output generated_tests/
```

### 3. Advanced: Tune Complexity and Diversity

```bash
python -m test_data_generator.cli \
  --teacher-samples test_samples/ \
  --source-context /path/to/source/folder/ \
  --count 15 \
  --complexity medium \
  --diversity 0.9 \
  --output generated_tests/
```

### 4. Domain Analysis Only

Analyze your domain without generating tests:

```bash
python -m test_data_generator.cli \
  --source-context /path/to/source/folder/ \
  --teacher-samples test_samples/ \
  --analyze-only \
  --output analysis/
```

## Command-Line Options

```
Required:
  --source-context PATH     Path to source code/docs directory or file
                           REQUIRED for domain understanding
  --output PATH            Output directory for generated tests

Optional:
  --teacher-samples PATH    Path to teacher test samples (file or directory)
                           Optional - can bootstrap from source context alone
  --count N                Number of tests to generate (default: 10)
  --complexity LEVEL       Generate specific complexity: simple, medium, or complex
  --diversity FACTOR       Diversity 0-1: 0=similar, 1=very diverse (default: 0.8)
  --region REGION          AWS region (default: us-west-2)
  --model-id MODEL         Bedrock model ID (default: claude-opus-4-5)
  --temperature TEMP       Generation temperature 0-1 (default: 0.8)
  --analyze-only           Only analyze domain, don't generate
  --no-deduplicate         Disable test name deduplication
  --no-ensure-complex      Disable ensuring 20% complex tests
  --use-two-pass-analysis  Use two-pass analysis for large source context
  --loading-strategy STR   Strategy for loading files (default: agent_evaluation)
  --verbose                Enable verbose logging
```

### Diversity Control

The `--diversity` parameter controls how different generated tests are:

- **0.0 - 0.3**: Low diversity - Stay close to patterns, mostly variations
- **0.4 - 0.6**: Medium diversity - Explore different aspects of core capabilities  
- **0.7 - 1.0**: High diversity - Explore edge cases, error handling, unusual scenarios

## How It Works

### Phase 1: Domain Analysis

The generator analyzes your source context and optional teacher samples to extract:

- **Core capabilities** being tested
- **Domain-specific patterns** and scenarios
- **User personas** and interaction styles  
- **Success criteria** and quality expectations
- **Edge cases** and complexity factors
- **Assertion patterns** and what they validate

### Phase 2: Intelligent Generation

Using the domain understanding, it generates tests that:

- Follow the same structure as teacher samples (or infer structure from source)
- Explore different scenarios and edge cases
- Cover different user personas and skill levels
- Maintain appropriate assertion quality
- Match desired complexity distribution

### Phase 3: Validation

Each generated test is validated to ensure:

- Required fields are present
- Assertions are valid and complete
- Structure matches teacher samples
- Reasonable defaults for timing/turns

### Output Files

After generation, you'll find:

```
output_directory/
├── domain_analysis.json           # Domain understanding and patterns
├── all_generated_tests.json       # All tests in one file
├── generated_test_001.json        # Individual test files
├── generated_test_002.json
└── ...
```

## Programmatic Usage

### Bootstrap Without Teacher Samples

```python
from test_data_generator import IntelligentTestGenerator
from test_data_generator.context_loader import ContextLoader

# Load source context (required)
loader = ContextLoader(strategy='agent_evaluation')
source_context = loader.load('/path/to/your/source/')

generator = IntelligentTestGenerator(
    region_name='us-west-2',
    model_id='us.anthropic.claude-opus-4-5-20251101-v1:0',
    temperature=0.8
)

# Generate from source context only
generated = generator.generate_test_cases(
    teacher_samples=[],  # Empty list
    count=10,
    source_context=source_context,  # Required
    diversity_factor=0.8,
    output_dir='output/'
)
```

### With Teacher Samples + Source Context

```python
# Load source context and teacher samples
loader = ContextLoader(strategy='agent_evaluation')
source_context = loader.load('/path/to/your/source/')
teacher_samples = [...]  # Your test samples

# Generate with both
generated = generator.generate_test_cases(
    teacher_samples=teacher_samples,
    count=20,
    source_context=source_context,
    complexity='medium',
    diversity_factor=0.8,
    output_dir='output/'
)
```

## Best Practices

### Always Required:
1. **Provide comprehensive source context**: Include documentation, code, configuration files
2. **Organize your source well**: Clear structure helps the analyzer understand your domain
3. **Include key files**: POWER.md, README, main entry points, core logic

### With Teacher Samples:
1. **Start with quality teachers**: Better teacher samples = better generated tests
2. **Start at 0.8 diversity**: Adjust based on results
3. **Review generated tests**: Spot-check first few generations
4. **Iterate**: Use domain analysis to understand coverage gaps

### Without Teacher Samples (Bootstrap):
1. **Start with lower count**: Generate 5-10 tests first to verify quality
2. **Review structure**: First-generation tests may need manual refinement
3. **Use refined tests as teachers**: Use generated tests as teacher samples for next round
4. **Iterate to improve**: Each generation learns from previous results

## Troubleshooting

**No tests generated**: Check that source context is provided and teacher samples (if used) have valid structure with assertions

**Low quality tests**: Try lowering diversity factor or providing more comprehensive source context

**Bedrock errors**: Verify AWS credentials and model access in your region

**Memory issues**: Reduce count or generate in smaller batches

**"Source context very large" warning**: 
- Tool auto-skips .git, node_modules, __pycache__, etc.
- Auto-skips files >100KB
- Content truncated intelligently for analysis
- Use specific file instead of full directory if needed

## Architecture

### System Overview

```
INPUT                          PROCESSING                       OUTPUT
─────                          ──────────                       ──────

┌──────────────┐              ┌────────────────────┐         ┌─────────────┐
│   Teacher    │              │  Domain Analyzer   │         │  Generated  │
│   Samples    │─────────────>│                    │         │   Tests     │
│  (optional)  │              │  • Extract patterns│         │ (10-50 tests)│
└──────────────┘              │  • Understand      │         └─────────────┘
                              │    capabilities    │
┌──────────────┐              │  • Identify personas│        ┌─────────────┐
│Source Context│─────────────>│  • Analyze         │        │   Domain    │
│  (required)  │              │    assertions      │        │  Analysis   │
└──────────────┘              └────────┬───────────┘        └─────────────┘
                                       │
                                       │ Domain Understanding
                                       │
                                       ▼
                              ┌────────────────────┐
                              │ Intelligent Gen.   │
                              │                    │
                              │  • Build prompts   │
                              │  • Generate batches│
                              │  • Ensure diversity│
                              │  • Validate output │
                              └────────┬───────────┘
                                       │
                                       ▼
                              ┌────────────────────┐
                              │   AWS Bedrock      │
                              │  (Claude Models)   │
                              └────────────────────┘
```

### Component Architecture

```
test_data_generator/
│
├── domain_analyzer.py
│   └─ DomainAnalyzer
│      ├─ analyze_test_samples()        # Phase 1: Understanding
│      ├─ _extract_structural_patterns()
│      ├─ _extract_domain_understanding()
│      ├─ _two_pass_analysis()
│      ├─ _smart_truncate()
│      └─ _call_bedrock()
│
├── intelligent_generator.py
│   └─ IntelligentTestGenerator
│      ├─ generate_test_cases()         # Phase 2: Generation
│      ├─ _generate_batch()
│      ├─ _build_generation_prompt()
│      ├─ _validate_and_fix_tests()
│      └─ _final_quality_pass()
│
├── context_loader.py
│   └─ ContextLoader
│      ├─ load()                        # Load source context
│      ├─ _discover_files()
│      └─ _prioritize_files()
│
└── cli.py
    ├─ main()                            # Command-line interface
    ├─ load_teacher_samples()
    └─ Argument parsing
```

### Key Design Decisions

**1. Two-Phase Approach (Analysis → Generation)**

*Why?* Separate understanding from generation, reusable domain analysis, better quality control

*Tradeoffs:* Two LLM calls instead of one, slightly slower but much better quality

**2. Batch Generation**

*Why?* Ensures diversity across batches, better progress tracking, fault tolerance

*Tradeoffs:* More API calls and complexity, but better results and reliability

**3. Validation & Auto-Fix**

*Why?* LLM output can be imperfect, ensures structural consistency, reduces manual cleanup

*Tradeoffs:* May mask generation issues, but much better usability

**4. Source Context Required, Teacher Samples Optional**

*Why?* Source context provides ground truth, enables bootstrapping without existing tests

*Tradeoffs:* More setup required, but more flexible and powerful

### Validation Pipeline

```
Generated Test
      │
      ▼
┌─────────────┐
│ Has ID?     │ ─No─> Generate ID
└──────┬──────┘
       │ Yes
       ▼
┌─────────────┐
│ Has name?   │ ─No─> Generate name
└──────┬──────┘
       │ Yes
       ▼
┌─────────────┐
│ Valid       │ ─No─> Set default
│ complexity? │
└──────┬──────┘
       │ Yes
       ▼
┌─────────────┐
│ Has         │ ─No─> Skip test
│ assertions? │
└──────┬──────┘
       │ Yes
       ▼
┌─────────────┐
│ Validate    │ ─Invalid─> Remove invalid
│ assertions  │
└──────┬──────┘
       │ Valid
       ▼
┌─────────────┐
│ Add to      │
│ output set  │
└─────────────┘
```

### Error Handling Strategy

**Level 1: Graceful Degradation**
- No teacher samples? Generate from source context alone
- Some tests invalid? Use valid ones
- Batch failed? Continue with others

**Level 2: Validation & Auto-Fix**
- Missing fields? Add defaults
- Invalid assertions? Remove them
- Wrong structure? Fix if possible

**Level 3: Clear Errors**
- No source context? Error & exit
- Bedrock unavailable? Error & exit
- All tests invalid? Error & exit

## Testing

### Running Tests

**Quick Smoke Test (No Dependencies)**
```bash
python3 evaluation/test_data_generator/test_basic.py
```

**Full Unit Test Suite**
```bash
# Run all unit tests
pytest evaluation/test_data_generator/test_units.py -v

# Run with coverage
pytest evaluation/test_data_generator/test_units.py \
  --cov=evaluation.test_data_generator \
  --cov-report=term-missing
```

**Run Specific Test Classes**
```bash
# Test only ContextLoader
pytest evaluation/test_data_generator/test_units.py::TestContextLoader -v

# Test only Deduplication
pytest evaluation/test_data_generator/test_units.py::TestDeduplication -v

# Test only DomainAnalyzer
pytest evaluation/test_data_generator/test_units.py::TestDomainAnalyzer -v
```

### Test Coverage Summary

**TestContextLoader (10 tests)**
- Strategy initialization and fallback behavior
- Binary file detection
- Single file and directory loading
- Skip patterns (directories, large files)
- Custom strategy creation

**TestDeduplication (4 tests)**
- `keep_first` - Keep first occurrence
- `keep_best` - Keep test with most assertions
- `keep_all_unique` - Rename duplicates
- No duplicates case

**TestDomainAnalyzer (5 tests)**
- Structural pattern extraction
- Complexity distribution analysis
- Assertion pattern analysis
- Default structure generation
- Empty sample handling

**TestCustomStrategyCreation (3 tests)**
- Basic custom strategy creation
- Priority pattern configuration
- File size limits

### What's Tested vs. Not Tested

**Tested (22 unit tests, ~0.1s runtime)**
- Context loading (~200 lines)
- Deduplication (~100 lines)
- Domain analysis (structural parts)
- File discovery and filtering
- Pattern extraction

**Not Tested (Requires AWS/Bedrock)**
- Domain understanding generation
- Test case generation
- Two-pass analysis
- LLM API calls

### CI/CD Integration

```bash
# Run tests and fail on any failures
pytest evaluation/test_data_generator/test_units.py --tb=short || exit 1

# Run with coverage threshold
pytest evaluation/test_data_generator/test_units.py \
    --cov=evaluation.test_data_generator \
    --cov-fail-under=70
```

## Contributing

The generator is designed to be extensible. To customize:

1. **Modify domain analysis**: Edit `domain_analyzer.py` to extract additional patterns
2. **Adjust generation**: Update `intelligent_generator.py` prompts for your domain
3. **Add validation**: Add custom validation logic for your test structure
4. **Create strategies**: Add new context loading strategies in `context_loader.py`

### Code Style

- Follow existing patterns for consistency
- Add docstrings for public methods
- Use type hints where appropriate
- Keep functions focused and small
- Add unit tests for deterministic logic

### Pull Request Guidelines

1. Ensure all tests pass
2. Add tests for new functionality
3. Update documentation as needed
4. Keep changes focused and atomic
5. Provide clear commit messages

### Writing New Tests

When adding new testable functionality:

1. Add unit tests to `test_units.py` if the logic is **deterministic**
2. Use mocking (`unittest.mock`) for external dependencies
3. Use temp directories for file I/O tests
4. Keep tests **fast**

Example:
```python
class TestNewFeature(unittest.TestCase):
    def test_feature_works(self):
        """Test that feature behaves correctly."""
        # Arrange, Act, Assert
```

## Installation

Install the evaluation package from the repository root:

```bash
# From agent-builder-toolkit-aws-transform/
cd evaluation
pip install -e .

# Or with test dependencies
pip install -e ".[test]"
```

## Requirements

- Python 3.11+
- boto3 (AWS Bedrock access)
- AWS credentials configured
- Access to Claude models in Bedrock

## License

Same as parent project.
