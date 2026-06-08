#!/bin/bash
# Start the evolution dashboard
# Usage: ./scripts/start_dashboard.sh [run_name]

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HARNESS_DIR="$(dirname "$SCRIPT_DIR")"

cd "$HARNESS_DIR"

# Activate virtual environment if it exists
if [ -f ".venv/bin/activate" ]; then
    echo "Activating virtual environment..."
    source .venv/bin/activate
elif [ -f "venv/bin/activate" ]; then
    echo "Activating virtual environment..."
    source venv/bin/activate
else
    echo "Warning: No virtual environment found, using system Python"
fi

# Default run directory
RUN_NAME="${1:-agent_builder_full}"
RUN_DIR="$HARNESS_DIR/runs/$RUN_NAME"

echo "============================================"
echo "Agent Builder Evolution Dashboard"
echo "============================================"
echo ""
echo "Monitoring: $RUN_DIR"
echo ""
echo "Dashboard will be available at:"
echo "  http://localhost:5000"
echo ""
echo "Press Ctrl+C to stop"
echo ""

# Start dashboard
python dashboard/evolution_dashboard.py --run-dir "$RUN_DIR"
