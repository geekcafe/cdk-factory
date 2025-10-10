#!/bin/bash

# CDK Factory Unit Test Runner
# This script runs the unit tests for the CDK Factory project using the virtual environment

set -e  # Exit on any error

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${YELLOW}CDK Factory Unit Test Runner${NC}"
echo "=================================="

./pysetup.sh --ci

# Check if pytest is installed in the virtual environment
if [ ! -f ".venv/bin/pytest" ]; then
    echo -e "${RED}Error: pytest not found in virtual environment${NC}"
    echo "Please install pytest:"
    echo "  source .venv/bin/activate"
    echo "  pip install pytest"
    exit 1
fi

echo -e "${YELLOW}Activating virtual environment...${NC}"
source ./.venv/bin/activate

echo -e "${YELLOW}Running unit tests...${NC}"
echo ""

# Run pytest with verbose output and coverage if available
if ./.venv/bin/python -c "import pytest_cov" 2>/dev/null; then
    echo "Running tests with coverage..."
    ./.venv/bin/python -m pytest tests/unit/ -v --cov=src/cdk_factory --cov-report=term-missing
else
    echo "Running tests without coverage (install pytest-cov for coverage reports)..."
    ./.venv/bin/python -m pytest tests/unit/ -v
fi

TEST_EXIT_CODE=$?

echo ""
if [ $TEST_EXIT_CODE -eq 0 ]; then
    echo -e "${GREEN}✅ All tests passed!${NC}"
else
    echo -e "${RED}❌ Some tests failed (exit code: $TEST_EXIT_CODE)${NC}"
fi

echo -e "${YELLOW}Test run completed.${NC}"
exit $TEST_EXIT_CODE
