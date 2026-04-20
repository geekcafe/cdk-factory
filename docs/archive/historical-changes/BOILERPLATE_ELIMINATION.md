# Eliminating Boilerplate in cdk-factory Projects

## Problem

Every project using cdk-factory currently needs to copy the same boilerplate code:

**Before (51 lines):**
```python
class CdkFactoryBootstrap:
    def __init__(self):
        pass
    
    def synth(self):
        path = str(Path(__file__).parent)
        outdir = "./devops/cdk-iac/cdk.out"  # Hardcoded!
        factory = CdkAppFactory(config_path=None, outdir=outdir, runtime_directory=path)
        cdk_app_file = "./app.py"  # Hardcoded!
        
        # Validation logic...
        if not os.path.exists(full_path):
            raise FileNotFoundError(...)
        
        return factory.synth(paths=[path], cdk_app_file=cdk_app_file)

def main():
    app = CdkFactoryBootstrap()
    app.synth()

if __name__ == "__main__":
    main()
```

**Issues:**
- ❌ Unnecessary wrapper class
- ❌ Hardcoded paths
- ❌ 51 lines of boilerplate copied to every project
- ❌ Inconsistent across projects
- ❌ Updates don't propagate to existing projects

## Solution 1: Simplified app.py (Immediate)

**After (30 lines):**
```python
#!/usr/bin/env python3
import os
from pathlib import Path
from cdk_factory.app import CdkAppFactory

if __name__ == "__main__":
    runtime_dir = str(Path(__file__).parent.resolve())
    config_path = os.getenv('CDK_CONFIG_PATH', 'config.json')
    outdir = os.getenv('CDK_OUT_DIR')
    
    factory = CdkAppFactory(
        config_path=config_path,
        outdir=outdir,
        runtime_directory=runtime_dir
    )
    
    factory.synth(cdk_app_file=__file__)
```

**Benefits:**
- ✅ 42% less code (30 lines vs 51)
- ✅ No unnecessary abstraction
- ✅ Environment-driven configuration
- ✅ Clear and readable

## Solution 2: CLI Tool (Recommended)

Add a `cdk-factory` CLI command to initialize projects:

```bash
# Install
pip install cdk-factory

# Initialize new project
cdk-factory init devops/cdk-iac --workload-name my-app --environment dev
```

**What it creates:**
- ✅ `app.py` from template
- ✅ `cdk.json` from template
- ✅ `config.json` (minimal)
- ✅ `.gitignore`

**Implementation:**
1. Add `src/cdk_factory/cli.py` (created)
2. Add `templates/` directory with templates (created)
3. Update `pyproject.toml`:

```toml
[project.scripts]
cdk-factory = "cdk_factory.cli:main"
```

## Solution 3: Template in Package (Alternative)

Include templates in the package and provide utility to copy them:

```python
from cdk_factory.templates import init_project

init_project(
    target_dir="devops/cdk-iac",
    workload_name="my-app",
    environment="dev"
)
```

## Integration Steps

### For cdk-factory Library

1. **Add templates directory:**
   ```
   src/cdk_factory/
   ├── templates/
   │   ├── app.py.template
   │   ├── cdk.json.template
   │   └── README.md
   └── cli.py
   ```

2. **Update pyproject.toml:**
   ```toml
   [project.scripts]
   cdk-factory = "cdk_factory.cli:main"
   
   [tool.setuptools.package-data]
   cdk_factory = ["templates/*"]
   ```

3. **Test the CLI:**
   ```bash
   pip install -e .
   cdk-factory init test-project
   ```

4. **Document in README:**
   ```markdown
   ## Quick Start
   
   Initialize a new project:
   ```bash
   cdk-factory init devops/cdk-iac
   ```
   
   This creates a standard project structure with all necessary files.
   ```

### For Existing Projects

**Migration path:**

1. Replace existing `app.py` with simplified version (30 lines)
2. Or use `cdk-factory init` to regenerate files
3. Update any custom logic if needed

**Before migrating:**
```bash
# Backup current app.py
cp devops/cdk-iac/app.py devops/cdk-iac/app.py.backup

# Copy new template
cp templates/app.py.template devops/cdk-iac/app.py

# Test
cd devops/cdk-iac
cdk synth
```

## Benefits Summary

| Aspect | Before | After |
|--------|--------|-------|
| Lines of code | 51 | 30 |
| Hardcoded paths | Yes | No |
| Wrapper class | Yes | No |
| Initialization time | Manual copy | `cdk-factory init` |
| Consistency | Varies by project | Standard template |
| Maintainability | Must update each project | Update template once |
| Environment support | Limited | Full (local + CI/CD) |

## Rollout Plan

### Phase 1: Create Templates (DONE ✅)
- [x] Create `templates/app.py.template`
- [x] Create `templates/cdk.json.template`
- [x] Create `templates/README.md`

### Phase 2: Add CLI (DONE ✅)
- [x] Create `src/cdk_factory/cli.py`
- [x] Add init command
- [x] Add list-templates command

### Phase 3: Package Updates (TODO)
- [ ] Update `pyproject.toml` with CLI entry point
- [ ] Add templates to package data
- [ ] Test CLI installation

### Phase 4: Documentation (TODO)
- [ ] Update main README with CLI usage
- [ ] Add migration guide for existing projects
- [ ] Add examples

### Phase 5: Publish (TODO)
- [ ] Bump version (e.g., 0.9.0)
- [ ] Publish to PyPI
- [ ] Announce to users

## Example Usage

### New Project
```bash
# Initialize
cdk-factory init my-app/devops/cdk-iac \\
  --workload-name my-app \\
  --environment dev

cd my-app/devops/cdk-iac

# Edit config.json with your infrastructure

# Deploy
cdk synth
cdk deploy
```

### Existing Project
```bash
# Backup current files
cp app.py app.py.backup

# Reinitialize with template
cdk-factory init . --workload-name my-app

# Compare and merge any custom logic
diff app.py.backup app.py

# Test
cdk synth
```

## Compatibility

- ✅ Backward compatible - existing projects continue to work
- ✅ Python 3.8+
- ✅ All existing config.json formats supported
- ✅ No breaking changes to CdkAppFactory API

## Questions?

- **Q: What about custom initialization logic?**
  - A: Add it in `app.py` after the standard initialization

- **Q: Can I still use custom directory structures?**
  - A: Yes, just pass the directory to `cdk-factory init`

- **Q: Will this break existing projects?**
  - A: No, it's opt-in. Existing projects continue to work.
