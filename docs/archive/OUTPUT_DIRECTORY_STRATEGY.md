# CDK Output Directory Strategy

## 📋 **Simple & Clear Priority Order**

The output directory logic follows a straightforward priority hierarchy:

```
1. Explicit `outdir` parameter     (highest priority)
2. CDK_OUTDIR environment variable
3. Default: {runtime_directory}/cdk.out
```

## 🎯 **Why This Works**

### **Local Development**
```python
# app.py in /Users/eric/project/devops/cdk-iac/
factory = CdkAppFactory()
# Output: /Users/eric/project/devops/cdk-iac/cdk.out
# CDK CLI can find it automatically via cdk.json
```

### **CodeBuild Pipeline**
```python
# app.py in /codebuild/output/src123/src/devops/cdk-iac/
factory = CdkAppFactory()
# Output: /codebuild/output/src123/src/devops/cdk-iac/cdk.out
# BuildSpec collects from relative path: devops/cdk-iac/cdk.out
```

### **Both Resolve to Same Relative Path!**
```
Local:     {project}/devops/cdk-iac/cdk.out
CodeBuild: {project}/devops/cdk-iac/cdk.out
                      ^^^^^^^^^^^^^^^^^^^^^^^^ Same relative location!
```

## 🔧 **Usage Examples**

### Default (Most Common)
```python
factory = CdkAppFactory()
# Uses: {runtime_directory}/cdk.out
```

### Custom Location
```python
factory = CdkAppFactory(outdir="/tmp/my-build/cdk.out")
# Uses: /tmp/my-build/cdk.out (absolute path)
```

### Environment Override
```bash
export CDK_OUTDIR="/custom/path/cdk.out"
python app.py
# Uses: /custom/path/cdk.out
```

## 🚫 **What We Removed**

### ❌ Complex Namespace Pattern
```python
# OLD (v0.9.7-0.9.9):
CdkAppFactory(outdir="my-app")
# → /tmp/cdk-factory/my-app/cdk.out
# Problem: Added complexity without solving bootstrap issue
```

### ❌ Hardcoded /tmp/cdk-factory Default
```python
# OLD:
self.outdir = "/tmp/cdk-factory/cdk.out"
# Problem: Doesn't work with standard CDK CLI workflow
```

## ✅ **What We Kept**

### ✅ Auto-Detection
```python
# No need to pass runtime_directory - auto-detected via stack inspection
factory = CdkAppFactory()
```

### ✅ Environment Override
```python
# Power users can override via environment variable
CDK_OUTDIR=/custom/path python app.py
```

### ✅ Explicit Override
```python
# Or pass explicitly for full control
factory = CdkAppFactory(outdir="/custom/path/cdk.out")
```

## 📦 **Pipeline Self-Bootstrapping**

The key insight for pipeline self-deployment:

```python
# pipeline_factory.py

def _get_relative_output_directory(self) -> str:
    """Convert absolute output path to relative path from repo root"""
    output_dir = self.workload.output_directory  # Absolute path
    cwd = os.getcwd()  # Repository root during synthesis
    return os.path.relpath(output_dir, cwd)  # Relative path!

# In _get_synth_shell_step:
cdk_out_directory = self._get_relative_output_directory()  # ✅ Relative!

# NOT:
cdk_out_directory = "/tmp/cdk-factory/cdk.out"  # ❌ Hardcoded!
cdk_out_directory = self.workload.output_directory  # ❌ Absolute path gets baked in!
```

**Why this matters:**

1. **Local Deploy (Bootstrap)**
   - Synthesizes to: `/Users/eric/project/devops/cdk-iac/cdk.out` (absolute)
   - Converts to: `devops/cdk-iac/cdk.out` (relative to cwd)
   - BuildSpec gets: `devops/cdk-iac/cdk.out` ✅

2. **CodeBuild Execution**
   - Starts in: `/codebuild/output/.../src` (repo root)
   - Synthesizes to: `/codebuild/output/.../src/devops/cdk-iac/cdk.out`
   - BuildSpec uses: `devops/cdk-iac/cdk.out` (same relative path!) ✅

3. **No Hardcoded Paths = No Bootstrap Problems!**

**The Critical Conversion:**
```
Absolute path → Relative path → Works everywhere!

Local:     /Users/eric/project/devops/cdk-iac/cdk.out
           ↓ os.path.relpath(output, os.getcwd())
           devops/cdk-iac/cdk.out ← Baked into BuildSpec

CodeBuild: /codebuild/output/.../devops/cdk-iac/cdk.out
           ↓ BuildSpec expects relative path
           devops/cdk-iac/cdk.out ← Same path works! ✅
```

## 🧪 **Test Coverage**

All scenarios tested:
- ✅ Default behavior (runtime_directory/cdk.out)
- ✅ Explicit outdir parameter
- ✅ CDK_OUTDIR environment variable
- ✅ CodeBuild environment (CODEBUILD_SRC_DIR)
- ✅ Various directory structures
- ✅ Auto-detection with and without project markers

## 📝 **Code Example**

```python
# src/cdk_factory/app.py

# Auto-detect runtime_directory if not provided
if not self.runtime_directory:
    self.runtime_directory = FileOperations.caller_app_dir()

# Clear priority order
if supplied_outdir:
    self.outdir = os.path.abspath(supplied_outdir)
elif os.getenv("CDK_OUTDIR"):
    self.outdir = os.path.abspath(os.getenv("CDK_OUTDIR"))
else:
    self.outdir = str(Path(self.runtime_directory).resolve() / "cdk.out")
```

## 🎯 **Summary**

**Simple Rule:** Output goes to `{runtime_directory}/cdk.out` unless you explicitly override it.

**Why It Works:**
- ✅ Consistent relative path in all environments
- ✅ Works with standard CDK CLI workflow
- ✅ Solves pipeline self-bootstrapping
- ✅ Simple to understand and debug
- ✅ Clear override mechanism for special cases

**No More:**
- ❌ Complex namespace patterns
- ❌ Hardcoded temporary directories
- ❌ Baked-in local paths in pipeline
- ❌ Four different ways to set output directory
