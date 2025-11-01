# Missing Implementations

This document tracks features that are partially implemented or missing from the CDK Factory stacks.

## Auto Scaling Stack - Scaling Policies

### Currently Implemented
- **Target Tracking CPU Utilization**: Basic CPU-based target tracking scaling policies
- **Update Policies**: Basic rolling update configuration

### Missing Implementations
- **Step Scaling Policies**: 
  - Custom metric-based step scaling
  - Multiple steps with lower/upper bounds
  - Custom scaling adjustments
- **Target Tracking Custom Metrics**:
  - Memory utilization
  - Request count
  - Custom CloudWatch metrics
- **Scheduled Scaling**:
  - Time-based scaling actions
  - Recurring schedules

### Test Configuration Issues
The `test_custom_scale_configuration` test uses scaling policy configurations that are not yet implemented:
- Step scaling with custom metrics (RequestCount)
- Multiple step configurations with lower/upper bounds
- Target tracking with non-CPU metrics

### Implementation Priority
1. **High**: Step scaling policies
2. **Medium**: Custom target tracking metrics  
3. **Low**: Scheduled scaling

### Files to Update
- `src/cdk_factory/stack_library/auto_scaling/auto_scaling_stack_standardized.py` - `_add_scaling_policies()` method
- `src/cdk_factory/configurations/resources/auto_scaling.py` - Scaling policy configuration models
- `tests/unit/test_auto_scaling_stack.py` - Test configurations

---

## Other Missing Implementations

*This document will be updated as other missing implementations are identified.*
