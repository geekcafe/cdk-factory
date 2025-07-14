#!/usr/bin/env bash
set -euo pipefail

ENV_FILE=".env.cdk"

# —— 0) Load persisted defaults if present ——
if [ -f "$ENV_FILE" ]; then
  # shellcheck disable=SC1090
  . "$ENV_FILE"
fi

# —— 1) Ensure our variables exist (even if empty) ——
: "${AWS_ACCOUNT_NUMBER:=""}"
: "${AWS_ACCOUNT_REGION:=""}"
: "${ENVIRONMENT:=""}"
: "${WORKLOAD_NAME:=""}"
: "${AWS_PROFILE:=""}"
: "${API_GATEWAY_NAME:=""}"
: "${DEPLOYED_USER_POOL_ARN:=""}"

# —— 2) Prompt helper — accepts Enter to keep default ——
prompt_default() {
  local _var=$1 _curr=$2 _label=$3
  read -p "${_label} [${_curr}]: " input
  # if input is empty, keep current; otherwise overwrite
  printf -v "$_var" '%s' "${input:-$_curr}"
}

prompt_default AWS_ACCOUNT_NUMBER "$AWS_ACCOUNT_NUMBER"  "AWS_ACCOUNT_NUMBER"
prompt_default AWS_ACCOUNT_REGION "$AWS_ACCOUNT_REGION"  "AWS_ACCOUNT_REGION"
prompt_default ENVIRONMENT           "$ENVIRONMENT"            "ENVIRONMENT"
prompt_default WORKLOAD_NAME         "$WORKLOAD_NAME"          "WORKLOAD_NAME"
prompt_default AWS_PROFILE           "$AWS_PROFILE"            "AWS_PROFILE (optional)"
prompt_default API_GATEWAY_NAME      "$API_GATEWAY_NAME"       "API_GATEWAY_NAME"
prompt_default DEPLOYED_USER_POOL_ARN "$DEPLOYED_USER_POOL_ARN" "DEPLOYED_USER_POOL_ARN"

# —— 3) Validate required inputs ——
missing=()
for v in AWS_ACCOUNT_NUMBER AWS_ACCOUNT_REGION ENVIRONMENT WORKLOAD_NAME API_GATEWAY_NAME DEPLOYED_USER_POOL_ARN; do
  if [ -z "${!v}" ]; then
    missing+=( "$v" )
  fi
done
if [ ${#missing[@]} -gt 0 ]; then
  echo "❌ Missing required: ${missing[*]}"
  exit 1
fi

# —— 4) Action: synth or deploy ——
read -p "Action (synth/deploy) [synth]: " choice
ACTION="${choice:-synth}"
# lowercase in POSIX
ACTION="$(printf '%s' "$ACTION" | tr '[:upper:]' '[:lower:]')"
if [ "$ACTION" != "synth" ] && [ "$ACTION" != "deploy" ]; then
  echo "Invalid action: $ACTION"
  exit 1
fi

# —— 5) Build CDK command ——
CDK_CMD=( cdk "$ACTION" )
[ -n "$AWS_PROFILE" ] && CDK_CMD+=( --profile "$AWS_PROFILE" )
CDK_CMD+=(
  -c CdkConfigPath=../../samples/api-gateway/config_min.json
  -c AccountNumber="$AWS_ACCOUNT_NUMBER"
  -c AccountRegion="$AWS_ACCOUNT_REGION"
  -c Environment="$ENVIRONMENT"
  -c WorkloadName="$WORKLOAD_NAME"
  -c ApiGatewayName="$API_GATEWAY_NAME"
  -c DeployedUserPoolArn="$DEPLOYED_USER_POOL_ARN"
)

# —— 6) Persist for next time ——  
cat > "$ENV_FILE" <<EOF
export AWS_ACCOUNT_NUMBER="$AWS_ACCOUNT_NUMBER"
export AWS_ACCOUNT_REGION="$AWS_ACCOUNT_REGION"
export ENVIRONMENT="$ENVIRONMENT"
export WORKLOAD_NAME="$WORKLOAD_NAME"
export API_GATEWAY_NAME="$API_GATEWAY_NAME"
export DEPLOYED_USER_POOL_ARN="$DEPLOYED_USER_POOL_ARN"
export AWS_PROFILE="$AWS_PROFILE"
EOF
echo "✅ Saved settings to $ENV_FILE"

# —— 7) Run it ——
echo "→ ${CDK_CMD[*]}"
"${CDK_CMD[@]}"
