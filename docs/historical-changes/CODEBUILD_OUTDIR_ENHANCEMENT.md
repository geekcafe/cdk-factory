# CodeBuild outdir Enhancement

## Status: ✅ IMPLEMENTED

**Changes made:**
- ✅ Added `_detect_project_root()` method to `CdkAppFactory`
- ✅ Updated `__init__` with `auto_detect_project_root` parameter
- ✅ Smart detection works WITHOUT `.git` (CodeBuild zip scenario)
- ✅ Uses multiple project markers (pyproject.toml, package.json, .gitignore, README.md, etc.)
- ✅ Updated template in `templates/app.py.template`
- ✅ Created comprehensive test suite

**Result:** Projects no longer need boilerplate code to handle `cdk.out` location!

## Problem

Every project needs boilerplate code to handle `cdk.out` location for CodeBuild:

```python
# Current: Required in every app.py
if os.getenv('CODEBUILD_SRC_DIR'):
    project_root = os.getenv('CODEBUILD_SRC_DIR')
else:
    project_root = str(Path(runtime_dir).parent.parent.resolve())

outdir = os.getenv('CDK_OUT_DIR') or os.path.join(project_root, 'cdk.out')

factory = CdkAppFactory(
    config_path=config_path,
    outdir=outdir,  # Must be explicit
    runtime_directory=runtime_dir
)
```

**Issues:**
- Repeated in every project
- Easy to forget or get wrong
- Not intuitive that CodeBuild needs outdir at project root

## Solution

Add automatic detection to `CdkAppFactory`:

### Option 1: Auto-detect in Constructor (Recommended)

```python
class CdkAppFactory:
    def __init__(
        self,
        config_path: str = None,
        outdir: str = None,
        runtime_directory: str = None,
        auto_detect_project_root: bool = True  # NEW
    ):
        self.runtime_directory = runtime_directory or os.getcwd()
        
        # NEW: Automatically detect project root for CodeBuild
        if auto_detect_project_root and outdir is None:
            project_root = self._detect_project_root()
            self.outdir = os.path.join(project_root, 'cdk.out')
        else:
            self.outdir = outdir
        
        # ... rest of init
    
    def _detect_project_root(self) -> str:
        """
        Detect project root directory
        
        Priority:
        1. CODEBUILD_SRC_DIR (in CodeBuild)
        2. Derive from runtime_directory (go up to find .git)
        3. runtime_directory itself (fallback)
        """
        # CodeBuild
        if os.getenv('CODEBUILD_SRC_DIR'):
            return os.getenv('CODEBUILD_SRC_DIR')
        
        # Local: Find project root by looking for .git
        current = Path(self.runtime_directory)
        for parent in [current] + list(current.parents):
            if (parent / '.git').exists():
                return str(parent)
        
        # Fallback: assume runtime_directory is in devops/cdk-iac
        # and project root is 2 levels up
        return str(Path(self.runtime_directory).parent.parent.resolve())
```

### Option 2: Smart Default Parameter

```python
class CdkAppFactory:
    def __init__(
        self,
        config_path: str = None,
        outdir: str | Literal['auto'] = 'auto',  # NEW: default to 'auto'
        runtime_directory: str = None
    ):
        self.runtime_directory = runtime_directory or os.getcwd()
        
        # NEW: Handle 'auto' outdir
        if outdir == 'auto':
            project_root = self._detect_project_root()
            self.outdir = os.path.join(project_root, 'cdk.out')
        elif outdir is None:
            self.outdir = None  # Let CDK use default
        else:
            self.outdir = outdir
```

## After Enhancement

Projects can use the minimal version:

```python
if __name__ == "__main__":
    runtime_dir = str(Path(__file__).parent.resolve())
    config_path = os.getenv('CDK_CONFIG_PATH', 'config.json')
    
    # That's it! No outdir calculation needed
    factory = CdkAppFactory(
        config_path=config_path,
        runtime_directory=runtime_dir
        # outdir is automatically set to project_root/cdk.out
    )
    
    factory.synth(cdk_app_file=__file__)
```

**Or explicitly disable if needed:**
```python
factory = CdkAppFactory(
    config_path=config_path,
    runtime_directory=runtime_dir,
    auto_detect_project_root=False  # Use CDK default behavior
)
```

## Implementation Steps (✅ COMPLETED)

### 1. Add Helper Method to CdkAppFactory ✅

