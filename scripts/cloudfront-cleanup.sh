#!/bin/bash
#
# CloudFront Function Association Cleanup Script
# 
# Use this when CDK deployments are stuck due to function association conflicts
# This script safely removes all function associations from a CloudFront distribution
#

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Usage
usage() {
    echo "Usage: $0 --distribution-id <DIST_ID> [--profile <PROFILE>] [--dry-run]"
    echo ""
    echo "Options:"
    echo "  --distribution-id    CloudFront distribution ID (required)"
    echo "  --profile            AWS profile name (optional)"
    echo "  --dry-run            Show what would be done without making changes"
    echo "  --help               Show this help message"
    echo ""
    echo "Example:"
    echo "  $0 --distribution-id E3T9ODGTZTLF2N --profile gc-shared"
    exit 1
}

# Parse arguments
DIST_ID=""
PROFILE=""
DRY_RUN=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --distribution-id)
            DIST_ID="$2"
            shift 2
            ;;
        --profile)
            PROFILE="$2"
            shift 2
            ;;
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        --help)
            usage
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            usage
            ;;
    esac
done

# Validate required arguments
if [ -z "$DIST_ID" ]; then
    echo -e "${RED}Error: --distribution-id is required${NC}"
    usage
fi

# Build AWS CLI command prefix
AWS_CMD="aws cloudfront"
if [ -n "$PROFILE" ]; then
    AWS_CMD="$AWS_CMD --profile $PROFILE"
fi

# Temp files
CONFIG_FILE="/tmp/cloudfront-config-${DIST_ID}.json"
CLEAN_CONFIG_FILE="/tmp/cloudfront-config-${DIST_ID}-clean.json"

echo -e "${YELLOW}========================================${NC}"
echo -e "${YELLOW}CloudFront Function Association Cleanup${NC}"
echo -e "${YELLOW}========================================${NC}"
echo ""
echo "Distribution ID: $DIST_ID"
if [ -n "$PROFILE" ]; then
    echo "AWS Profile: $PROFILE"
fi
if [ "$DRY_RUN" = true ]; then
    echo -e "${YELLOW}Mode: DRY RUN (no changes will be made)${NC}"
fi
echo ""

# Step 1: Get current configuration
echo -e "${GREEN}Step 1: Fetching current distribution configuration...${NC}"
$AWS_CMD get-distribution-config --id "$DIST_ID" > "$CONFIG_FILE"

if [ $? -ne 0 ]; then
    echo -e "${RED}Error: Failed to get distribution configuration${NC}"
    exit 1
fi

ETAG=$(cat "$CONFIG_FILE" | jq -r '.ETag')
echo "ETag: $ETAG"

# Step 2: Show current function associations
echo ""
echo -e "${GREEN}Step 2: Current function associations:${NC}"

LAMBDA_COUNT=$(cat "$CONFIG_FILE" | jq -r '.DistributionConfig.DefaultCacheBehavior.LambdaFunctionAssociations.Quantity // 0')
CF_FUNC_COUNT=$(cat "$CONFIG_FILE" | jq -r '.DistributionConfig.DefaultCacheBehavior.FunctionAssociations.Quantity // 0')

echo "  Lambda@Edge functions: $LAMBDA_COUNT"
if [ "$LAMBDA_COUNT" -gt 0 ]; then
    cat "$CONFIG_FILE" | jq -r '.DistributionConfig.DefaultCacheBehavior.LambdaFunctionAssociations.Items[]? | "    - \(.EventType): \(.LambdaFunctionARN)"'
fi

echo "  CloudFront Functions: $CF_FUNC_COUNT"
if [ "$CF_FUNC_COUNT" -gt 0 ]; then
    cat "$CONFIG_FILE" | jq -r '.DistributionConfig.DefaultCacheBehavior.FunctionAssociations.Items[]? | "    - \(.EventType): \(.FunctionARN)"'
fi

# Check if cleanup is needed
if [ "$LAMBDA_COUNT" -eq 0 ] && [ "$CF_FUNC_COUNT" -eq 0 ]; then
    echo ""
    echo -e "${GREEN}✓ No function associations found. Distribution is already clean!${NC}"
    rm -f "$CONFIG_FILE"
    exit 0
