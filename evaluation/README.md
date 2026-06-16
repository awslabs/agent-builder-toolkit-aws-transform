# Evaluation Infrastructure

This directory contains tools and test data for evaluating AWS Transform agents and their capabilities.

## Overview

The evaluation infrastructure consists of:
1. **Test Data Generator** - Intelligent test case generation from teacher samples and source context
2. **Test Samples** - Curated test cases for agent evaluation
3. **Evaluation System** - Automated test execution and scoring (`src/eval_runner/`, with its ACP execution engine under `eval_runner/execution/`)

## Layout

Standard `src/` layout. The pieces worth knowing (the rest is discoverable from
the tree):

- **`src/eval_runner/`** — the evaluation library: the `list`/`run`/`report`/`clean`
  CLI, the pluggable `EvaluationEngine`, scoring `metrics/` (`assertion_pass_rate`
  + `llm_judge`), and the ACP execution engine under `execution/`. `validators/`
  is a separate evolution-safety layer, **not** wired into the evaluation pipeline.
- **`src/test_data_generator/`** — generates test cases from teacher samples and
  source context.
- **`src/run_eval.py`** — repo-specific wiring (the `agent-builder-eval` console
  script); builds the `EvalConfig` pointing at this repo's `agent_under_test/` and
  `test_samples/`.
- **`tests/`** — mirrors the `src/` package layout.
- **`test_samples/`, `agent_under_test/`** — repo data consumed at runtime; not
  packaged into the wheel.

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

Install the package first (`pip install -e evaluation/`), then:

```bash
# Generate 20 test cases from source context only
python -m test_data_generator.cli \
  --source-context /path/to/agent/code/ \
  --count 20 \
  --output generated_tests/

# Generate with teacher samples + source context
python -m test_data_generator.cli \
  --teacher-samples evaluation/test_samples/ \
  --source-context /path/to/agent/code/ \
  --count 20 \
  --output generated_tests/

# High diversity generation for edge cases
python -m test_data_generator.cli \
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
- [Generator README](src/test_data_generator/README.md) - Complete guide (usage, architecture, testing)

**Testing:**
```bash
# Run the generator smoke + unit tests
pytest evaluation/tests/test_data_generator/ -v
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

### 3. Evaluation System (`eval_runner/`)

A single package with internal layers. The top level holds the **scoring +
orchestration** layer (test-case model, pluggable metric registry, parallel
`EvaluationEngine`, canonical CLI). Its `execution/` subpackage is the **ACP
execution engine** that drives a multi-turn conversation with the agent under
test and grades transcripts with an LLM judge.

**Layers:**

| Layer | Where | Responsibility |
|-------|-------|----------------|
| Execution | `eval_runner.execution` (`EvalOrchestrator`) | Run the agent/skill over ACP → transcript |
| Scoring | `eval_runner` (`MetricRegistry`) | `assertion_pass_rate`, `tool_usage`, `error_handling`, `completeness` (deterministic) + `llm_judge` (LLM-as-judge) |
| Orchestration | `eval_runner.cli` + `execution/report.py` | Run many via `EvaluationEngine`, aggregate, HTML dashboard |

`eval_runner.ACPAgent` is the bridge: it converts a `TestCase` to an engine
scenario, runs it via `EvalOrchestrator.run_scenario()`, and flattens the
transcript into an `ExecutionResult` so any metric can score it. The CLI `run`
routes scenarios through `EvaluationEngine`; the `llm_judge` metric reuses the
engine's judge via `EvalOrchestrator.grade_transcript()`.

> The evolution layer (`eval_runner/validators/`) is intentionally separate and
> not wired into the evaluation pipeline here.

**Features:**
- Automated multi-turn execution against the agent under test
- Pluggable scoring: deterministic transcript/tool checks **and** LLM-as-judge,
  mixed per config (`metrics: ["assertion_pass_rate", "llm_judge"]`)
- Per-assertion pass/fail, pass rate, token usage
- Test result reporting (JSON results + HTML dashboard)
- CLI: `list` / `run` / `report` / `clean`

**Built-in metrics** (resolve by name in `metrics: [...]`; each scores 0–10 and
passes at ≥ 7.0, so they combine cleanly in one run):

| Metric | LLM? | What it scores | Per-test config (`metadata`) |
|--------|------|----------------|------------------------------|
| `assertion_pass_rate` | no | Fraction of deterministic assertions (`transcript_contains`, `output_contains`, `tool_called`) that pass | — (reads `assertions`) |
| `tool_usage` | no | Whether `expected_tools` were called and `forbidden_tools` were avoided | `expected_tools: [...]`, `forbidden_tools: [...]` |
| `error_handling` | no | Whether the transcript is free of a surfaced framework error (default marker: `ERROR:`) — error *absence*, not recovery quality | `error_markers: [...]` (optional override; replaces the default) |
| `completeness` | no | Whether the run reached its designed end (finished before exhausting `max_turns`) **and** the final output is non-empty | `completion_markers: [...]` (optional; requires an explicit substring instead of the turn-budget signal) |
| `llm_judge` | yes (Bedrock) | LLM-as-judge verdict over `llm_judge` assertions | — (reads `assertions`) |

