# HarnessEvolver — self-improvement loop for the agent under test

This directory is a **self-improvement loop** for the **AWS Transform
agent-builder** agent. Where the sibling `../evaluation/` framework only
*measures* the agent, this loop *improves* it: it runs the agent on eval
scenarios, diagnoses why it fails, edits the agent's own definition to fix the
failure mechanisms, and repeats — keeping a held-out test set honest the whole
way, exactly like a machine-learning training run.

The Python package (`harness_evolver`, under [`src/`](src/harness_evolver/)) is
**engine-agnostic**: it drives any `Environment` whose
`run(target_dir, artifacts_dir)` callback evaluates the current target and
leaves an `evaluation_summary.json` behind. In this repo that callback drives
the in-repo evaluation framework (`../evaluation/src/eval_runner`), so
**evolution and plain evaluation share one engine** and can never diverge.

---

## Where this fits: the full lifecycle

Evolution is the last stage of a single lifecycle that runs behind one command,
`agent-builder-eval` (defined in `../evaluation/src/cli.py`). You generate test
data, measure the agent against it, then evolve the agent — all on the same
engine and scenarios:

| Stage | Verb | Does | Backed by |
|-------|------|------|-----------|
| **Generate** | `generate` | Synthesize diverse eval scenarios from teacher samples + source context | `test_data_generator` |
| **Inspect** | `list` | List the scenarios in a suite (`--test-dir`) | `eval_runner` |
| **Measure** | `run` | Run scenarios against the agent under test (ACP + LLM judge) | `eval_runner` engine |
| **Report** | `report` | Build the HTML results dashboard | `eval_runner` |
| **Diagnose** | `insights` | Root-cause a finished run — mechanisms + citations → `report.md` | `harness_evolver.analyst` |
| **Improve** | `evolve` | Self-improve the agent: measure → diagnose → edit → snapshot, with early stopping + best-checkpoint selection | `harness_evolver.Orchestrator` |
| **Review** | `review` | PR-style per-step diff of everything an evolution run changed | `git` over `snapshots.git` |
| **Trace** | `evohistory` | Surface a run's cumulative `evolution_history.md` | `harness_evolver` |

```bash
# A typical end-to-end pass (run from ../evaluation/, env set up there):
agent-builder-eval generate --source-context /path/to/agent/ --count 30 --output generated_tests/
agent-builder-eval run --test-dir generated_tests/ --report          # measure baseline
agent-builder-eval evolve --test-dir generated_tests/ \              # improve
  --train-slice 0:15 --validation-slice 15:22 --test-slice 22:30 --review
agent-builder-eval review runs/evolve/agent_builder_train            # see what changed
```

