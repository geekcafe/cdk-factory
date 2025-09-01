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

# check if virtual environment exists
if [ -d ".unittest" ]; then
    echo "🧹 Deleting old virtual environment"
    # delete old virtual environment
    # rm -rf .unittest
fi

echo "🧹 Creating new virtual environment"
python -m venv .unittest
source ./.unittest/bin/activate
which python


pip install --upgrade pip
pip install -r ./requirements.txt
pip install -r ./requirements.dev.txt
pip install -r ./requirements.tests.txt

# Check if pytest is installed in the virtual environment
if [ ! -f ".unittest/bin/pytest" ]; then
    echo -e "${RED}Error: pytest not found in virtual environment${NC}"
    echo "Please install pytest:"
    echo "  source .unittest/bin/activate"
    echo "  pip install pytest"
    exit 1
fi

echo -e "${YELLOW}Activating virtual environment...${NC}"
source ./.unittest/bin/activate

echo -e "${YELLOW}Running unit tests...${NC}"
echo ""

# Run pytest with verbose output and coverage if available
if ./.unittest/bin/python -c "import pytest_cov" 2>/dev/null; then
    echo "Running tests with coverage..."
    ./.unittest/bin/python -m pytest tests/unit/ -v --cov=src/cdk_factory --cov-report=term-missing
else
    echo "Running tests without coverage (install pytest-cov for coverage reports)..."
    ./.unittest/bin/python -m pytest tests/unit/ -v
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
