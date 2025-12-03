#!/bin/bash
# Development environment setup for Phone Agent
# This script installs all dependencies including the shared library

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
SHARED_LIBS_DIR="$PROJECT_DIR/../shared-libs"

echo "=== Phone Agent Development Setup ==="
echo ""

# Check Python version
PYTHON_VERSION=$(python3 --version 2>&1 | cut -d' ' -f2)
echo "Python version: $PYTHON_VERSION"

# Check if shared-libs exists
if [ ! -d "$SHARED_LIBS_DIR" ]; then
    echo "ERROR: shared-libs directory not found at: $SHARED_LIBS_DIR"
    echo "Please ensure the IT-Friends repository is cloned correctly."
    exit 1
fi

echo ""
echo "Step 1/3: Installing shared library (itf-shared)..."
pip install -e "$SHARED_LIBS_DIR"

echo ""
echo "Step 2/3: Installing phone-agent with dev dependencies..."
pip install -e "$PROJECT_DIR[dev]"

echo ""
echo "Step 3/3: Verifying installation..."
python3 -c "import itf_shared; print('  itf_shared: OK')"
python3 -c "import phone_agent; print('  phone_agent: OK')"

echo ""
echo "=== Setup Complete! ==="
echo ""
echo "Next steps:"
echo "  1. Run tests:     pytest tests/ -v"
echo "  2. Start server:  uvicorn phone_agent.main:app --reload"
echo "  3. View API docs: http://localhost:8000/docs"
echo ""
