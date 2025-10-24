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



# Create and activate virtual environment if it doesn't exist
if [ ! -d ".venv" ]; then
    echo -e "${YELLOW}Creating virtual environment...${NC}"
    python3 -m venv .venv
    # Install dependencies
    echo -e "${YELLOW}Installing dependencies...${NC}"
    pip install -q -r requirements.dev.txt
    pip install -q -r requirements.tests.txt
fi

# see if it's activated
if [ ! -f ".venv/bin/activate" ]; then
    echo -e "${YELLOW}Activating virtual environment...${NC}"
    source ./.venv/bin/activate
fi



# Check if pytest is installed in the virtual environment
if ! command -v pytest &> /dev/null; then
    echo -e "${RED}Error: pytest could not be installed or found in the virtual environment.${NC}"
    exit 1
fi

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
