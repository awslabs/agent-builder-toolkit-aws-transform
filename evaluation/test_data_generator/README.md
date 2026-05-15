# Intelligent Test Data Generator

Generate diverse, high-quality test cases by understanding your task domain and learning from teacher samples.

## Overview

This intelligent test generator solves the problem of limited test data by:

1. **Understanding your domain** - Analyzes source code/documentation and optional teacher test samples using LLM to extract domain patterns, capabilities, user personas, and success criteria
2. **Generating diverse tests** - Creates new test cases that explore different scenarios, edge cases, and complexity levels
3. **Maintaining quality** - Ensures generated tests follow proper structure and quality standards

**Key Feature**: Source context (code/docs) is **always required** for domain understanding. Teacher samples are optional - you can bootstrap from source code alone!

## Why Use This?

**Problem**: You need more test samples for agent evolution, but manually creating test cases is time-consuming and you want to ensure good coverage.

**Solution**: This generator learns from a small set of teacher samples and generates diverse, realistic test cases automatically.

## Features

- 🧠 **Domain Understanding**: Uses Claude to deeply understand what your tests validate
- 🎯 **Targeted Generation**: Generates tests covering different capabilities, personas, and scenarios  
- 🔄 **Diversity Control**: Tune how similar/different generated tests should be from teachers
- ✅ **Quality Validation**: Ensures generated tests have proper structure and valid assertions
- 📊 **Analysis Reports**: Provides insights into domain patterns and test coverage

## Quick Start

### 1. Bootstrap from Source Context (No Teacher Samples)

Generate tests directly from your source code without any teacher samples:

```bash
python -m test_data_generator.cli \
  --source-context /path/to/your/source/code/ \
  --count 20 \
  --output generated_tests/
```

The generator analyzes your source code, documentation, and configuration files to understand:
- What capabilities your system has
- What should be tested
- Appropriate test structures and assertions

### 2. Generate with Teacher Samples + Source Context

For best results, combine teacher samples with source context:

```bash
python -m test_data_generator.cli \
  --teacher-samples test_data/ \
  --source-context /path/to/your/source/code/ \
  --count 20 \
  --output generated_tests/
```

### 3. Advanced: Tune Complexity and Diversity

Generate specific complexity with high diversity:

```bash
python -m test_data_generator.cli \
  --teacher-samples test_data/ \
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
  --teacher-samples test_data/ \
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

Optional:
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

## How It Works

### Phase 1: Domain Analysis

The generator analyzes your teacher samples to extract:

- **Core capabilities** being tested
- **Domain-specific patterns** and scenarios
- **User personas** and interaction styles  
- **Success criteria** and quality expectations
- **Edge cases** and complexity factors
- **Assertion patterns** and what they validate

### Phase 2: Intelligent Generation

Using the domain understanding, it generates tests that:

- Follow the same structure as teacher samples
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

## Output Files

After generation, you'll find:

```
output_directory/
├── domain_analysis.json           # Domain understanding and patterns
├── all_generated_tests.json       # All tests in one file
├── generated_test_001.json        # Individual test files
├── generated_test_002.json
└── ...
```

## Integration with Evolution

Use generated tests with your evolution workflow:

```bash
# 1. Generate tests (source context always required)
python -m test_data_generator.cli \
  --source-context src/ \
  --teacher-samples test_data/ \
  --count 30 \
  --output test_data_expanded/

# 2. Update config to use expanded test data
# Edit examples/config.yaml:
#   test_data:
#     path: "test_data_expanded/"

# 3. Run evolution with more tests
python run_evolution.py \
  --config examples/config.yaml \
  --evolve \
  --auto-patch \
  --validation-method agent_judge \
  --mode standard  # Now uses expanded test set
```

## Diversity Control

The `--diversity` parameter controls how different generated tests are from teacher samples:

- **0.0 - 0.3**: Low diversity - Stay close to teacher patterns, mostly variations
- **0.4 - 0.6**: Medium diversity - Explore different aspects of core capabilities  
- **0.7 - 1.0**: High diversity - Explore edge cases, error handling, unusual scenarios

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

## Programmatic Usage

You can also use the generator in your Python code. **Note**: `source_context` is always required.

### Bootstrap Without Teacher Samples

```python
from test_data_generator import IntelligentTestGenerator
from test_data_generator.context_loader import ContextLoader

# Load source context (required)
loader = ContextLoader(strategy='agent_evaluation')
source_context = loader.load('/path/to/your/source/')

generator = IntelligentTestGenerator(
    region_name=your_region,
    model_id=your_model,
    temperature=0.8
)

# Generate from source context only (no teacher samples)
generated = generator.generate_test_cases(
    teacher_samples=[],  # Empty list
    count=10,
    source_context=source_context,  # Required
    diversity_factor=0.8,
    output_dir='output/'
)

print(f"Generated {len(generated)} tests from source context")
```

### With Teacher Samples + Source Context

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

# Load teacher samples
teacher_samples = [...]  # Your test samples

# Generate with both teacher samples and source context
generated = generator.generate_test_cases(
    teacher_samples=teacher_samples,
    count=20,
    source_context=source_context,  # Required
    complexity='medium',
    diversity_factor=0.8,
    output_dir='output/'
)

print(f"Generated {len(generated)} tests")
```

## Requirements

- Python 3.11+
- boto3 (AWS Bedrock access)
- AWS credentials configured
- Access to Claude models in Bedrock

## Troubleshooting

**No tests generated**: Check that teacher samples have valid structure with assertions

**Low quality tests**: Try lowering diversity factor or providing POWER.md context

**Bedrock errors**: Verify AWS credentials and model access in your region

**Memory issues**: Reduce count or generate in smaller batches

**"Power instructions very large" warning**: 
- Tool auto-skips .git, node_modules, __pycache__, etc.
- Auto-skips files >100KB
- Content truncated to 10K chars for analysis
- Use specific file instead of full directory if needed

## Examples

See the [examples](../examples/) directory for sample configurations and generated tests.

## Architecture

```
test_data_generator/
├── __init__.py              # Package exports
├── cli.py                   # Command-line interface
├── domain_analyzer.py       # Domain understanding via LLM
├── intelligent_generator.py # Test generation logic
└── README.md               # This file
```

## Contributing

The generator is designed to be extensible. To customize:

1. Modify `domain_analyzer.py` to extract additional patterns
2. Adjust `intelligent_generator.py` prompts for your domain
3. Add custom validation logic for your test structure

## License

Same as parent project.