`tool_usage` and `completeness` **abstain** (score 10.0 / pass) when they have no
signal to act on — `tool_usage` without `expected_tools`/`forbidden_tools`,
`completeness` without a tracked turn count or `completion_markers` — so they are
safe to enable globally and only "activate" when there's something to grade.
`error_handling` is always active (a transcript free of framework errors is the
universal expectation). Note `completeness` keys off the turn budget, **not** the
ACP engine's `__DONE__` sentinel, which the orchestrator consumes before it
reaches the transcript. Example test-case metadata:

```json
"metadata": {
  "expected_tools": ["keyword_search"],
  "forbidden_tools": ["delete_agent"]
}
```

**Custom metrics:** implement the `MetricInterface` (a `name` property and an
`evaluate(execution, test_case) -> MetricResult`) and register it:
`MetricRegistry().register("my_metric", MyMetric)`. See
`src/eval_runner/metrics/tool_usage.py` for a deterministic reference
implementation.

**Wiring for this repo** (`src/run_eval.py` + `agent_under_test/`):

```bash
# After `pip install -e evaluation/`, use the console script:
agent-builder-eval list
agent-builder-eval run --scenario onboarding-intermediate --report

# Or run the module directly:
python evaluation/src/run_eval.py list
python evaluation/src/run_eval.py run --scenario onboarding-intermediate --report
```

`run_eval.py` builds the unified `eval_runner.EvalConfig`. Its `framework_config`
points the ACP engine at the agent defined in `agent_under_test/` (AGENT.md +
mcp.json → the real `agent-builder` MCP server) and the scenarios in
`test_samples/`. The CLI delegates `list`/`run`/`report`/`clean` to the framework's
native implementation (so the HTML report is produced with zero fidelity loss).
The `list` command works offline; `run` drives a live conversation and needs
`kiro-cli` plus model access.

```

## Generating Test Data

### For Agent Evaluation
Generate diverse tests covering the agent's capabilities:

```bash
python -m test_data_generator.cli \
  --source-context /path/to/agent/source/ \
  --count 50 \
  --diversity 0.8 \
  --output generated_tests/agent_eval/
```

### For Regression Testing
Generate tests with specific complexity:

```bash
python -m test_data_generator.cli \
  --teacher-samples evaluation/test_samples/ \
  --source-context /path/to/agent/source/ \
  --count 30 \
  --complexity medium \
  --output generated_tests/regression/
```

### For Edge Case Discovery
Use high diversity to find edge cases:

```bash
python -m test_data_generator.cli \
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
python -m test_data_generator.cli \
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
python -m test_data_generator.deduplicate_tests \
  --input generated_tests/all.json \
  --output generated_tests/unique.json \
  --strategy keep_best
```

## Development

### Running Tests

```bash
# Full suite (eval_runner + test_data_generator)
pytest evaluation/

# Just the test data generator
pytest evaluation/tests/test_data_generator/ -v

# With coverage
pytest evaluation/tests/test_data_generator/ \
  --cov=test_data_generator \
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
python -m test_data_generator.cli \
  --source-context /path/to/agent/ \
  --count 50 \
  --diversity 0.8 \
  --output bootstrap_tests/

# 2. Review and curate
# Manually review generated_tests/all_generated_tests.json
# Move high-quality tests to test_samples/

# 3. Use curated tests as teacher samples for refinement
python -m test_data_generator.cli \
  --teacher-samples test_samples/ \
  --source-context /path/to/agent/ \
  --count 30 \
  --output refined_tests/
```


```bash
# Generate stable, deterministic tests
python -m test_data_generator.cli \
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
- [x] **Evaluation framework** - Automated multi-turn test execution (ACP)
- [x] **Test runner** - Parallel test execution (`EvaluationEngine`)
- [x] **Scoring engine** - Pass/fail with metrics (`assertion_pass_rate`, `llm_judge`)
- [x] **Results dashboard** - HTML visualization and reporting
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

# For the evolution verbs (insights / evolve / review / evohistory), install the
# evolve extra. It pulls in the sibling harness-evolver package (../evolution)
# via [tool.uv.sources], so install it with uv (plain pip can't resolve a local
# path extra):
uv pip install -e ".[evolve]"
```

**Requirements:**
- Python 3.11+
- boto3>=1.28.0 (AWS Bedrock access)
- AWS credentials configured
- pytest>=7.0.0 (for testing, optional)
- For the `evolve` extra: [`uv`](https://docs.astral.sh/uv/) (resolves the local
  `harness-evolver` path dependency) + `kiro-cli` on PATH for live runs

## Contributing

When adding new capabilities:

1. **Document in source code** - Clear docstrings and comments
2. **Add unit tests** - Cover deterministic logic without AWS calls
3. **Update examples** - Add usage examples to `example.py`
4. **Update README** - Document new features and workflows

## Resources

- [Test Data Generator README](src/test_data_generator/README.md) - Complete documentation
- [Example Usage](src/test_data_generator/example.py) - Code examples

## Support

For issues or questions:
1. Check existing documentation in `src/test_data_generator/`
2. Run the test suite to validate setup: `pytest evaluation/tests/test_data_generator/`
3. Review examples: `evaluation/src/test_data_generator/example.py`

---

**Status:** Test data generation and the evaluation system (multi-turn ACP
execution, pluggable scoring, HTML reporting) are complete. CI/CD integration and
regression tracking are the remaining roadmap items.
