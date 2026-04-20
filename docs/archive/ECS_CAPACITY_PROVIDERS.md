# ECS Capacity Providers - Automatic Instance Scaling

## Overview

ECS Capacity Providers enable **fully automated ASG scaling** based on actual task placement needs. This eliminates manual ASG scaling policies and ensures optimal capacity during normal operations and deployments.

## What Problem Does This Solve?

### Without Capacity Providers (Manual Scaling)

```
❌ Manual ASG Scaling:
  - Define threshold-based scaling policies (CPU > 75%)
  - Tune thresholds to prevent under/over-provisioning
  - May not scale for deployments
  - Reactive (scales after metrics breach)
  - Complex to configure correctly

Result: Either under-provisioned (task failures) or over-provisioned (wasted cost)
```

### With Capacity Providers (Automatic Scaling)

```
✅ Automatic ECS-Managed Scaling:
  - ECS monitors task placement attempts
  - Scales ASG proactively when tasks can't be placed
  - Handles deployment scenarios automatically
  - Maintains target capacity utilization
  - No manual policies or thresholds to tune

Result: Right-sized capacity at all times, automatic deployment support
```

## How It Works

### 1. ECS Monitors Cluster Capacity

```
ECS continuously tracks:
  - Available capacity (CPU, Memory, Ports)
  - Pending tasks (waiting for placement)
  - Running tasks (consuming capacity)
  - Target capacity percentage (default: 100%)
```

### 2. Capacity Provider Scales ASG

```
When tasks can't be placed:
  1. ECS detects insufficient capacity
  2. Capacity provider calculates needed instances
  3. ASG scales up (respecting min/max bounds)
  4. Instances register with cluster
  5. ECS places pending tasks

When capacity is underutilized:
  1. ECS detects excess capacity
  2. Capacity provider identifies unused instances
  3. Drains tasks from target instances
  4. ASG scales down (respecting min bound)
```

### 3. Deployment Scenario

```
Normal: 2 instances, 2 tasks
↓
Deployment starts (needs 4 tasks temporarily)
↓
ECS detects: Need capacity for 2 more tasks
↓
Capacity provider scales ASG: 2 → 3 instances
↓
Deployment completes: 4 tasks finish, 2 old tasks stop
↓
Back to: 2 tasks running
↓
Capacity provider scales down: 3 → 2 instances
```

**All automatic - no manual intervention required!**

## Configuration

### Cluster Stack Configuration

**File:** `config-03-stage-01-ecs-cluster.json`

```json
{
  "module": "ecs_cluster_stack",
  "ecs_cluster": {
    "name": "prod-workload-cluster",
    "capacity_providers": [
      {
        "name": "prod-workload-capacity-provider",
        "auto_scaling_group_arn": "{{ssm:/prod/workload/asg/arn}}",
        "target_capacity": 100,
        "minimum_scaling_step_size": 1,
        "maximum_scaling_step_size": 4,
        "instance_warmup_period": 300
      }
    ],
    "default_capacity_provider_strategy": [
      {
        "capacity_provider": "prod-workload-capacity-provider",
        "weight": 1,
        "base": 0
      }
    ]
  }
}
```

### Configuration Parameters

#### Capacity Provider Settings

**`name`** (required)
- Name of the capacity provider
- Must be unique within the cluster
- Example: `"prod-workload-capacity-provider"`

**`auto_scaling_group_arn`** (required)
- ARN of the ASG to manage
- Can use SSM parameter reference: `"{{ssm:/path/to/asg/arn}}"`
- ASG must be deployed before cluster stack

**`target_capacity`** (optional, default: 100)
- Target cluster capacity utilization percentage
- Range: 1-100
- Higher = more efficient, lower = more buffer
- **Recommended:** 100 for cost optimization
- Use 80-90 if you want spare capacity buffer

**`minimum_scaling_step_size`** (optional, default: 1)
- Minimum number of instances to add/remove per scaling event
- Range: 1-10000
- **Recommended:** 1 for gradual scaling

**`maximum_scaling_step_size`** (optional, default: 10)
- Maximum number of instances to add/remove per scaling event
- Range: 1-10000
- **Recommended:** 4-10 based on traffic patterns

**`instance_warmup_period`** (optional, default: 300)
- Seconds to wait after instance launch before considering it ready
- Allows time for ECS agent registration and health checks
- **Recommended:** 300 (5 minutes) for most cases

