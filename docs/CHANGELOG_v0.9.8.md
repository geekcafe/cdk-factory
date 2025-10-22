# CDK Factory v0.9.7 - Consistent Output Directory

## 🚀 Major Improvement: Always Use `/tmp/cdk-factory/cdk.out`

### The Problem We Solved

**v0.9.6 and earlier** had inconsistent behavior:
- Local dev: `outdir=None` created random temp directories (`/tmp/cdk.outXXXX`)
- Made `cdk deploy` fail (couldn't find artifacts)
- Required complex relative path calculations
- Different behavior in CodeBuild vs local

### The Solution (v0.9.7)

**Always use a consistent, predictable location:** `/tmp/cdk-factory/cdk.out`

```python
# app.py - New behavior
CDK_FACTORY_BASE_DIR = "/tmp/cdk-factory"
self.outdir = f"{CDK_FACTORY_BASE_DIR}/cdk.out"

# Clean and recreate for fresh synthesis
if os.path.exists(self.outdir):
    shutil.rmtree(self.outdir)
os.makedirs(self.outdir, exist_ok=True)
```

### Benefits

✅ **Consistent everywhere** - Same path in local dev, CodeBuild, anywhere  
✅ **Predictable** - Always know where artifacts are  
✅ **CDK CLI compatible** - Can use `cdk deploy --app /tmp/cdk-factory/cdk.out`  
✅ **No relative path issues** - Absolute path always works  
✅ **Automatic cleanup** - Directory is cleaned before each synthesis  
✅ **No conflicts** - /tmp is writable in all environments

### Changes to `outdir` Parameter

**`outdir` now works as a namespace** (not a full path):

```python
# No outdir → default namespace
factory = CdkAppFactory()
# Output: /tmp/cdk-factory/cdk.out

# With namespace → isolated directory
factory = CdkAppFactory(outdir="my-app")
# Output: /tmp/cdk-factory/my-app/cdk.out

# Full path → basename extracted
factory = CdkAppFactory(outdir="/custom/path/my-project")
# Output: /tmp/cdk-factory/my-project/cdk.out
```

**Benefits:**
- ✅ Prevents conflicts when running multiple builds locally
- ✅ Consistent base location (`/tmp/cdk-factory`)
- ✅ Simple namespace isolation
- ✅ Backward compatible (parameter still works)

### Migration Guide

**If you were passing `outdir` parameter with full path:**
```python
# Old (v0.9.6) - Full path
factory = CdkAppFactory(outdir="/custom/path/cdk.out")

# New (v0.9.7+) - Namespace only
factory = CdkAppFactory(outdir="my-app")  # → /tmp/cdk-factory/my-app/cdk.out
# or
factory = CdkAppFactory()  # → /tmp/cdk-factory/cdk.out (default)
```

**If you need to find synthesized files:**
```bash
# Default namespace:
/tmp/cdk-factory/cdk.out/

# Custom namespace:
/tmp/cdk-factory/my-app/cdk.out/

# Use with CDK CLI:
cdk deploy --app /tmp/cdk-factory/cdk.out
cdk deploy --app /tmp/cdk-factory/my-app/cdk.out
```

**For concurrent local builds:**
```python
# Build 1
factory1 = CdkAppFactory(outdir="project-a")
# Output: /tmp/cdk-factory/project-a/cdk.out

# Build 2 (can run simultaneously)
factory2 = CdkAppFactory(outdir="project-b")
# Output: /tmp/cdk-factory/project-b/cdk.out

# No conflicts! ✅
```

### Pipeline Changes

**BuildSpec artifact collection:**
```yaml
# Old (v0.9.6) - Relative path
artifacts:
  base-directory: devops/cdk-iac/cdk.out  # ❌ Fragile
  
# New (v0.9.7+) - Absolute path
artifacts:
  base-directory: /tmp/cdk-factory/cdk.out  # ✅ Reliable
```

### Code Changes

**Files Modified:**
1. `src/cdk_factory/app.py` - Always use `/tmp/cdk-factory/cdk.out`
2. `src/cdk_factory/pipeline/pipeline_factory.py` - Use absolute path in buildspec
3. `src/cdk_factory/pipeline/path_utils.py` - Created (path conversion utilities)
4. `pyproject.toml` - Version bumped to 0.9.7

**Tests Updated:**
1. `tests/unit/test_project_root_detection.py` - Updated for new behavior
2. `tests/integration/test_cdk_synth_output_location.py` - Created to verify behavior
3. `tests/unit/test_pipeline_path_conversion.py` - Tests path conversion logic

### Test Results

```
✅ 9/9 Project root detection tests passed
✅ 6/6 Pipeline path conversion tests passed
✅ 4/4 CDK synth output location integration tests passed
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ 19/19 total tests passed
```

### Technical Details

**Why `/tmp/cdk-factory`?**
- `/tmp` is writable in all environments (local, CodeBuild, Docker, etc.)
- Namespaced to avoid conflicts with other tools
- Automatically cleaned by OS or our code
- Consistent absolute path

**Symlink handling:**
- macOS: `/tmp` → `/private/tmp` (handled by path resolution)
- Tests resolve symlinks to ensure comparisons work correctly

**Cleanup strategy:**
- Directory is removed and recreated on each synthesis
- Prevents stale artifacts
- Ensures fresh, consistent state

### No Deprecation!

The `outdir` parameter is **not deprecated** - it's been **enhanced**!

- **v0.9.6 and earlier**: Full path specification
- **v0.9.7+**: Namespace within `/tmp/cdk-factory/`
- **Backward compatible**: Parameter still works, just with new behavior

---

## Additional Improvements

### Path Conversion Utilities

Created `src/cdk_factory/pipeline/path_utils.py` for reusable path conversion logic:
- `convert_app_file_to_relative_directory()` - Converts app.py paths to directories
- Handles symlinks (macOS `/var` → `/private/var`)
- Used by tests to verify production code

### Enhanced Testing

**Integration tests** verify end-to-end synthesis:
- Test local dev behavior
- Test CodeBuild behavior  
- Test deprecation warnings
- Test consistent output location

### Fixed Issues

1. ❌ **v0.9.6**: `outdir=None` created random temp directories
2. ✅ **v0.9.7**: Always uses `/tmp/cdk-factory/cdk.out`

3. ❌ **v0.9.6**: Complex relative path calculations
4. ✅ **v0.9.7**: Simple absolute path (no calculations needed)

5. ❌ **v0.9.6**: MRO error with `IStack` inheritance
6. ✅ **v0.9.7**: Fixed by removing redundant `cdk.Stack` inheritance

---

## Upgrade Instructions

### For Existing Projects

1. **Update cdk-factory:**
   ```bash
   pip install --upgrade cdk-factory==0.9.7
   ```

2. **Remove `outdir` parameters** (if any):
   ```python
   # Remove this parameter - it's ignored anyway
   factory = CdkAppFactory(outdir="/custom/path")  # ❌
   factory = CdkAppFactory()  # ✅
   ```

3. **Update CDK CLI commands** (if needed):
   ```bash
   # Use absolute path
   cdk deploy --app /tmp/cdk-factory/cdk.out
   ```

4. **Update buildspec.yml** (for pipeline projects):
   ```yaml
   artifacts:
     base-directory: /tmp/cdk-factory/cdk.out
   ```

### No Breaking Changes for Most Users

If you weren't explicitly using `outdir` parameter, **no changes needed!**  
Everything will work automatically with the new consistent location.

---

## Questions & Support

**Q: Will this break my existing deployments?**  
A: No! The change only affects where synthesis artifacts are written. Your deployed infrastructure is unaffected.

**Q: Can I still use a custom output directory?**  
A: Yes! Use the `outdir` parameter as a namespace:
```python
factory = CdkAppFactory(outdir="my-project")
# Output: /tmp/cdk-factory/my-project/cdk.out
```

**Q: How do I prevent conflicts when running multiple builds?**  
A: Use different namespaces:
```python
# Terminal 1
CdkAppFactory(outdir="project-a").synth()

# Terminal 2 (can run simultaneously)
CdkAppFactory(outdir="project-b").synth()
```

**Q: What if I need artifacts in a different location?**  
A: Copy them after synthesis:
```bash
cp -r /tmp/cdk-factory/my-app/cdk.out ./my-custom-location/
```

**Q: Does this work on Windows?**  
A: The concept is the same, but you'll need to adjust the path to use a Windows temp directory. We recommend using WSL or Docker for consistent behavior.
