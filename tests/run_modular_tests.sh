#!/bin/bash
# Script to run unit tests for the modular stack components

# Set up colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[0;33m'
NC='\033[0m' # No Color

echo -e "${YELLOW}Running unit tests for modular stack components...${NC}"
echo

# Change to project root directory
cd "$(dirname "$0")/.." || exit 1

# Run tests for each module
modules=(
  "rds"
  "auto_scaling"
  "route53"
  "security_group"
)

success=true

for module in "${modules[@]}"; do
  echo -e "${YELLOW}Testing ${module} module...${NC}"
  python3 -m pytest tests/unit/test_${module}_stack.py -v
  
  if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ ${module} tests passed${NC}"
  else
    echo -e "${RED}✗ ${module} tests failed${NC}"
    success=false
  fi
  echo
done

# Final summary
if [ "$success" = true ]; then
  echo -e "${GREEN}All tests passed successfully!${NC}"
  exit 0
else
  echo -e "${RED}Some tests failed. Please check the output above for details.${NC}"
  exit 1
fi