fi

# Step 3: Create cleaned configuration
echo ""
echo -e "${GREEN}Step 3: Creating cleaned configuration...${NC}"

cat "$CONFIG_FILE" | jq '
  .DistributionConfig |
  .DefaultCacheBehavior.FunctionAssociations = {"Quantity": 0} |
  .DefaultCacheBehavior.LambdaFunctionAssociations = {"Quantity": 0}
' > "$CLEAN_CONFIG_FILE"

echo "  Cleaned config saved to: $CLEAN_CONFIG_FILE"

# Step 4: Apply changes
echo ""
if [ "$DRY_RUN" = true ]; then
    echo -e "${YELLOW}Step 4: DRY RUN - Would remove all function associations${NC}"
    echo ""
    echo "To apply these changes, run without --dry-run:"
    echo "  $0 --distribution-id $DIST_ID $([ -n "$PROFILE" ] && echo "--profile $PROFILE")"
    
    rm -f "$CONFIG_FILE" "$CLEAN_CONFIG_FILE"
    exit 0
fi

echo -e "${GREEN}Step 4: Applying changes to CloudFront distribution...${NC}"
echo -e "${YELLOW}⚠️  This will remove ALL function associations from the distribution${NC}"
read -p "Are you sure you want to continue? (yes/no): " CONFIRM

if [ "$CONFIRM" != "yes" ]; then
    echo "Aborted."
    rm -f "$CONFIG_FILE" "$CLEAN_CONFIG_FILE"
    exit 0
fi

$AWS_CMD update-distribution \
    --id "$DIST_ID" \
    --if-match "$ETAG" \
    --distribution-config "file://$CLEAN_CONFIG_FILE" \
    > /dev/null

if [ $? -ne 0 ]; then
    echo -e "${RED}Error: Failed to update distribution${NC}"
    rm -f "$CONFIG_FILE" "$CLEAN_CONFIG_FILE"
    exit 1
fi

echo -e "${GREEN}✓ Successfully updated distribution${NC}"

# Step 5: Wait for deployment
echo ""
echo -e "${GREEN}Step 5: Waiting for distribution deployment...${NC}"
echo "This may take 5-10 minutes..."

$AWS_CMD wait distribution-deployed --id "$DIST_ID"

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ Distribution deployed successfully${NC}"
else
    echo -e "${YELLOW}⚠️  Wait timed out or failed. Check distribution status manually.${NC}"
fi

# Step 6: Verify cleanup
echo ""
echo -e "${GREEN}Step 6: Verifying cleanup...${NC}"

$AWS_CMD get-distribution-config --id "$DIST_ID" > "$CONFIG_FILE"

LAMBDA_COUNT=$(cat "$CONFIG_FILE" | jq -r '.DistributionConfig.DefaultCacheBehavior.LambdaFunctionAssociations.Quantity // 0')
CF_FUNC_COUNT=$(cat "$CONFIG_FILE" | jq -r '.DistributionConfig.DefaultCacheBehavior.FunctionAssociations.Quantity // 0')

echo "  Lambda@Edge functions: $LAMBDA_COUNT"
echo "  CloudFront Functions: $CF_FUNC_COUNT"

if [ "$LAMBDA_COUNT" -eq 0 ] && [ "$CF_FUNC_COUNT" -eq 0 ]; then
    echo ""
    echo -e "${GREEN}========================================${NC}"
    echo -e "${GREEN}✓ SUCCESS: All function associations removed${NC}"
    echo -e "${GREEN}========================================${NC}"
    echo ""
    echo "Next steps:"
    echo "1. Run your CDK deployment to add back desired functions"
    echo "2. Wait 20-30 minutes for Lambda@Edge propagation (if using Lambda@Edge)"
    echo "3. Test your CloudFront distribution"
else
    echo ""
    echo -e "${YELLOW}⚠️  Warning: Some functions still present${NC}"
    echo "Manual verification may be needed."
fi

# Cleanup temp files
rm -f "$CONFIG_FILE" "$CLEAN_CONFIG_FILE"

echo ""
echo "Done!"
