# Evolution Dashboard

Real-time monitoring dashboard for Agent Builder evolution experiments.

## Features

- **Live Metrics**: Auto-updating metrics every 5 seconds
- **Interactive Plots**: 
  - Assertion pass rate (train vs validation)
  - Test success rate (complete tests)
  - Generalization gap (overfitting indicator)
- **Step-by-Step Table**: Detailed results for each training step
- **Status Tracking**: Current step, stage (training/validation/editing)
- **Best Checkpoint Highlighting**: Automatically identifies best validation checkpoint

## Quick Start

### Terminal 1: Start Evolution
```bash
cd evolution
source .venv/bin/activate
PYTHONPATH=. python experiment/evolve_agent_builder.py
```

### Terminal 2: Start Dashboard
```bash
cd evolution
source .venv/bin/activate
python dashboard/evolution_dashboard.py --run-dir runs/agent_builder_full
```

### Open Browser
Navigate to: **http://localhost:5000**

## Usage

### Monitor a Different Run
```bash
python dashboard/evolution_dashboard.py --run-dir runs/agent_builder_standard
```

### Change Port
```bash
python dashboard/evolution_dashboard.py --run-dir runs/agent_builder_full --port 8080
```

### Allow Remote Access
```bash
python dashboard/evolution_dashboard.py --run-dir runs/agent_builder_full --host 0.0.0.0
```

## Dashboard Components

### 1. Summary Cards
- **Current Step**: Which training step is running
- **Best Validation**: The checkpoint with highest validation performance
- **Latest Gap**: Train-val gap at current step (overfitting indicator)
- **Test Performance**: Test set results (if available)

### 2. Assertion Pass Rate Plot
Shows individual assertion-level performance:
- Blue line: Training performance
- Purple line: Validation performance
- Green star: Best validation checkpoint

### 3. Test Success Rate Plot
Shows complete test pass rate (all assertions must pass):
- More sensitive to overfitting
- Better indicator of real-world performance

### 4. Generalization Gap Plot
Bar chart showing train-val gap at each step:
- Green: < 5% (good generalization)
- Orange: 5-10% (warning)
- Red: > 10% (severe overfitting)

### 5. Results Table
Detailed step-by-step breakdown:
- Assertion counts and pass rates
- Test success rates
- Timestamps
- Highlighted rows:
  - **Green background**: Best validation checkpoint
  - **Yellow background**: Current step

## Requirements

The dashboard requires Flask and Plotly. Install with:

```bash
pip install flask plotly
```

These should already be installed if you're using the HarnessEvolver environment.

## Troubleshooting

### "No data available yet"
- Wait for the first training step to complete
- Check that the run directory path is correct

### Dashboard not updating
- Check that the evolution is actually running
- Verify the run directory exists and contains a `agent_builder_train` subdirectory
- Browser console (F12) should show no errors

### Port already in use
```bash
# Use a different port
python dashboard/evolution_dashboard.py --run-dir runs/agent_builder_full --port 5001
```

## Tips

1. **Start dashboard before evolution**: It will wait for data
2. **Leave it running**: Auto-refreshes every 5 seconds
3. **Monitor overfitting**: Watch the gap plot - red bars indicate problems
4. **Check best checkpoint**: Green star shows which step to use
5. **Compare to test**: Final test results show if validation was predictive

## Example Workflow

```bash
# Terminal 1: Start evolution (takes ~30-60 min)
cd evolution
source .venv/bin/activate
PYTHONPATH=. python experiment/evolve_agent_builder.py

# Terminal 2: Monitor progress
cd evolution
source .venv/bin/activate
python dashboard/evolution_dashboard.py --run-dir runs/agent_builder_full

# Browser: Open http://localhost:5000
# Watch the metrics update in real-time
# See which checkpoint performs best
# Compare to final test results when complete
```

## Screenshot Description

The dashboard shows:
- **Top row**: 4 metric cards with key numbers
- **Middle**: 3 interactive Plotly charts
- **Bottom**: Detailed table with all step results
- **Status bar**: Current progress and auto-refresh indicator

Colors indicate health:
- 🟢 Green: Good performance, low gap
- 🟡 Orange: Warning, moderate gap
- 🔴 Red: Danger, high gap or degradation