The first four verbs are the **evaluation** side (`../evaluation/`); the last
four are the **evolution** side documented here. `insights`, `evolve`, and
`review` all live in this package and are reached through the thin adapter at
`../evaluation/src/evolution/` (no vendoring — see
[How this relates to `../evaluation/`](#how-this-relates-to-evaluation)). The
optional deps for the evolution verbs are installed with
`pip install -e ".[evolve]"` from `../evaluation/`.

---

## The key idea

**An LLM edits the agent source files to make it score better, over and
over, until the gains run out.**

Concretely, the loop repeats four moves:

1. **Run** the agent on a set of eval scenarios and score it (assertion pass rate).
2. **Diagnose** *why* it failed — the specific mechanisms, with evidence.
3. **Edit** the agent's definition (`AGENT.md` + `mcp.json`) to fix those mechanisms.
4. **Keep the change only if it helps** on scenarios the editor never saw.

The agent's harness (any part of the harness including prompt, tools, code, skills, and so on) *is* the thing being optimized — there is no model
fine-tuning, no weights. Each pass is one "edit step," and the metric scores are the
signal that tells the loop whether the last edit was an improvement.

### Same shape as ML training

Instead of adjusting model weights, this harness evolver optimize the context around the foundation model, the loop maps onto it one-to-one — and the same
overfitting risk applies, which is why the scenarios are split into seen/unseen
sets:

| ML training concept | Here |
|---|---|
| **Model weights** (what gets optimized) | The agent source files: e.g.: `AGENT.md` + `mcp.json` in `../evaluation/agent_under_test/` |
| **Loss / objective** | Assertion pass rate on the eval scenarios (higher = better) |
| **Gradient step** | One *evolution step*: diagnose failures → an LLM edits the agent definition |
| **Training set** | `--train-slice` of the scenarios — the evolver sees these failures and edits against them |
| **Validation set** | `--validation-slice` — used for early stopping and to pick the best checkpoint; the evolver only sees it *after* it has already edited (step > 0) |
| **Test set** | `--test-slice` — measured once before and once after the whole run; **never** shown to the evolver |
| **Checkpoint** | A snapshot of the agent definition after each step (`post_step_NNN`) |
| **Early stopping** | Stop when validation pass rate stops improving for `patience` steps |
| **Generalization gap** | Train pass rate − validation pass rate; a large gap means the evolver overfit to the scenarios it saw |

**Why a held-out split matters.** An LLM editing an agent against the scenarios
it can see will happily hard-code instructions that pass *those* scenarios
without generalizing. Train/validation/test are disjoint slices of one scenario
directory; the test slice is never seen by the evolver, so the before/after test
numbers are an honest estimate of whether the agent actually got better.

---

## The two agents in the loop

Each step uses **two separate Claude agents** (via the Claude Agent SDK), with
distinct jobs and tool access:

1. **Analyst** ([`src/harness_evolver/analyst.py`](src/harness_evolver/analyst.py)) —
   reads the run artifacts (transcripts, logs, the `evaluation_summary.json`) and
   the agent's *source*, then writes a **diagnostic `report.md`**: the root-cause
   mechanisms by which the agent failed, with citations to concrete evidence. It
   *stops at diagnosis* — it does not propose or make edits. Tools: `Read`,
   `Glob`, `Grep`, `Write`. (Also exposed standalone as the `insights` verb.)

2. **Evolver** ([`src/harness_evolver/evolver/`](src/harness_evolver/evolver/)) —
   is handed the analyst's report(s) plus recent trajectory/history, treats them
   as *observations not instructions*, builds a mental model of the agent, and
   **edits the agent definition** to fix the mechanisms. It is prompted to prefer
   general fixes over instance-specific hacks and to keep the definition simple
   (a complexity budget discourages bloating `AGENT.md`). Tools: `Read`, `Glob`,
   `Grep`, `Write`, `Edit`, run with `cwd = target_dir` and `acceptEdits`.

The split is deliberate: the analyst decides *what went wrong*, the evolver
decides *what to change* — and only the evolver can write to the target.

---

## Anatomy of one step

For each step `0 … budget`:

```
            ┌─────────────────────────────────────────────────────────┐
            │  Run TRAIN (+VALIDATION) scenarios against target_dir     │
            │     eval_runner → ACP (kiro-cli) → LLM-judge grading      │
            │     → evaluation_summary.json   ◄── the contract          │
            └───────────────────────────┬─────────────────────────────┘
                                        │
            ┌───────────────────────────▼─────────────────────────────┐
            │  ANALYST diagnoses artifacts → report.md (root causes)    │
            └───────────────────────────┬─────────────────────────────┘
                                        │
            ┌───────────────────────────▼─────────────────────────────┐
            │  snapshot pre_step_NNN  →  EVOLVER edits AGENT.md/mcp.json │
            │                         →  snapshot post_step_NNN         │
            └───────────────────────────┬─────────────────────────────┘
                                        │
            ┌───────────────────────────▼─────────────────────────────┐
            │  Record trajectory + evolution_history; early-stop check  │
            └─────────────────────────────────────────────────────────┘
```

The last iteration (`step == budget`, or the step that triggers early stopping)
is **measurement-only** — it runs the scenarios one more time without editing, so
the final data point is never dropped. It lands in `final_eval/` instead of
`step_NNN/`.

**The contract.** Everything downstream — early stopping, checkpoint selection,
the history file, the dashboard — reads a single JSON file the `run` callback
writes: `evaluation_summary.json`, with at least
`assertion_pass_rate`, `total_tests`, and `tests[]` of `{test_id, passed}`. As
long as a `run` callback emits that schema, the loop works with any engine.

**After the loop**, `run_experiment` selects the best checkpoint by
`selection_metric` (default `validation`), restores the target directory to that
`post_step_NNN` snapshot, and re-measures the held-out test set. So the agent you
end up with is the one that validated best — not necessarily the last one.

---

## What it evolves

| | |
|---|---|
| **Target** (editable) | `../evaluation/agent_under_test/` — `AGENT.md` + `mcp.json` |
| **Scenarios** | `../evaluation/test_samples/` (sliced into train / validation / test) |
| **Engine** | `../evaluation/src/eval_runner` — drives the agent live over ACP and grades with an LLM judge |

The evolver mutates the target **in a snapshot ledger** (`snapshots.git`), not
destructively on disk — see [Run layout](#run-layout). The target's working copy
is restored to the best validation checkpoint at the end.

---

## 1. Prerequisites

- Python 3.11+ (3.12 recommended), with [`uv`](https://docs.astral.sh/uv/).
- The ACP driver binary `kiro-cli` on `PATH` (drives the agent under test).
- Bedrock access for the agent under test **and** for the analyst/evolver agents
  (Claude via the Claude Agent SDK). Credentials must be discoverable by
  `boto3` (env vars, `AWS_PROFILE`, or instance role).

If `uv` is not on `PATH`:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
source $HOME/.local/bin/env
```

---

## 2. Set up the environment

```bash
cd evolution
./setup/setup-agent-builder-env.sh
```

The script is idempotent. It creates `.venv/` (Python 3.12), installs
`harness_evolver` (this package) editable, verifies the Claude Agent SDK and AWS
credentials, and checks that the target agent (`../evaluation/agent_under_test/`)
and scenarios (`../evaluation/test_samples/`) are present.

To do it by hand:

```bash
cd evolution
uv venv --python 3.12
source .venv/bin/activate
uv pip install -e .
```

---

## 3. Run an evolution

Two entry points, same loop:

**A. The unified eval CLI** (recommended — shares config with `run`):

```bash
# from evaluation/, with its env set up (see ../evaluation/README.md)
agent-builder-eval evolve --budget 5 \
  --train-slice 0:10 --validation-slice 10:15 --test-slice 15:20 --review
```

This routes through the `evolution` adapter (`../evaluation/src/evolution/`),
which puts this package on `sys.path` (no vendoring) and re-wires the evolver to
evaluate through the **same `eval_runner` engine** as the `run` verb. It is the
canonical way to evolve. See the [evaluation README](../evaluation/README.md) for
the `insights`, `review`, and `evohistory` companions.

**B. The standalone experiment script** (self-contained config):

```bash
cd evolution
source .venv/bin/activate
PYTHONPATH=. python experiment/evolve_agent_builder.py
```

Edit `RUN_MODE` (`quick` / `standard` / `full`) and the slice/budget constants
near the top of
[`experiment/evolve_agent_builder.py`](experiment/evolve_agent_builder.py).
The three modes differ only in slice sizes and run directory:

| Mode | train | validation | test | budget | patience |
|------|-------|-----------|------|--------|----------|
| `quick` | `0:2` | `2:4` | `4:6` | 5 | 3 |
| `standard` | `0:10` | `10:15` | `15:20` | 5 | 3 |
| `full` | `0:30` | `30:40` | `40:50` | 5 | 3 |

Output goes to `runs/agent_builder_<mode>/`.

> **Note:** the train/validation/test split needs enough scenarios in
> `../evaluation/test_samples/` to be meaningful. With only a handful of
> scenarios the validation/test slices come back empty. Add scenarios there (or
> point at a generated suite via `agent-builder-eval evolve --test-dir …`) before
> running a `standard`/`full` evolution.

`run_evolution.sh` is a convenience wrapper around entry point B (activates the
venv, checks AWS creds, then runs the experiment script and prints how to inspect
the resulting snapshot ledger).

### Tuning knobs

The loop is parameterized the same way through both entry points
(CLI flags ↔ `Orchestrator.run_experiment` args):

| Knob | CLI flag | Meaning |
|------|----------|---------|
| Budget | `--budget` | Max number of edit steps before the final measurement-only pass |
| Early-stopping patience | `--patience` | Stop if validation doesn't improve for N steps (0 = disabled) |
| Min delta | (script: `early_stopping_min_delta`) | Improvement below this (default `0.01` = 1%) doesn't reset patience |
| Selection metric | (script: `selection_metric`) | Which checkpoint to restore: `validation` (default), `train`, or `final` |

### Configuration via environment variables

The standalone path resolves everything repo-relative by default; override any
of these without editing code (see
[`env_configs/agent_builder_env.py`](env_configs/agent_builder_env.py)):

| Env var | Default | Purpose |
|---------|---------|---------|
| `AGENT_BUILDER_EVAL_ROOT` | `../evaluation` | Root of the evaluation framework |
| `AGENT_BUILDER_EVAL_FRAMEWORK_DIR` | `$EVAL_ROOT/src` | Where `eval_runner` is importable from |
| `AGENT_BUILDER_TARGET_DIR` | `$EVAL_ROOT/agent_under_test` | The editable agent definition |
| `AGENT_BUILDER_TEST_DATA_DIR` | `$EVAL_ROOT/test_samples` | Scenario directory the slices index into |
| `AGENT_BUILDER_ACP_BINARY` | `kiro-cli` | ACP driver binary for the agent under test |
| `AGENT_BUILDER_AGENT_MODEL` | `claude-opus-4.6` | Model the agent under test runs on |

---

## 4. Monitor (optional dashboard)

```bash
cd evolution
source .venv/bin/activate
uv pip install -e ".[dashboard]"                  # Flask + plotly
./scripts/start_dashboard.sh agent_builder_full   # → http://localhost:5000
```

`start_dashboard.sh` launches
[`dashboard/evolution_dashboard.py`](dashboard/evolution_dashboard.py)
(`--run-dir runs/<name>`, `--port`, `--host`), which renders live per-step
train/validation pass rates, the generalization gap, and the best checkpoint.
See [`dashboard/README.md`](dashboard/README.md) for the full panel reference.

---

## Run layout

```
runs/<run_name>/
├── <train_env_name>/                # e.g. agent_builder_train
│   ├── snapshots.git/               # baseline + pre/post-edit target snapshots
│   ├── trajectory.jsonl             # one event per phase
│   ├── evolution_history.md         # cumulative per-step results + decisions
│   ├── reports/<env>/step_NNN.md    # analyst reports, per env, per step
│   ├── step_000/
│   │   ├── prompt.md                # what the evolver agent was given
│   │   ├── agent_trace.jsonl        # the evolver agent's stream
│   │   └── <env_name>/
│   │       ├── run/                 # eval artifacts + evaluation_summary.json
│   │       └── analyst_output/report.md   # diagnostic report ("insights")
│   └── final_eval/<env_name>/...    # measurement-only re-run (last data point)
└── test/                            # held-out test set, never seen by the evolver
    ├── before/                      # measured against the baseline target
    │   ├── run/evaluation_summary.json
    │   └── analyst_output/report.md
    └── after/                       # measured against the selected best checkpoint
        ├── run/evaluation_summary.json
        └── analyst_output/report.md
```

The evolver's edits are **not** committed to the agent repo. They live in
`runs/<run>/<train_env>/snapshots.git/` as
`baseline → pre_step_NNN → post_step_NNN`:

```bash
cd runs/<run>/<train_env>
GIT_DIR=snapshots.git git log --oneline
GIT_DIR=snapshots.git git diff pre_step_000 post_step_000
```

> Note: `baseline` / `pre_step_NNN` / `post_step_NNN` are commit **messages**,
> not branches or tags. `git log --grep` matches them, but `git diff` needs a
> resolved SHA — which is exactly what the `review` verb (and
> `generate_change_review.py`) does for you.

```bash
# Cumulative diff — everything the run changed, baseline → final:
baseline=$(git --git-dir=snapshots.git log master -n1 --format=%H --grep='^baseline$')
git --git-dir=snapshots.git diff "$baseline" master
```

---

## Utilities

Standalone tools (not part of the loop; run them against a completed run dir):

| Script | Purpose |
|--------|---------|
| [`scripts/generate_change_review.py`](scripts/generate_change_review.py) | PR-style markdown diff of a run's snapshot ledger (also exposed as `agent-builder-eval review`). |
| [`scripts/reconstruct_history.py`](scripts/reconstruct_history.py) | Rebuild `evolution_history.md` from an existing run's artifacts. |
| [`scripts/plot_training_results.py`](scripts/plot_training_results.py), [`scripts/plot_training_results_enhanced.py`](scripts/plot_training_results_enhanced.py) | Plot train/validation/test curves from a run. |
| [`scripts/run_agent_builder_evaluation.py`](scripts/run_agent_builder_evaluation.py) | One-off evaluation of an agent dir without evolving (`--agent-dir`, `--test-slice`). |
| [`scripts/verify_model_selection.py`](scripts/verify_model_selection.py) | Show which checkpoint validation-based selection would pick for a run. |
| [`scripts/verify_implementation.py`](scripts/verify_implementation.py) | Self-check that early-stopping / regularization / data-split features are wired in the source. |

Smoke-test the engine wiring without a full run (one scenario, no edits):

```bash
PYTHONPATH=src python scripts/run_agent_builder_evaluation.py \
  --agent-dir ../evaluation/agent_under_test \
  --test-slice 0:1 --output-dir /tmp/eval-smoke
```

---

## Package layout

```
evolution/
├── src/harness_evolver/        # the package (engine-agnostic)
│   ├── orchestrator.py         # Orchestrator: run_evolve / run_experiment + checkpoint selection
│   ├── evolver/                # the evolver agent (evolver.py + prompt.py) — edits the target
│   ├── analyst.py              # diagnostic report generator ("insights") — diagnoses, never edits
│   ├── environment.py          # Environment(target_dir, goal, run, name) — the engine boundary
│   ├── snapshots.py            # the snapshot-ledger git wrapper
│   ├── trajectory.py           # per-phase event log (trajectory.jsonl)
│   └── evolution_history.py    # cumulative history + EvaluationStats (reads the contract)
├── env_configs/agent_builder_env.py   # make_env() → eval_runner-backed Environment (the repo wiring)
├── experiment/evolve_agent_builder.py # standalone experiment entry point (RUN_MODE)
├── dashboard/                  # live monitoring (Flask + plotly)
├── scripts/                    # all standalone tools: change-review, history rebuild,
│                               #   plotting, one-off eval, verification, dashboard launcher
├── tests/                      # unit tests (test_evolution_history.py)
├── setup/setup-agent-builder-env.sh
└── run_evolution.sh
```

Public API:

```python
from harness_evolver import Orchestrator, Environment, configure_logging
```

The repo-specific binding lives entirely in
[`env_configs/agent_builder_env.py`](env_configs/agent_builder_env.py):
`make_env(name, test_slice)` returns an `Environment` whose `run` callback drives
`eval_runner`'s `ExecutionConfig` + `EvalOrchestrator.run_eval()` and writes the
`evaluation_summary.json` contract. To evolve a *different* agent or engine, write
a new `make_env` — the loop itself doesn't change.

---

## How this relates to `../evaluation/`

| | `../evaluation/` | `evolution/` (this dir) |
|---|---|---|
| Verb | `run` (and `generate`, `report`) | `evolve` (and `insights`, `review`) |
| Goal | **Measure** the agent | **Improve** the agent |
| Output | Pass rates, HTML dashboard | An edited `agent_under_test/` + the path that got there |
| Engine | `eval_runner` (ACP + LLM judge) | the **same** `eval_runner`, driven step-by-step |

`evolution/` stays a self-contained project (its own git/venv/pyproject) and is
**not** vendored into the evaluation package. The thin adapter at
`../evaluation/src/evolution/` puts this `src/` on `sys.path` and re-wires the
evolver onto the evaluation engine, so `run` and `evolve` never drift apart. See
the [evaluation README](../evaluation/README.md) for the unified CLI.

---

## Troubleshooting

- **`kiro-cli: not found`.** The agent under test is driven over ACP by
  `kiro-cli`; install it and ensure it's on `PATH` (or set `AGENT_BUILDER_ACP_BINARY`).
- **Bedrock auth / `NoCredentialsError`.** Set `AWS_PROFILE` (or other boto3
  credentials) before running. The setup script's credential check catches this.
- **Empty / degenerate split.** With only a handful of scenarios in
  `test_samples/`, the validation and test slices may be empty (the `run`
  callback writes an `ERROR.txt` and returns). Add more scenarios, point at a
  generated suite, or shrink the slices.
- **Analyst returns "did not produce a report".** The harness retries up to 3
  times. If it persists, inspect
  `runs/<run>/<env>/step_NNN/<env>/analyst_output/` and adjust the prompt in
  [`src/harness_evolver/analyst.py`](src/harness_evolver/analyst.py).
- **Pass rate jumps around between runs.** Expected — both the agent under test
  and the LLM judge are non-deterministic. Trust the validation/test split and
  the trend across steps, not a single number.
- **`verify_implementation.py` Phase-4 failures.** A known pre-existing quirk: the
  check expects slice values that don't match the experiment script's `full`
  mode. Unrelated to the loop's correctness.
```
