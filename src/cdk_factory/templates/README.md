# CDK Factory Templates

This directory contains templates for initializing new cdk-factory projects.

## Available Templates

- **`app.py.template`** - Standard application entry point
- **`cdk.json.template`** - CDK configuration file

## Usage

### Method 1: Using the CLI (Recommended)

```bash
# Install cdk-factory with CLI support
pip install cdk-factory

# Initialize a new project
cdk-factory init devops/cdk-iac --workload-name my-app --environment dev

# This creates:
# - devops/cdk-iac/app.py
# - devops/cdk-iac/cdk.json
# - devops/cdk-iac/config.json (minimal template)
# - devops/cdk-iac/.gitignore
```

### Method 2: Manual Copy

```bash
# Copy templates manually
cp templates/app.py.template your-project/devops/cdk-iac/app.py
cp templates/cdk.json.template your-project/devops/cdk-iac/cdk.json

# Create config.json (see examples/)
```

## Template Variables

The templates use minimal configuration. All settings are driven by:

1. **Environment Variables** - `AWS_ACCOUNT`, `AWS_REGION`, `WORKLOAD_NAME`, etc.
2. **CDK Context** - Pass via `-c` flag: `cdk deploy -c WorkloadName=my-app`
3. **config.json** - Your infrastructure configuration

## Project Structure

After initialization, your project should look like:

```
your-project/
├── devops/
│   └── cdk-iac/
│       ├── app.py           # Entry point (from template)
│       ├── cdk.json         # CDK config (from template)
│       ├── config.json      # Your infrastructure config
│       ├── .gitignore       # Generated
│       └── commands/        # Your build scripts (optional)
│           ├── docker-build.sh
│           └── docker-build.py
├── src/                     # Your application code
└── Dockerfile               # Your docker config
```

## Customization

The templates are intentionally minimal. You can:

1. ✅ Add custom environment variables
2. ✅ Modify config.json structure
3. ✅ Add project-specific initialization in app.py
4. ❌ Don't modify core path resolution logic (it's environment-agnostic)

## Integration with pyproject.toml

To enable the CLI, update `pyproject.toml`:

```toml
[project.scripts]
cdk-factory = "cdk_factory.cli:main"
```

Or in `setup.py`:

```python
entry_points={
    'console_scripts': [
        'cdk-factory=cdk_factory.cli:main',
    ],
}
```

## Benefits

✅ **No boilerplate** - Standard entry point across all projects  
✅ **Environment-agnostic** - Works locally and in CI/CD  
✅ **Consistent** - All projects follow same pattern  
✅ **Maintainable** - Updates to template benefit all projects  
✅ **Simple** - Just 30 lines of code in app.py
