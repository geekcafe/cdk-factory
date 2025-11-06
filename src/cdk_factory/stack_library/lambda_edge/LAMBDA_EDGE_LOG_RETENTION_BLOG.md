# The Lambda@Edge Log Retention Nightmare: A Tale of CloudFormation Frustration

## 🎭 The Setup

You've just built an amazing Lambda@Edge function. It's deployed globally, handling requests at the edge with lightning speed. You're feeling proud - until you get the AWS bill and realize those edge logs are costing you a fortune because they never expire.

"No problem," you think. "I'll just set a log retention policy in my CloudFormation template."

Famous last words.

## 🚨 The Problem: "The specified log group does not exist"

Your deployment starts, and then you see it:

```
EdgeLogRetentioneucentral180637808 - FAILED
Received response status [FAILED] from custom resource. 
Message returned: The specified log group does not exist.
```

Wait, what? How can the log group not exist? I'm deploying a Lambda function!

## 🔍 The Investigation: Understanding Lambda@Edge Logging

After hours of digging through AWS documentation and Stack Overflow posts, you discover the truth:

**Lambda@Edge log groups are created on-demand.**

Not during deployment. Not when you create the function. Only when the function is actually invoked at an edge location.

This means:
- Your CloudFormation template runs
- Lambda@Edge function gets deployed to edge locations
- Custom resource tries to set log retention
- **FAILS** because log groups don't exist yet
- Log groups get created later when someone actually uses your function

## 🤯 The Mind-Bending Architecture

Here's where it gets even more confusing:

```bash
# Log group naming pattern
/aws/lambda/{edge-region}.{function-name}

# Examples
/aws/lambda/eu-central-1.my-edge-function
/aws/lambda/ap-southeast-1.my-edge-function
/aws/lambda/us-west-2.my-edge-function

# BUT THEY'RE ALL IN us-east-1!
arn:aws:logs:us-east-1:123456789:log-group:/aws/lambda/eu-central-1.my-edge-function
```

Yes, you read that right. A log group named `/aws/lambda/eu-central-1.my-function` is physically located in `us-east-1`. This makes perfect sense to someone at AWS, apparently.

## 💡 The Failed Attempts

### Attempt 1: Custom Resource with SDK Calls
```python
cr.AwsCustomResource(
    self, "EdgeLogRetention",
    on_update={
        "service": "CloudWatchLogs",
        "action": "putRetentionPolicy",
        "parameters": {
            "logGroupName": "/aws/lambda/eu-central-1.my-function",
            "retentionInDays": 7
        }
    }
)
```
**Result**: "The specified log group does not exist"

### Attempt 2: Fix the Service Name
```
Package @aws-sdk/client-logs does not exist
```
Oh, it's `CloudWatchLogs` not `Logs`. Easy fix!

**Result**: Still "The specified log group does not exist"

### Attempt 3: Fix IAM Permissions
```python
policy=cr.AwsCustomResourcePolicy.from_statements([
    iam.PolicyStatement(
        actions=["logs:PutRetentionPolicy", "logs:DeleteRetentionPolicy"],
        resources=["arn:aws:logs:us-east-1:*:log-group:/aws/lambda/eu-central-1.my-function*"]
    )
])
```
**Result**: "User is not authorized to perform: logs:PutRetentionPolicy"

### Attempt 4: Fix Region and Permissions
```python
# All edge log groups are in us-east-1, not the edge region!
resources=["arn:aws:logs:us-east-1:*:log-group:/aws/lambda/eu-central-1.my-function*"]
```
**Result**: "The specified log group does not exist"

## 🎭 The Realization

You finally understand: **You're trying to set retention on something that doesn't exist yet.**

It's like trying to put a roof on a house before the foundation is poured. Lambda@Edge log groups are created when the function is first invoked at that edge location, which could be minutes, hours, or days after deployment.

## 🤔 The Solutions We Considered

### Solution 1: EventBridge + Lambda (The "Proper" Way)
```yaml
EventPattern:
  source: ["aws.logs"]
  detail-type: ["AWS API Call via CloudTrail"]
  detail:
    eventSource: ["logs.amazonaws.com"]
    eventName: ["CreateLogGroup"]
```

**Pros**: Real-time, automatic, handles all edge regions
**Cons**: Requires CloudTrail, another Lambda to maintain, complex setup

### Solution 2: Periodic Lambda Function (The "Good Enough" Way)
```python
def lambda_handler(event, context):
    # Scan for edge log groups every hour
    # Apply retention if needed
```

**Pros**: Simple, no CloudTrail dependency
**Cons**: Not real-time, runs even when not needed

### Solution 3: Post-Deployment Script (The "Manual" Way)
```bash
# Wait for log groups to appear
until aws logs describe-log-groups --log-group-name-prefix "/aws/lambda/eu-central-1.my-function"; do
    sleep 30
done
```

**Pros**: Direct control, no extra resources
**Cons**: Manual, timing issues, not scalable

### Solution 4: CloudWatch Subscription (The "Overkill" Way)
**Pros**: Event-driven
**Cons**: Complex, requires log group to exist first

## 🏳️ The Decision: We're Tabling This

After weighing all options, we decided to **disable edge log retention for now**:

```python
def _configure_edge_log_retention(self, function_name: str) -> None:
    # DISABLED: Edge log groups don't exist during deployment
    logger.warning("Edge log retention disabled - log groups are created on-demand")
    return
```

Why?

1. **Complexity vs. Benefit**: The solutions are complex for what should be a simple configuration
2. **Cost Impact**: We'll monitor costs and implement something if it becomes a problem
3. **AWS Responsibility**: This feels like something AWS should handle better
4. **Time Constraints**: We have features to ship, not logging architecture to perfect

## 🤷‍♂️ The Frustration

Here's what frustrates us most:

1. **No Clear Documentation**: AWS doesn't clearly document this limitation
2. **Misleading Error Messages**: "Log group does not exist" doesn't explain WHY
3. **Counterintuitive Architecture**: Why are edge logs in us-east-1?
4. **No Built-in Solution**: AWS should provide a way to set default retention

## 📣 The Call for Help

**We're throwing this out to the community:**

Has anyone solved this elegantly? Are we missing something obvious? Is there a magical CloudFormation feature we don't know about?

### What We Tried:
- ✅ Custom resources with proper IAM permissions
- ✅ Correct service names (`CloudWatchLogs` not `Logs`)
- ✅ Right region targeting (`us-east-1` for all edge logs)
- ✅ Multiple deployment approaches

### What We Need:
- 🤔 A way to set retention policies on edge log groups during deployment
- 🤔 Or a clean post-deployment solution that doesn't require manual intervention
- 🤔 Or confirmation that this is impossible and we should stop trying

## 🎯 The Current State

For now, our Lambda@Edge functions deploy successfully with a warning:

```
Edge log retention configuration disabled - log groups are created on-demand.
Desired retention: 7 days. See TODO for implementation approach.
```

We'll monitor the costs and implement one of the solutions if it becomes a real problem. But for now, we're choosing **shipping features over perfect logging architecture**.

## 🔮 The Future

Hopefully, AWS will:
1. **Document this limitation** clearly
2. **Provide a built-in solution** for edge log retention
3. **Fix the confusing architecture** (or at least explain it better)

Until then, we'll keep an eye on our logging costs and hope someone in the community has a better solution.

---

**Have you solved this? Drop your solutions in the comments! Let's save the next developer from this nightmare.**

#AWS #Lambda #CloudFormation #EdgeComputing #Frustration #LoggingNightmare
