# Pipeline Stage Stable IDs

## Problem

Pipeline stage names were being used as CloudFormation construct IDs, causing resource replacements when stage names changed.

### Example Issue

**Before Fix:**
```
Stage config: "name": "Database"
CloudFormation Logical ID: prodworkloadcorepipelineDatabaseprodworkloadrdsworkloadprodrdsinstanceSecret...
```

If you renamed the stage from "Database" to "RDS Deploy", CloudFormation would:
1. Detect the logical ID change
2. Create new resources (including a new RDS instance!)
3. Delete old resources (data loss!)

## Solution

**Added `stable_id` property to `PipelineStageConfig`** that generates construct IDs based on stack names instead of human-readable stage names.

### Implementation

```python
@property
def stable_id(self) -> str:
    """
    Returns a stable construct ID for the stage based on stack names.
    This ensures CloudFormation logical IDs don't change when stage names are renamed.
    """
    if self.stacks and len(self.stacks) > 0:
        stack_name = self.stacks[0].name  # e.g., "prod-workload-rds"
        parts = stack_name.split('-')
        if len(parts) > 2:
            stable_name = parts[-1]  # Extract "rds"
        else:
            stable_name = stack_name
        return re.sub(r'[^a-zA-Z0-9-]', '', stable_name)
    
    # Fallback to sanitized stage name
    return re.sub(r'[^a-zA-Z0-9-]', '', self.name)
```

**After Fix:**
```
Stage config: "name": "Database" (or any other name)
CloudFormation Logical ID: prodworkloadcorepipelinerdsprodworkloadrdsworkloadprodrdsinstanceSecret...
                                            ^^^
                                            Stable! Derived from stack name
```

## Usage

The change is transparent - no config updates needed. The pipeline factory automatically uses `stage.stable_id` instead of `stage.name`:

```python
# Before
pipeline_stage = PipelineStage(self, stage.name, **kwargs)

# After
pipeline_stage = PipelineStage(self, stage.stable_id, **kwargs)
```

## Impact

### For New Deployments
- No impact - stable IDs are used from the start

### For Existing Deployments
- **Warning:** First deployment after this change will cause resource replacement
- **Reason:** Logical IDs will change from stage name to stable ID
- **Recommendation:** Deploy during maintenance window

### Migration Strategy

1. **Review Changes:**
   ```bash
   cdk diff
   ```
   Look for resources marked as replacement

2. **For Stateful Resources (RDS, S3, etc.):**
   - Schedule maintenance window
   - Consider manual resource migration if needed
   - Verify backups exist

3. **For Stateless Resources:**
   - Safe to replace
   - May cause brief downtime during replacement

## Benefits

- ✅ Rename pipeline stages without affecting infrastructure
- ✅ Cleaner, more predictable CloudFormation logical IDs
- ✅ Stack-based IDs reflect actual resources being deployed
- ✅ No config changes required

## Examples

### Stage: Database (Stack: prod-workload-rds)
- **Old ID:** `Database`
- **New ID:** `rds`

### Stage: Storage (Stacks: prod-workload-media-bucket, prod-workload-backup-bucket)
- **Old ID:** `Storage`
- **New ID:** `mediabucket` (from first stack)

### Stage: Networking (Stack: prod-workload-vpc)
- **Old ID:** `Networking`
- **New ID:** `vpc`

## Related Files

- `/src/cdk_factory/configurations/pipeline_stage.py` - Stable ID property
- `/src/cdk_factory/pipeline/pipeline_factory.py` - Uses stable_id for construct creation

## Version

- **Added:** 2025-11-17
- **Version:** Next release after 0.34.3
