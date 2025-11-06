# Lambda@Edge Log Retention - Implementation Plan

## 🚨 Current Status: DISABLED

Lambda@Edge log retention configuration has been **disabled** because edge log groups are created on-demand when the function is invoked at edge locations, not during CloudFormation deployment.

## 🔍 Problem Analysis

### Why Deployment-Time Configuration Fails
1. **On-Demand Creation**: Lambda@Edge log groups are created only when the function is actually invoked at edge locations
2. **Timing Issue**: CloudFormation deployment happens before any edge invocations occur
3. **Error**: `The specified log group does not exist` when trying to set retention policies

### Log Group Naming Pattern
```
Pattern: /aws/lambda/{edge-region}.{function-name}
Example: /aws/lambda/eu-central-1.trav-talks-blue-green-edge-function
Location: All edge log groups are created in us-east-1
```

## 💡 Proposed Solutions

### Solution 1: EventBridge + Lambda (Recommended)
```yaml
# EventBridge rule to detect log group creation
EventPattern:
  source: ["aws.logs"]
  detail-type: ["AWS API Call via CloudTrail"]
  detail:
    eventSource: ["logs.amazonaws.com"]
    eventName: ["CreateLogGroup"]
    requestParameters:
      logGroupName: ["/aws/lambda/*.edge-function"]
```

**Implementation:**
1. Create EventBridge rule that triggers on log group creation
2. Lambda function receives event and sets retention policy
3. Automatic handling of new edge log groups

**Pros:**
- Automatic and real-time
- No manual intervention required
- Handles all edge regions

**Cons:**
- Additional Lambda function to maintain
- Requires CloudTrail enabled for CloudWatch Logs

### Solution 2: Periodic Lambda Function
```python
def lambda_handler(event, context):
    # Scan for edge log groups
    log_groups = logs.describe_log_groups(
        logGroupNamePrefix='/aws/lambda/eu-central-1.trav-talks-blue-green-edge-function'
    )
    
    # Apply retention policy
    for log_group in log_groups['logGroups']:
        logs.put_retention_policy(
            logGroupName=log_group['logGroupName'],
            retentionInDays=7
        )
```

**Implementation:**
1. Create Lambda function on schedule (e.g., every hour)
2. Scan for edge log groups with function name pattern
3. Apply retention policy if not already set

**Pros:**
- Simple to implement
- No CloudTrail dependency
- Can handle existing log groups

**Cons:**
- Not real-time (delayed retention)
- Runs periodically even when not needed

### Solution 3: Post-Deployment Script
```bash
#!/bin/bash
# Wait for edge log groups to appear
function_name="trav-talks-blue-green-edge-function"
edge_regions=("eu-central-1" "eu-west-1" "ap-southeast-1")

for region in "${edge_regions[@]}"; do
    log_group="/aws/lambda/${region}.${function_name}"
    
    # Wait for log group to exist
    until aws logs describe-log-groups --log-group-name-prefix "$log_group" --region us-east-1; do
        echo "Waiting for log group: $log_group"
        sleep 30
    done
    
    # Set retention policy
    aws logs put-retention-policy --log-group-name "$log_group" --retention-in-days 7 --region us-east-1
done
```

**Implementation:**
1. Script runs after Lambda@Edge deployment
2. Waits for edge log groups to be created
3. Sets retention policies when they appear

**Pros:**
- Direct control over timing
- No additional AWS resources needed

**Cons:**
- Manual process
- Hard to determine when log groups will appear
- Not automated

### Solution 4: CloudWatch Logs Subscription
```python
# Lambda triggered by log group creation via subscription filter
def lambda_handler(event, context):
    for record in event['Records']:
        log_group = record['logGroup']
        if 'edge-function' in log_group:
            # Set retention policy
            logs.put_retention_policy(
                logGroupName=log_group,
                retentionInDays=7
            )
```

**Implementation:**
1. Create subscription filter on log group pattern
2. Lambda function triggered by log events
3. Set retention policy on first log event

**Pros:**
- Event-driven
- No CloudTrail needed

**Cons:**
- Requires log group to exist first
- Complex subscription filter setup

## 🎯 Recommended Implementation

### Phase 1: Quick Win (Solution 2)
Implement periodic Lambda function as temporary solution:
- Easy to implement quickly
- Solves immediate problem
- Can be replaced later with better solution

### Phase 2: Production Solution (Solution 1)
Implement EventBridge + Lambda for production:
- Real-time response
- Automatic handling
- Best long-term solution

## 📋 Implementation Steps for Solution 1

### 1. Create EventBridge Rule
```python
event_rule = events.Rule(
    self, "EdgeLogGroupRule",
    event_pattern=events.EventPattern(
        source=["aws.logs"],
        detail_type=["AWS API Call via CloudTrail"],
        detail={
            "eventSource": ["logs.amazonaws.com"],
            "eventName": ["CreateLogGroup"],
            "requestParameters": {
                "logGroupName": [{"prefix": "/aws/lambda/"}]
            }
        }
    )
)
```

### 2. Create Lambda Function
```python
retention_handler = _lambda.Function(
    self, "EdgeLogRetentionHandler",
    runtime=_lambda.Runtime.PYTHON_3_9,
    handler="handler.lambda_handler",
    code=_lambda.Code.from_asset("lambda/edge_log_retention"),
    environment={
        "RETENTION_DAYS": "7",
        "FUNCTION_NAME_PATTERN": "*edge-function"
    }
)
```

### 3. Add Permissions
```python
retention_handler.add_to_role_policy(
    iam.PolicyStatement(
        actions=["logs:PutRetentionPolicy", "logs:DescribeLogGroups"],
        resources=["*"]
    )
)
```

### 4. Connect EventBridge to Lambda
```python
event_rule.add_target(targets.LambdaFunction(retention_handler))
```

## 🔧 Current Configuration

The edge log retention configuration is currently **disabled** in the Lambda Edge stack:

```python
def _configure_edge_log_retention(self, function_name: str) -> None:
    # DISABLED: See implementation plan above
    logger.warning("Edge log retention disabled - see TODO for implementation")
    return
```

## 📊 Configuration Impact

| Setting | Current Behavior | Target Behavior |
|---------|------------------|-----------------|
| `edge_log_retention_days` | Warning logged, no action applied | Retention policy set on all edge log groups |
| Edge log groups | Created with default retention (never expire) | Created with specified retention (e.g., 7 days) |
| Cost impact | Potential high log storage costs | Controlled log storage costs |

---

**Status**: Ready for implementation when edge log retention is required.
