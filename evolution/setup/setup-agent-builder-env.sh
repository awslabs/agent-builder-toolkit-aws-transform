#!/usr/bin/env bash
# Setup script for Agent Builder evolution environment
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"

echo "=== Setting up Agent Builder Evolution Environment ==="
echo "Repository root: $REPO_ROOT"

# 1. Check Python version
echo ""
echo "1. Checking Python version..."
python3 --version | grep -q "Python 3\.1[1-9]" || {
    echo "ERROR: Python 3.11+ required"
    exit 1
}
echo "✓ Python version OK"

# 2. Create main venv if it doesn't exist
echo ""
echo "2. Setting up main venv..."
if [ ! -d "$REPO_ROOT/.venv" ]; then
    echo "Creating .venv..."
    uv venv --python 3.12 "$REPO_ROOT/.venv"
    echo "Installing harness_evolver..."
    source "$REPO_ROOT/.venv/bin/activate"
    uv pip install -e "$REPO_ROOT"
else
    echo "✓ .venv already exists"
    source "$REPO_ROOT/.venv/bin/activate"
    # Reinstall in case of updates
    echo "Ensuring harness_evolver is installed..."
    pip install -e "$REPO_ROOT" > /dev/null 2>&1
fi

# 3. Verify Claude Agent SDK
echo ""
echo "3. Verifying dependencies..."
python3 -c "from harness_evolver import Orchestrator, configure_logging; print('✓ harness_evolver OK')"
python3 -c "import claude_agent_sdk; print('✓ claude-agent-sdk OK')"

# 4. Check AWS credentials
echo ""
echo "4. Checking AWS credentials..."
if python3 -c "import boto3; boto3.client('bedrock-runtime', region_name='us-east-1')" 2>/dev/null; then
    echo "✓ AWS credentials OK"
else
    echo "WARNING: AWS credentials not found or not configured"
    echo "  Evolution requires Bedrock access for Claude agents"
    echo "  Set AWS_PROFILE or configure credentials"
fi

# 5. Verify eval scenarios (the test samples)
echo ""
echo "5. Verifying eval scenarios..."
EVAL_ROOT="${AGENT_BUILDER_EVAL_ROOT:-$(dirname "$REPO_ROOT")/evaluation}"
TEST_DATA_DIR="${AGENT_BUILDER_TEST_DATA_DIR:-$EVAL_ROOT/test_samples}"
if [ -d "$TEST_DATA_DIR" ]; then
    TEST_COUNT=$(find "$TEST_DATA_DIR" -name "*.json" | wc -l)
    echo "✓ Found $TEST_COUNT scenario file(s) in test_samples"
else
    echo "ERROR: Scenario directory not found: $TEST_DATA_DIR"
    exit 1
fi

# 6. Verify target agent directory (the agent under test)
echo ""
echo "6. Verifying target agent directory..."
AGENT_DIR="${AGENT_BUILDER_TARGET_DIR:-$EVAL_ROOT/agent_under_test}"
if [ -d "$AGENT_DIR" ]; then
    echo "✓ Agent directory exists: $AGENT_DIR"
    if [ -f "$AGENT_DIR/AGENT.md" ]; then
        echo "  - AGENT.md found"
    else
        echo "  WARNING: AGENT.md not found"
    fi
    if [ -f "$AGENT_DIR/mcp.json" ]; then
        echo "  - mcp.json found"
    else
        echo "  WARNING: mcp.json not found"
    fi
else
    echo "ERROR: Agent directory not found: $AGENT_DIR"
    exit 1
fi

# 7. Create scripts directory if needed
echo ""
echo "7. Setting up scripts directory..."
mkdir -p "$REPO_ROOT/scripts"
echo "✓ Scripts directory ready"

echo ""
echo "=== Setup Complete ==="
echo ""
echo "To run evolution:"
echo "  1. Activate venv: source $REPO_ROOT/.venv/bin/activate"
echo "  2. Run experiment: PYTHONPATH=. python experiment/evolve_agent_builder.py"
echo ""
echo "Run modes (edit experiment/evolve_agent_builder.py, set RUN_MODE):"
echo "  - 'quick'    small slices, fast iteration"
echo "  - 'standard' medium slices"
echo "  - 'full'     full slices, comprehensive"
