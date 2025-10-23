# Changelog v0.9.11 - Simplified Output Directory Logic

## 🎯 **TL;DR**

**Massively simplified output directory handling.** Removed complex namespace patterns and hardcoded paths. Now uses simple priority: explicit > environment > default.

## ✅ **What Changed**

### **Simplified Priority Order**
```python
# Priority 1: Explicit parameter
CdkAppFactory(outdir="/custom/path/cdk.out")

# Priority 2: Environment variable
CDK_OUTDIR=/custom/path/cdk.out python app.py

# Priority 3: Default
CdkAppFactory()  # → {runtime_directory}/cdk.out
```

### **Removed Complexity**
- ❌ Removed namespace pattern (`outdir="my-app"` → `/tmp/cdk-factory/my-app/cdk.out`)
- ❌ Removed hardcoded `/tmp/cdk-factory` default
- ❌ Removed confusing "is it a path or a namespace?" logic
- ❌ Removed duplicate logging

### **What Stayed**
- ✅ Auto-detection of `runtime_directory` via stack inspection
- ✅ `CDK_OUTDIR` environment variable override
- ✅ Explicit `outdir` parameter support
- ✅ Default: `{runtime_directory}/cdk.out`

## 🔧 **Key Fixes**

### **1. Pipeline Self-Bootstrapping**

**Critical Fix - Pipeline Self-Bootstrapping:**

**The Problem:**
```python
# During local synthesis:
self.workload.output_directory = "/Users/eric/.../devops/cdk-iac/cdk.out"  # ❌ Absolute!

# This absolute path gets baked into BuildSpec
primary_output_directory = "/Users/eric/.../devops/cdk-iac/cdk.out"  # ❌ Won't exist in CodeBuild!
```

**The Solution:**
```python
# pipeline_factory.py
def _get_relative_output_directory(self) -> str:
    """Convert absolute path to relative path from repo root"""
    output_dir = self.workload.output_directory
    cwd = os.getcwd()  # Repository root during synthesis
    return os.path.relpath(output_dir, cwd)

# Use relative path in BuildSpec
cdk_out_directory = self._get_relative_output_directory()  # ✅ Relative!
```

**Why This Works:**
- Local synthesis: Computes relative path from current working directory
- BuildSpec gets: `devops/cdk-iac/cdk.out` (relative!)
- CodeBuild execution: Same relative path works from repo root
- No baked-in absolute paths! ✅

**The key insight:**
```
Local:     /Users/eric/project/devops/cdk-iac/cdk.out
           └─ Relative to cwd: devops/cdk-iac/cdk.out

CodeBuild: /codebuild/output/.../devops/cdk-iac/cdk.out
           └─ Relative to cwd: devops/cdk-iac/cdk.out

BuildSpec uses: devops/cdk-iac/cdk.out ✅ Works in both!
```

## 📝 **Migration Guide**

### **No Changes Needed (Most Users)**
If you weren't using custom `outdir`, everything works the same:
```python
factory = CdkAppFactory()
# Output: {runtime_directory}/cdk.out
```

### **If Using Namespace Pattern**
**Before (v0.9.7-0.9.9):**
```python
factory = CdkAppFactory(outdir="my-app")
# Output: /tmp/cdk-factory/my-app/cdk.out
```

**After (v0.9.10):**
```python
# Use explicit path or environment variable
factory = CdkAppFactory(outdir="/tmp/my-app/cdk.out")
# Or:
CDK_OUTDIR=/tmp/my-app/cdk.out python app.py
```

### **If Using Absolute Path**
Still works the same:
```python
factory = CdkAppFactory(outdir="/custom/path/cdk.out")
# Output: /custom/path/cdk.out
```

## 🧪 **Test Updates**

All tests updated and passing:
- ✅ Default behavior
- ✅ Explicit outdir parameter
- ✅ CDK_OUTDIR environment variable
- ✅ CodeBuild environment
- ✅ Various directory structures
- ✅ Auto-detection scenarios

## 📊 **Before vs After**

### **Before (v0.9.7-0.9.9) - Complex**
```python
if supplied_outdir:
    if os.path.isabs(supplied_outdir):
        self.outdir = supplied_outdir
    else:
        namespace = supplied_outdir.rstrip("/")
        if not namespace or namespace in (".", ".."):
            namespace = "default"
        self.outdir = f"/tmp/cdk-factory/{namespace}/cdk.out"  # Namespace pattern
else:
    self.outdir = str(Path(self.runtime_directory) / "cdk.out")

env_out = os.getenv("CDK_OUTDIR")
if env_out:
    self.outdir = os.path.abspath(env_out)
```

### **After (v0.9.10) - Simple**
```python
if supplied_outdir:
    self.outdir = os.path.abspath(supplied_outdir)
elif os.getenv("CDK_OUTDIR"):
    self.outdir = os.path.abspath(os.getenv("CDK_OUTDIR"))
else:
    self.outdir = str(Path(self.runtime_directory).resolve() / "cdk.out")
```

**Lines of code:** 15 → 6 (60% reduction!)
**Logic branches:** 5 → 3 (40% reduction!)

## ✅ **Benefits**

1. **Simpler Logic** - Clear priority order, easy to understand
2. **No Confusion** - `outdir` is always a path, not sometimes a namespace
3. **Fixes Bootstrap** - Pipeline reads actual output location dynamically
4. **Better Defaults** - Works with standard CDK CLI workflow
5. **Easier Debugging** - Less code paths to trace
6. **Maintainable** - Future developers will thank you

## 📚 **Documentation**

New documentation added:
- `docs/OUTPUT_DIRECTORY_STRATEGY.md` - Complete strategy explanation

## 🎉 **Summary**

We went full circle from:
1. **v0.9.6** - Random temp directories ❌
2. **v0.9.7** - Hardcoded `/tmp/cdk-factory` ❌
3. **v0.9.8-0.9.9** - Complex namespace patterns ❌
4. **v0.9.10** - Simple, consistent, predictable ✅

**The lesson:** Sometimes the simplest solution is the best. Using `{runtime_directory}/cdk.out` works everywhere because it maintains the same relative path structure.

---

## Version Bump

- Version: 0.9.9 → 0.9.10
- All tests passing ✅
- Documentation updated ✅
- Complexity reduced ✅
