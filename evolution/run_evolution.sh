#!/usr/bin/env bash
# Convenience script to run agent-builder evolution with proper environment setup
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=== Agent Builder Evolution ==="
echo ""

# Check if venv exists
if [ ! -d ".venv" ]; then
    echo "ERROR: Virtual environment not found at .venv/"
    echo "Run setup first: ./setup/setup-agent-builder-env.sh"
    exit 1
fi

# Activate venv
echo "Activating virtual environment..."
source .venv/bin/activate

# Verify harness_evolver is installed
if ! python3 -c "import harness_evolver" 2>/dev/null; then
    echo "Installing harness_evolver..."
    pip install -e . > /dev/null
fi

# Check AWS credentials
if ! aws sts get-caller-identity >/dev/null 2>&1; then
    echo ""
    echo "WARNING: AWS credentials not configured or not working"
    echo "Set AWS_PROFILE or configure credentials before continuing"
    echo ""
    read -p "Press Enter to continue anyway, or Ctrl-C to abort..."
fi

# Run evolution
echo ""
echo "Starting evolution..."
echo "Output: runs/agent_builder_*/agent_builder_train/"
echo ""

PYTHONPATH=. python3 experiment/evolve_agent_builder.py "$@"

EXIT_CODE=$?

if [ $EXIT_CODE -eq 0 ]; then
    echo ""
    echo "=== Evolution Complete ==="
    echo ""
    echo "View results:"
    echo "  cd runs/agent_builder_*/agent_builder_train"
    echo "  GIT_DIR=snapshots.git git diff baseline HEAD"
    echo ""
else
    echo ""
    echo "=== Evolution Failed ==="
    echo "Exit code: $EXIT_CODE"
    echo ""
fi

exit $EXIT_CODE