#### Capacity Provider Strategy

**`capacity_provider`** (required)
- Name of the capacity provider to use
- Must match a provider defined in `capacity_providers` array

**`weight`** (optional, default: 1)
- Relative weight when using multiple providers
- Higher weight = more tasks placed on this provider
- Example: weight=2 gets twice as many tasks as weight=1

**`base`** (optional, default: 0)
- Minimum number of tasks to place on this provider
- Remaining tasks distributed by weight
- **Recommended:** 0 for single provider setups

### ASG Stack Configuration

**File:** `config-03-stage-02-ecs-asg-launch-template.json`

Must export ASG ARN to SSM:

```json
{
  "module": "auto_scaling_stack",
  "auto_scaling": {
    "min_capacity": 2,
    "max_capacity": 6,
    "desired_capacity": 2,
    "ssm": {
      "exports": {
        "auto_scaling_group_name": "/prod/workload/asg/name",
        "auto_scaling_group_arn": "/prod/workload/asg/arn"
      }
    }
  }
}
```

**Important:** Remove manual scaling policies - capacity provider handles all scaling!

### Service Stack Configuration

**File:** `config-03-stage-03-ecs-service-taskdef.json`

No changes needed! Task auto-scaling continues to work:

```json
{
  "module": "ecs_service_stack",
  "ecs_service": {
    "launch_type": "EC2",
    "desired_count": 2,
    "enable_auto_scaling": true,
    "min_capacity": 2,
    "max_capacity": 10,
    "auto_scaling_target_cpu": 70,
    "auto_scaling_target_memory": 80
  }
}
```

## Scaling Behavior

### Target Capacity Explained

The `target_capacity` parameter controls how aggressively the capacity provider scales:

**target_capacity: 100** (Maximum efficiency)
```
Goal: Keep cluster at 100% utilization
- No spare capacity
- Scales up immediately when tasks pending
- Scales down quickly when tasks stop
- Most cost-effective
- Recommended for production
```

**target_capacity: 90** (Small buffer)
```
Goal: Keep cluster at 90% utilization
- Maintains ~10% spare capacity
- Scales up proactively before 100%
- Slower to scale down
- Good for variable workloads
```

**target_capacity: 75** (Large buffer)
```
Goal: Keep cluster at 75% utilization
- Maintains ~25% spare capacity
- Scales up well before needed
- Much slower to scale down
- Use for highly variable or spiky workloads
```

### Scaling Examples

#### Example 1: Normal Traffic (target_capacity: 100)

```
State: 2 instances (t3.small: 2 vCPU, 2GB each)
       2 tasks (512 CPU units, 1024 MB each)

Cluster capacity:
  Available: 4000 CPU units, 4096 MB
  Used:      1024 CPU units, 2048 MB
  Utilization: 25% CPU, 50% Memory

Capacity provider action: No scaling (under target)
```

#### Example 2: Traffic Spike (target_capacity: 100)

```
Step 1: Traffic increases
  - Task CPU hits 75%
  - ECS Service scales: 2 → 5 tasks

Step 2: ECS attempts to place 3 new tasks
  - Need: 1536 CPU units, 3072 MB
  - Available: 2976 CPU units, 2048 MB
  - Result: Only 2 of 3 tasks can be placed (not enough memory)

Step 3: Capacity provider detects pending tasks
  - 1 task waiting for placement
  - Calculates: Need 1 more instance
  - ASG scales: 2 → 3 instances

Step 4: New instance registers
  - After warmup period (300s)
  - Adds: 2000 CPU units, 2048 MB
  - Pending task gets placed

Final state: 3 instances, 5 tasks running
```

#### Example 3: Deployment (target_capacity: 100)

```
Initial: 2 instances, 3 tasks

Deployment config:
  maximum_percent: 200 (can run 6 tasks during deployment)
  minimum_healthy_percent: 50 (must keep 2 tasks)

Step 1: Deployment starts
  - ECS tries to start 3 new tasks (total: 6)
  - Need: 3072 CPU units, 6144 MB
  - Available: 4000 CPU units, 4096 MB
  - Result: Not enough memory for all 6

Step 2: Capacity provider scales
  - ASG scales: 2 → 3 instances
  - New capacity: 6000 CPU units, 6144 MB
  - All 6 tasks can now run

Step 3: Deployment completes
  - Old 3 tasks stop
  - Back to 3 tasks running
  
Step 4: Capacity provider detects underutilization
  - Only using 50% of capacity
  - After scale-in protection expires
  - ASG scales: 3 → 2 instances

Final: 2 instances, 3 tasks (same as start)
```