```python
# In cdk_factory/app.py

def _detect_project_root(self) -> str:
    """
    Detect project root directory for proper cdk.out placement
    
    Priority:
    1. CODEBUILD_SRC_DIR (CodeBuild environment)
    2. Find project markers (pyproject.toml, package.json, .gitignore, README.md, etc.)
       NOTE: CodeBuild often gets zip without .git, so we check multiple markers
    3. Assume devops/cdk-iac structure (go up 2 levels)
    4. Fallback to runtime_directory
    
    Returns:
        str: Absolute path to project root
    """
    # Priority 1: CodeBuild environment (most reliable)
    codebuild_src = os.getenv('CODEBUILD_SRC_DIR')
    if codebuild_src:
        return codebuild_src
    
    # Priority 2: Look for project root markers
    # CodeBuild often gets zip without .git, so check multiple markers
    current = Path(self.runtime_directory).resolve()
    
    # Walk up the directory tree looking for root markers
    for parent in [current] + list(current.parents):
        # Check for common project root indicators
        root_markers = [
            '.git',           # Git repo (local dev)
            'pyproject.toml', # Python project root
            'package.json',   # Node project root
            'Cargo.toml',     # Rust project root
            '.gitignore',     # Often at root
            'README.md',      # Often at root
            'requirements.txt', # Python dependencies
        ]
        
        # If we find multiple markers (2+) at this level, it's likely the root
        markers_found = sum(1 for marker in root_markers if (parent / marker).exists())
        if markers_found >= 2 and parent != current:
            return str(parent)
    
    # Priority 3: Assume devops/cdk-iac structure
    parts = current.parts
    if len(parts) >= 2 and parts[-2:] == ('devops', 'cdk-iac'):
        return str(current.parent.parent)
    
    # Also try just 'cdk-iac' or 'devops'
    if len(parts) >= 1 and parts[-1] in ('cdk-iac', 'devops', 'infrastructure', 'iac'):
        potential_root = current.parent
        while potential_root.name in ('devops', 'cdk-iac', 'infrastructure', 'iac'):
            potential_root = potential_root.parent
        return str(potential_root)
    
    # Fallback: use runtime_directory
    return str(current)
```

### 2. Update __init__ Method ✅

```python
def __init__(
    self,
    args: CommandlineArgs | None = None,
    runtime_directory: str | None = None,
    config_path: str | None = None,
    outdir: str | None = None,
    add_env_context: bool = True,
    auto_detect_project_root: bool = True,  # NEW
) -> None:
    self.args = args or CommandlineArgs()
    self.runtime_directory = runtime_directory or str(Path(__file__).parent)
    self.config_path: str | None = config_path
    self.add_env_context = add_env_context
    
    # Auto-detect outdir for CodeBuild compatibility
    if outdir is None and self.args.outdir is None and auto_detect_project_root:
        project_root = self._detect_project_root()
        self.outdir = os.path.join(project_root, 'cdk.out')
        
        # Log for visibility
        if os.getenv('CODEBUILD_SRC_DIR'):
            print(f"📦 CodeBuild detected: cdk.out at {self.outdir}")
    else:
        self.outdir = outdir or self.args.outdir
    
    self.app: aws_cdk.App = aws_cdk.App(outdir=self.outdir)
```

### 3. Update Template ✅

Updated `templates/app.py.template`:

```python
#!/usr/bin/env python3
"""
CDK Factory Application Entry Point
"""

import os
from pathlib import Path
from cdk_factory.app import CdkAppFactory


if __name__ == "__main__":
    # Runtime directory (where this file lives)
    runtime_dir = str(Path(__file__).parent.resolve())
    
    # Configuration
    config_path = os.getenv('CDK_CONFIG_PATH', 'config.json')
    
    # Create and synth
    # outdir is automatically set to project_root/cdk.out
    factory = CdkAppFactory(
        config_path=config_path,
        runtime_directory=runtime_dir
    )
    
    factory.synth(cdk_app_file=__file__)
```

## Benefits

✅ **No boilerplate** - Projects don't need to calculate project_root  
✅ **Automatic CodeBuild support** - Works in CI/CD without changes  
✅ **Smart defaults** - Finds .git to determine project root  
✅ **Backward compatible** - Explicit outdir still works  
✅ **Opt-out available** - Set `auto_detect_project_root=False`  
✅ **Better logging** - Shows where cdk.out will be created  
✅ **Consistent behavior** - All projects benefit automatically

## Testing

```python
# Test 1: CodeBuild environment
os.environ['CODEBUILD_SRC_DIR'] = '/codebuild/src'
factory = CdkAppFactory(runtime_directory='/codebuild/src/devops/cdk-iac')
assert factory.outdir == '/codebuild/src/cdk.out'

# Test 2: Local with .git
factory = CdkAppFactory(runtime_directory='/home/user/project/devops/cdk-iac')
assert factory.outdir == '/home/user/project/cdk.out'

# Test 3: Explicit outdir (override)
factory = CdkAppFactory(
    runtime_directory='/path',
    outdir='/custom/path/cdk.out'
)
assert factory.outdir == '/custom/path/cdk.out'

# Test 4: Disable auto-detect
factory = CdkAppFactory(
    runtime_directory='/path',
    auto_detect_project_root=False
)
assert factory.outdir is None  # CDK default behavior
```

## Migration Path

1. ✅ Add `_detect_project_root()` method to CdkAppFactory
2. ✅ Update `__init__` with `auto_detect_project_root` parameter
3. ✅ Update template in `templates/app.py.template`
4. ✅ Add tests
5. ✅ Update documentation
6. ✅ Bump version (0.9.0)
7. ✅ Publish to PyPI
8. ✅ Update existing projects to simplified version

### Existing Projects

**Before (current boilerplate):**
```python
if os.getenv('CODEBUILD_SRC_DIR'):
    project_root = os.getenv('CODEBUILD_SRC_DIR')
else:
    project_root = str(Path(runtime_dir).parent.parent.resolve())
outdir = os.getenv('CDK_OUT_DIR') or os.path.join(project_root, 'cdk.out')

factory = CdkAppFactory(config_path=config_path, outdir=outdir, runtime_directory=runtime_dir)
```

**After (with enhanced cdk-factory):**
```python
factory = CdkAppFactory(config_path=config_path, runtime_directory=runtime_dir)
```

Just delete the boilerplate! 🎯
