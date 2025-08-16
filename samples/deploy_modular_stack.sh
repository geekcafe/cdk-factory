#!/bin/bash
# Script to deploy the modular full stack application

# Default values
DEPLOYMENT_NAME="dev"
DOMAIN_NAME="example.com"
HOSTED_ZONE_ID=""
CERTIFICATE_ARN=""
DB_NAME="appdb"
DB_USERNAME="admin"
CONTAINER_IMAGE="nginx:latest"
CONTAINER_PORT=80

# Parse command line arguments
while [[ $# -gt 0 ]]; do
  case $1 in
    --deployment-name)
      DEPLOYMENT_NAME="$2"
      shift 2
      ;;
    --domain-name)
      DOMAIN_NAME="$2"
      shift 2
      ;;
    --hosted-zone-id)
      HOSTED_ZONE_ID="$2"
      shift 2
      ;;
    --certificate-arn)
      CERTIFICATE_ARN="$2"
      shift 2
      ;;
    --db-name)
      DB_NAME="$2"
      shift 2
      ;;
    --db-username)
      DB_USERNAME="$2"
      shift 2
      ;;
    --container-image)
      CONTAINER_IMAGE="$2"
      shift 2
      ;;
    --container-port)
      CONTAINER_PORT="$2"
      shift 2
      ;;
    --help)
      echo "Usage: $0 [options]"
      echo "Options:"
      echo "  --deployment-name    Environment name (default: dev)"
      echo "  --domain-name        Domain name for DNS records (default: example.com)"
      echo "  --hosted-zone-id     Route53 hosted zone ID"
      echo "  --certificate-arn    ACM certificate ARN for HTTPS"
      echo "  --db-name            Database name (default: appdb)"
      echo "  --db-username        Database username (default: admin)"
      echo "  --container-image    Container image to run (default: nginx:latest)"
      echo "  --container-port     Container port (default: 80)"
      echo "  --help               Show this help message"
      exit 0
      ;;
    *)
      echo "Unknown option: $1"
      exit 1
      ;;
  esac
done

# Build CDK context parameters
CONTEXT_PARAMS=(
  "--context" "deployment_name=$DEPLOYMENT_NAME"
  "--context" "domain_name=$DOMAIN_NAME"
  "--context" "db_name=$DB_NAME"
  "--context" "db_username=$DB_USERNAME"
  "--context" "container_image=$CONTAINER_IMAGE"
  "--context" "container_port=$CONTAINER_PORT"
)

# Add optional parameters if provided
if [[ -n "$HOSTED_ZONE_ID" ]]; then
  CONTEXT_PARAMS+=("--context" "hosted_zone_id=$HOSTED_ZONE_ID")
fi

if [[ -n "$CERTIFICATE_ARN" ]]; then
  CONTEXT_PARAMS+=("--context" "certificate_arn=$CERTIFICATE_ARN")
fi

# Print deployment information
echo "Deploying ModularWebAppStack with the following parameters:"
echo "  Deployment Name: $DEPLOYMENT_NAME"
echo "  Domain Name: $DOMAIN_NAME"
echo "  DB Name: $DB_NAME"
echo "  DB Username: $DB_USERNAME"
echo "  Container Image: $CONTAINER_IMAGE"
echo "  Container Port: $CONTAINER_PORT"

if [[ -n "$HOSTED_ZONE_ID" ]]; then
  echo "  Hosted Zone ID: $HOSTED_ZONE_ID"
fi

if [[ -n "$CERTIFICATE_ARN" ]]; then
  echo "  Certificate ARN: $CERTIFICATE_ARN"
fi

# Deploy the stack
echo "Running cdk deploy..."
cd "$(dirname "$0")/.." || exit 1
python -m samples.modular_full_stack deploy ModularWebAppStack "${CONTEXT_PARAMS[@]}"