## Best Practices

### 1. Set Appropriate ASG Bounds

```json
{
  "min_capacity": 2,    // Always keep 2 for HA
  "max_capacity": 10,   // Cap cost exposure
  "desired_capacity": 2 // Capacity provider manages this
}
```

**Don't set `desired_capacity` too high** - capacity provider will manage it.

### 2. Size Instances for Task Requirements

```
If task needs: 512 CPU, 1024 MB
Instance options:
  ✅ t3.small (2 vCPU, 2GB) = 3-4 tasks per instance
  ✅ t3.medium (2 vCPU, 4GB) = 6-7 tasks per instance
  ❌ t3.micro (1 vCPU, 1GB) = 1 task per instance (inefficient scaling)
```

### 3. Configure Instance Warmup

```json
{
  "instance_warmup_period": 300  // 5 minutes
}
```

- Too short: Tasks placed before instance ready (fails)
- Too long: Slower scaling, higher costs
- **Recommended:** 300s (5 min) for most workloads

### 4. Set Maximum Step Size Based on Traffic

```json
{
  "minimum_scaling_step_size": 1,
  "maximum_scaling_step_size": 4  // Scale 4 instances at once
}
```

**Steady traffic:** Use 1-2 (gradual scaling)
**Spiky traffic:** Use 4-10 (fast response)

### 5. Remove Manual ASG Scaling Policies

```json
{
  "auto_scaling": {
    // ❌ REMOVE THIS - Conflicts with capacity provider
    "scaling_policies": [...]
  }
}
```

Capacity provider and manual policies will conflict!

## Monitoring

### Key Metrics

**CloudWatch Metrics to Monitor:**

**ECS Cluster:**
- `CPUReservation` - % of cluster CPU reserved
- `MemoryReservation` - % of cluster memory reserved
- `RegisteredContainerInstancesCount` - Number of EC2 instances

**ECS Service:**
- `CPUUtilization` - Actual CPU usage
- `MemoryUtilization` - Actual memory usage
- `RunningTaskCount` - Healthy tasks

**Capacity Provider:**
- No direct metrics exposed
- Monitor via cluster capacity and ASG metrics

**Auto Scaling Group:**
- `GroupDesiredCapacity` - Target instances (managed by CP)
- `GroupInServiceInstances` - Healthy instances
- `GroupPendingInstances` - Launching instances

### CloudWatch Alarms

```yaml
HighCPUReservation:
  Metric: CPUReservation
  Threshold: > 90%
  Evaluation: 2 periods of 5 minutes
  Action: Alert if consistently high (may hit max capacity)

HighMemoryReservation:
  Metric: MemoryReservation
  Threshold: > 90%
  Evaluation: 2 periods of 5 minutes
  Action: Alert if consistently high

PendingTasks:
  Custom Metric: Tasks in PENDING state
  Threshold: > 0 for 10 minutes
  Action: Alert - capacity provider may be at max or failing
```

## Troubleshooting

### Issue 1: Tasks Stuck in PENDING

**Symptoms:**
- Tasks show PENDING status for > 5 minutes
- CloudWatch shows `CapacityProviderReservation` not increasing

**Causes:**
1. ❌ ASG at max capacity
2. ❌ Instance warmup period too short
3. ❌ ECS agents not registering

**Solutions:**
```bash
# Check ASG capacity
aws autoscaling describe-auto-scaling-groups \
  --auto-scaling-group-names "prod-workload-asg"

# Check instance count vs max
# If at max, increase max_capacity in config

# Check ECS instances
aws ecs list-container-instances \
  --cluster prod-workload-cluster

# Check instance registration
aws ecs describe-container-instances \
  --cluster prod-workload-cluster \
  --container-instances <id>
```

### Issue 2: Slow Scaling During Traffic Spike

**Symptoms:**
- Traffic spike hits
- Tasks scale up quickly
- Instances scale up slowly (> 10 minutes)

**Causes:**
- Instance warmup period too long
- Maximum step size too small
- EC2 instance launch time

**Solutions:**
```json
{
  "instance_warmup_period": 180,      // Reduce to 3 min
  "maximum_scaling_step_size": 10,    // Scale more aggressively
  "min_capacity": 3                   // Keep more instances warm
}
```

### Issue 3: Excessive Scaling (Flapping)

**Symptoms:**
- ASG constantly scaling up/down
- Instances launch and terminate rapidly

**Causes:**
- `target_capacity` too high (100%)
- Tasks have highly variable CPU/memory
- Deployment config causes temporary overload

**Solutions:**
```json
{
  "target_capacity": 85,  // Leave 15% buffer
  "instance_warmup_period": 300,  // Allow stabilization
  "minimum_scaling_step_size": 1  // Scale gradually
}
```

### Issue 4: Capacity Provider Not Scaling

**Symptoms:**
- Tasks pending
- ASG stuck at `desired_capacity`
- No scaling events

**Causes:**
1. ❌ Capacity provider not associated with cluster
2. ❌ ASG ARN incorrect in config
3. ❌ Managed termination protection preventing scale-down

**Solutions:**
```bash
# Verify capacity provider association
aws ecs describe-clusters \
  --clusters prod-workload-cluster \
  --include ATTACHMENTS

# Check capacity provider exists
aws ecs describe-capacity-providers \
  --capacity-providers prod-workload-capacity-provider

# Verify ASG ARN matches
aws ssm get-parameter --name "/prod/workload/asg/arn"
```

## Migration from Manual Scaling

### Step 1: Deploy Capacity Provider Configuration

Update configs and deploy cluster stack:

```bash
# Update configs (as shown in Configuration section)
# Deploy cluster stack with capacity providers
cdk deploy prod-workload-ecs-cluster-stack
```

### Step 2: Remove Manual Scaling Policies

Update ASG config:

```json
{
  "auto_scaling": {
    // Remove scaling_policies section
    "min_capacity": 2,
    "max_capacity": 6,
    "desired_capacity": 2
  }
}
```

Deploy ASG stack:

```bash
cdk deploy prod-workload-ecs-asg-stack
```

### Step 3: Monitor and Tune

Watch for 24-48 hours:
- Monitor task placement
- Check scaling events
- Adjust `target_capacity` if needed
- Tune step sizes based on traffic

## Capacity Provider vs Manual Scaling

| Feature | Manual Scaling | Capacity Provider |
|---------|---------------|-------------------|
| **Setup Complexity** | High | Low |
| **Deployment Scaling** | ❌ May fail | ✅ Automatic |
| **Threshold Tuning** | ❌ Required | ✅ Not needed |
| **Cost Efficiency** | ⚠️ If tuned well | ✅ Optimal |
| **Scaling Speed** | ⚠️ Reactive | ✅ Proactive |
| **Maintenance** | ❌ High | ✅ Low |
| **AWS Recommended** | ❌ Legacy | ✅ Best practice |

## Cost Impact

### Before (Manual Scaling)

```
Scenario: Peak traffic 4 hours/day

Manual policy: Scale at 75% CPU
  - Over-provision: Keep 4 instances always
  - Cost: 4 × $0.042/hr × 720hr = $120.96/month
  - Utilization: 40% average
```

### After (Capacity Provider)

```
Same scenario with capacity provider:

target_capacity: 100%
  - Right-size: 2 instances off-peak, 4-6 at peak
  - Average: 3 instances
  - Cost: 3 × $0.042/hr × 720hr = $90.72/month
  - Utilization: 85% average
  - Savings: $30.24/month (25%)
```

## Conclusion

ECS Capacity Providers provide:

1. ✅ **Automatic scaling** - No manual policies needed
2. ✅ **Deployment support** - Handles temporary capacity needs
3. ✅ **Cost optimization** - Right-sized capacity at all times
4. ✅ **Simplified operations** - Less configuration, fewer alerts
5. ✅ **AWS best practice** - Recommended approach for EC2 launch type

**Recommendation:** Always use Capacity Providers for EC2 launch type in production.

---

**Version:** 1.0  
**Last Updated:** November 19, 2025  
**CDK Factory Version:** 0.40.0+  
**Related Docs:**
- `ECS_EC2_SCALING_ARCHITECTURE.md`
- `STATIC_WEBSITE_STACK_CONFIGURATION.md`
