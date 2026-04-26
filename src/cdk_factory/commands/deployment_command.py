"""
CdkDeploymentCommand — generic base class for local / CI deployment scripts.

Projects subclass this, define their ``environments`` and ``required_vars``,
and get env-file loading, env-var propagation, validation, and CDK
synth/deploy/diff for free.

Usage::

    from cdk_factory.commands.deployment_command import CdkDeploymentCommand, EnvironmentConfig

    class MyDeployment(CdkDeploymentCommand):
        @property
        def environments(self):
            return {
                'prod': EnvironmentConfig('prod', '.env.deploy.prod', 'main'),
                'dev':  EnvironmentConfig('dev',  '.env.deploy.dev',  'develop'),
            }

        @property
        def required_vars(self):
            return [
                ('AWS_ACCOUNT', 'AWS Account ID'),
                ('ECR_REPOSITORY_NAME', 'ECR Repository Name'),
            ]

    if __name__ == '__main__':
        MyDeployment.main()
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import boto3
from botocore.exceptions import ClientError, ProfileNotFound

from cdk_factory.utilities.route53_delegation import Route53Delegation


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class EnvironmentConfig:
    """Describes one deployment environment (e.g., dev, uat, prod)."""

    name: str
    env_file: str
    git_branch: str
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class StackInfo:
    """Represents a discovered CloudFormation stack."""

    name: str
    status: str
    stage: str


@dataclass
class DeletionResult:
    """Result of a single stack deletion attempt."""

    stack_name: str
    stage: str
    status: str  # DELETE_COMPLETE, DELETE_FAILED, TIMEOUT, SKIPPED
    error_reason: Optional[str] = None


@dataclass
class DnsCleanupResult:
    """Result of DNS delegation cleanup."""

    attempted: bool
    success: bool
    zone_name: str
    message: str


@dataclass
class RetainedResource:
    """A resource that survived stack deletion."""

    resource_type: str
    name: str


@dataclass
class CleanupResult:
    """Result of a single resource cleanup attempt."""

    resource_type: str
    resource_name: str
    status: str  # "DELETED", "FAILED", "SKIPPED", "UNSUPPORTED"
    error_reason: Optional[str] = None


# ---------------------------------------------------------------------------
# Base command
# ---------------------------------------------------------------------------


class CdkDeploymentCommand:
    """
    Generic base class for CDK deployment commands.

    Provides built-in deployment file auto-discovery from a ``deployments/``
    directory and multi-pass ``{{PLACEHOLDER}}`` resolution. Subclasses can
    override :py:attr:`environments` for custom behavior, or rely on the
    built-in auto-discovery.
    """

    DEPLOYMENTS_DIR = "deployments"

    STANDARD_ENV_VARS: list = [
        ("aws_account", "AWS_ACCOUNT"),
        ("aws_region", "AWS_REGION"),
        ("aws_profile", "AWS_PROFILE"),
        ("git_branch", "GIT_BRANCH"),
        ("workload_name", "WORKLOAD_NAME"),
        ("tenant_name", "TENANT_NAME"),
    ]

    STAGE_KEYWORDS: dict = {
        "network": ["api-gateway", "cloudfront"],
        "compute": ["lambda", "docker"],
        "queues": ["sqs"],
        "persistent-resources": ["dynamodb", "s3-", "cognito", "route53"],
    }

    DELETION_ORDER: list = [
        "unknown",
        "network",
        "compute",
        "queues",
        "persistent-resources",
    ]

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    def __init__(self, script_dir: Optional[Path] = None):
        """
        Args:
            script_dir: Directory that contains the deploy script and ``.env``
                files.  Defaults to the current working directory.
        """
        self.script_dir: Path = script_dir or Path.cwd()
        self._deployment_configs: Dict[str, dict] = {}
        self._deploy_config: Dict[str, Any] = {}
        self._auto_discover_deployments()
        self._load_deploy_config()

    # ------------------------------------------------------------------
    # Deployment auto-discovery
    # ------------------------------------------------------------------

    def _auto_discover_deployments(self) -> None:
        """Scan deployments/ for deployment.*.json files.

        After loading each JSON file, resolves ``{{PLACEHOLDER}}`` references
        using the ``parameters`` block so that fields like ``name`` and
        ``description`` are usable for the interactive menu.
        """
        deployments_path = self.script_dir / self.DEPLOYMENTS_DIR
        if not deployments_path.exists():
            return  # No deployments dir — subclass must provide environments

        for f in sorted(deployments_path.glob("deployment.*.json")):
            with open(f, "r", encoding="utf-8") as fh:
                config = json.load(fh)
            config["_file"] = str(f)

            # Resolve {{PLACEHOLDER}} references from the parameters block
            config = self._resolve_deployment_placeholders(config)

            name = config.get("name", f.stem)
            self._deployment_configs[name] = config

    @staticmethod
    def _resolve_deployment_placeholders(config: dict) -> dict:
        """Resolve ``{{KEY}}`` placeholders in a deployment config dict.

        Uses the ``parameters`` block as the value source. Runs multiple
        passes to handle chained references (e.g. ``{{HOSTED_ZONE_NAME}}``
        which itself contains ``{{TENANT_NAME}}``).
        """
        params = config.get("parameters", {})
        if not params:
            return config

        placeholder_re = re.compile(r"\{\{([A-Za-z_][A-Za-z0-9_]*)\}\}")

        def _replace(text: str, values: dict) -> str:
            return placeholder_re.sub(
                lambda m: str(values.get(m.group(1), m.group(0))), text
            )

        # Resolve parameters themselves first (chained refs)
        for _ in range(5):
            changed = False
            for key, value in params.items():
                if isinstance(value, str) and "{{" in value:
                    resolved = _replace(value, params)
                    if resolved != value:
                        params[key] = resolved
                        changed = True
            if not changed:
                break

        # Now resolve the entire config dict using resolved parameters
        def _resolve_value(value):
            if isinstance(value, str) and "{{" in value:
                return _replace(value, params)
            if isinstance(value, dict):
                return {k: _resolve_value(v) for k, v in value.items()}
            if isinstance(value, list):
                return [_resolve_value(v) for v in value]
            return value

        return _resolve_value(config)

    # ------------------------------------------------------------------
    # Configuration loading
    # ------------------------------------------------------------------

    def _load_deploy_config(self) -> None:
        """Load optional deploy.config.json for project-specific overrides."""
        config_path = self.script_dir / "deploy.config.json"
        if config_path.exists():
            with open(config_path, "r", encoding="utf-8") as fh:
                self._deploy_config = json.load(fh)
            # Apply stage_keywords override if present
            if self._deploy_config.get("stage_keywords"):
                self.STAGE_KEYWORDS = self._deploy_config["stage_keywords"]

    def _is_json_mode(self, env_config: EnvironmentConfig) -> bool:
        """Return True if this environment uses JSON-based parameter loading."""
        return bool(env_config.extra.get("parameters"))

    # ------------------------------------------------------------------
    # Subclass contract
    # ------------------------------------------------------------------

    @property
    def environments(self) -> Dict[str, EnvironmentConfig]:
        """Return a mapping of environment name → :class:`EnvironmentConfig`.

        Default implementation uses auto-discovered deployment configs.
        Subclasses may override for custom behavior.
        """
        if not self._deployment_configs:
            self._print(
                "No deployment.*.json files found in the deployments/ directory.",
                "red",
            )
            self._print(
                f"  Looked in: {self.script_dir / self.DEPLOYMENTS_DIR}",
                "white",
            )
            self._print("", "white")
            self._print(
                "  Create a deployments/deployment.<env>.json file, or subclass",
                "white",
            )
            self._print(
                "  CdkDeploymentCommand and override the `environments` property.",
                "white",
            )
            sys.exit(1)

        envs: Dict[str, EnvironmentConfig] = {}
        for name, config in self._deployment_configs.items():
            env_file = config.get("_file", "")
            git_branch = config.get(
                "git_branch", config.get("parameters", {}).get("GIT_BRANCH", "main")
            )
            envs[name] = EnvironmentConfig(
                name=name,
                env_file=env_file,
                git_branch=git_branch,
                extra=config,
            )
        return envs

    @property
    def required_vars(self) -> List[Tuple[str, str]]:
        """Return a list of ``(VAR_NAME, description)`` tuples to validate.

        Priority: deploy.config.json > JSON-mode defaults (8 vars) >
        env-file-mode defaults (4 vars).  Subclasses may override.
        """
        # deploy.config.json overrides take first priority
        if self._deploy_config.get("required_vars"):
            return [tuple(pair) for pair in self._deploy_config["required_vars"]]

        # JSON mode defaults (8 vars)
        if hasattr(self, "_current_env_config") and self._is_json_mode(
            self._current_env_config
        ):
            return [
                ("AWS_ACCOUNT", "AWS Account ID"),
                ("AWS_REGION", "AWS Region"),
                ("WORKLOAD_NAME", "Workload Name"),
                ("ENVIRONMENT", "Environment name"),
                ("TENANT_NAME", "Tenant name. Required for namespaces"),
                ("GIT_BRANCH", "Git branch"),
                ("CODE_REPOSITORY_NAME", "Code repository name"),
                ("CODE_REPOSITORY_ARN", "Code repository ARN"),
            ]

        # Env-file mode defaults (4 vars)
        return [
            ("AWS_ACCOUNT", "AWS Account ID"),
            ("AWS_REGION", "AWS Region"),
            ("AWS_PROFILE", "AWS CLI Profile"),
            ("WORKLOAD_NAME", "Workload Name"),
        ]

    def display_configuration_summary(self, config_file: str) -> None:
        """Print a deployment summary.  Mode-aware: JSON mode shows richer output."""
        self._print("", "white")
        if hasattr(self, "_current_env_config") and self._is_json_mode(
            self._current_env_config
        ):
            self._print("Deployment Configuration", "blue")
            self._print(
                f"  Environment  : {os.environ.get('ENVIRONMENT', 'N/A')}", "white"
            )
            self._print(
                f"  Account      : {os.environ.get('AWS_ACCOUNT', 'N/A')}", "white"
            )
            self._print(
                f"  Region       : {os.environ.get('AWS_REGION', 'N/A')}", "white"
            )
            self._print(
                f"  Profile      : {os.environ.get('AWS_PROFILE', 'N/A')}", "white"
            )
            self._print(
                f"  Workload     : {os.environ.get('WORKLOAD_NAME', 'N/A')}", "white"
            )
            self._print(
                f"  Git Branch   : {os.environ.get('GIT_BRANCH', 'N/A')}", "white"
            )
            self._print(f"  Config File  : {config_file}", "white")
        else:
            self._print("Configuration Summary", "blue")
            self._print(f"  Config file : {config_file}", "white")
            self._print(
                f"  Environment : {os.environ.get('ENVIRONMENT', 'N/A')}", "white"
            )
            self._print(
                f"  AWS Account : {os.environ.get('AWS_ACCOUNT', 'N/A')}", "white"
            )
            self._print(
                f"  AWS Region  : {os.environ.get('AWS_REGION', 'N/A')}", "white"
            )
            self._print(
                f"  Git Branch  : {os.environ.get('GIT_BRANCH', 'N/A')}", "white"
            )
        self._print("", "white")

    # ------------------------------------------------------------------
    # Environment helpers
    # ------------------------------------------------------------------

    def load_env_file(self, env_file: str) -> Dict[str, str]:
        """Load ``KEY=VALUE`` pairs from *env_file* (relative to script_dir).

        In JSON mode, returns an empty dict — env vars come from the
        deployment JSON, not ``.env`` files.
        """
        # JSON mode: env vars come from deployment JSON, not .env files
        if hasattr(self, "_current_env_config") and self._is_json_mode(
            self._current_env_config
        ):
            return {}

        env_path = self.script_dir / env_file
        if not env_path.exists():
            self._print(f"Configuration file '{env_file}' not found!", "red")
            self._print("", "white")
            self._print(f"  1. Copy an example file and edit it:", "white")
            self._print(f"     cp .env.deploy.example {env_file}", "white")
            self._print(f"  2. Run this script again.", "white")
            self._print("Note: .env files should be in .gitignore", "yellow")
            sys.exit(1)

        self._print(f"Loading configuration from {env_file}...", "blue")
        env_vars: Dict[str, str] = {}
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, value = line.partition("=")
                    env_vars[key.strip()] = value.strip().strip("\"'")
        return env_vars

    def set_environment_variables(
        self,
        env_config: EnvironmentConfig,
        env_vars: Dict[str, str],
    ) -> None:
        """Apply environment defaults then override with values from *env_vars*.

        In JSON mode (deployment JSON with parameters block), delegates to
        :meth:`_set_json_environment_variables`.  In env-file mode, applies
        the existing logic: merge env vars, set aliases, expand references.
        """
        # JSON mode: load from deployment JSON parameters
        if self._is_json_mode(env_config):
            self._set_json_environment_variables(env_config)
            return

        # Env-file mode (existing logic)
        # Defaults from the EnvironmentConfig
        os.environ.setdefault("ENVIRONMENT", env_config.name)
        os.environ.setdefault("GIT_BRANCH", env_config.git_branch)

        # Values from the env file take precedence
        for key, value in env_vars.items():
            os.environ[key] = value

        # Common alias mappings (env file values already set above)
        _aliases = {
            "WORKLOAD_NAME": "CDK_WORKLOAD_NAME",
            "AWS_ACCOUNT": "AWS_ACCOUNT_NUMBER",
            "AWS_REGION": "DEVOPS_REGION",
        }
        for src, dst in _aliases.items():
            if src in os.environ and dst not in os.environ:
                os.environ[dst] = os.environ[src]

        # Expand variable references (e.g. VALUE=${OTHER_VAR}-suffix)
        for key in list(os.environ.keys()):
            original = os.environ[key]
            expanded = os.path.expandvars(original)
            if expanded != original:
                os.environ[key] = expanded

    def _set_json_environment_variables(self, env_config: EnvironmentConfig) -> None:
        """Load env vars from deployment JSON config (JSON mode)."""
        config = env_config.extra

        # 1. ENVIRONMENT from deployment name
        os.environ["ENVIRONMENT"] = config.get("name", env_config.name)

        # 2. Parameters block — source of truth
        for key, value in config.get("parameters", {}).items():
            os.environ[key] = str(value)

        # 3. Standard top-level fields
        env_var_mapping = self._deploy_config.get(
            "standard_env_vars", self.STANDARD_ENV_VARS
        )
        for json_key, env_key in env_var_mapping:
            value = config.get(json_key, "")
            if value:
                os.environ[env_key] = str(value)

        # 4. Code repository
        repo = config.get("code_repository", {})
        if repo.get("name"):
            os.environ["CODE_REPOSITORY_NAME"] = str(repo["name"])
        if repo.get("connector_arn"):
            os.environ["CODE_REPOSITORY_ARN"] = str(repo["connector_arn"])

        # 5. Management account
        mgmt = config.get("management", {})
        if mgmt.get("account"):
            os.environ["MANAGEMENT_ACCOUNT"] = str(mgmt["account"])
        if mgmt.get("cross_account_role_arn"):
            os.environ["MANAGEMENT_ACCOUNT_ROLE_ARN"] = str(
                mgmt["cross_account_role_arn"]
            )
        if mgmt.get("hosted_zone_id"):
            os.environ["MGMT_R53_HOSTED_ZONE_ID"] = str(mgmt["hosted_zone_id"])

        # 6. Config.json defaults for unset vars
        config_json_path = self.script_dir / "config.json"
        if config_json_path.exists():
            with open(config_json_path, "r", encoding="utf-8") as fh:
                main_config = json.load(fh)
            for param in main_config.get("cdk", {}).get("parameters", []):
                env_var = param.get("env_var_name", "")
                default_value = param.get("value")
                if env_var and default_value and env_var not in os.environ:
                    os.environ[env_var] = str(default_value)

        # 7. Default DEPLOYMENT_NAMESPACE to TENANT_NAME
        if "DEPLOYMENT_NAMESPACE" not in os.environ:
            os.environ["DEPLOYMENT_NAMESPACE"] = os.environ.get("TENANT_NAME", "")

        # 8. Resolve {{PLACEHOLDER}} references (max 5 passes)
        placeholder_re = re.compile(r"\{\{([A-Za-z_][A-Za-z0-9_]*)\}\}")
        changed = True
        max_passes = 5
        passes = 0
        while changed and passes < max_passes:
            changed = False
            passes += 1
            for key in list(os.environ.keys()):
                value = os.environ[key]
                if "{{" in value:
                    resolved = placeholder_re.sub(
                        lambda m: os.environ.get(m.group(1), m.group(0)), value
                    )
                    if resolved != value:
                        os.environ[key] = resolved
                        changed = True

    def validate_required_variables(self) -> None:
        """Raise SystemExit if any required variable is missing or placeholder."""
        self._print("Validating configuration...", "blue")
        missing = [
            f"  - {name} ({desc})"
            for name, desc in self.required_vars
            if not os.environ.get(name) or os.environ[name].startswith("YOUR_")
        ]
        if missing:
            self._print("Missing required configuration variables:", "red")
            for m in missing:
                print(m)
            self._print("Please update your environment file.", "yellow")
            sys.exit(1)
        self._print("Configuration validated", "green")

        # <TODO> placeholder detection
        todos = [key for key, value in os.environ.items() if value == "<TODO>"]
        if todos:
            self._print("", "white")
            self._print(
                f"Found {len(todos)} unresolved <TODO> placeholder(s) in deployment config:",
                "red",
            )
            for key in sorted(todos):
                self._print(f"  {key} = <TODO>", "yellow")
            self._print("", "white")
            self._print(
                "These values must be set before CDK can synthesize or deploy.",
                "red",
            )
            self._print(
                "Update your deployment JSON: deployments/deployment.*.json",
                "yellow",
            )
            sys.exit(1)

    # ------------------------------------------------------------------
    # CDK operations
    # ------------------------------------------------------------------

    def run_cdk_synth(self, config_file: str) -> None:
        """Run ``python3 app.py --config <config_file>`` in script_dir."""
        self._print("Running CDK synthesis...", "blue")
        self._run(["python3", "app.py", "--config", config_file])
        self._print("CDK synthesis completed successfully", "green")

    def run_cdk_deploy(self, config_file: str) -> None:
        """Synthesise then deploy all stacks."""
        self.run_cdk_synth(config_file)
        self._print("Running CDK deployment...", "blue")
        self._run(
            [
                "cdk",
                "deploy",
                "--all",
                "--require-approval",
                "never",
                "--app",
                f"python3 app.py --config {config_file}",
            ]
        )
        self._print("CDK deployment completed successfully", "green")

    def run_cdk_diff(self, config_file: str) -> None:
        """Synthesise then diff all stacks."""
        self.run_cdk_synth(config_file)
        self._print("Running CDK diff...", "blue")
        self._run(["cdk", "diff", "--all"])
        self._print("CDK diff completed successfully", "green")

    def run_cdk_destroy(self, config_file: str) -> None:
        """Destroy all stacks."""
        self._print("Running CDK destroy...", "red")
        self._run(
            [
                "cdk",
                "destroy",
                "--all",
                "--force",
                "--app",
                f"python3 app.py --config {config_file}",
            ]
        )
        self._print("CDK destroy completed successfully", "green")

    def run_target_destroy(
        self,
        env_config: EnvironmentConfig,
        target_profile: Optional[str] = None,
        confirm_destroy: bool = False,
        skip_dns_cleanup: bool = False,
        no_interactive_failures: bool = False,
        stack_delete_timeout: int = 1800,
    ) -> None:
        """Orchestrate the full target resource destruction flow.

        Steps: profile selection → session creation → stack discovery →
        classification → confirmation → stage-by-stage deletion →
        DNS cleanup → retained resources discovery → summary report.
        """
        # 1. Profile selection
        profile_name = self._select_target_profile(env_config, target_profile)

        # 2. Session creation
        session = self._create_target_session(profile_name)

        # 3. Stack discovery
        stack_prefix = self._build_stack_prefix(env_config)
        stacks = self._discover_target_stacks(session, stack_prefix)

        # 4. No stacks check — still check for retained resources
        if not stacks:
            self._print("", "white")
            self._print(
                f"  No stacks found matching prefix '{stack_prefix}'.",
                "blue",
            )
            self._print("  Checking for retained resources...", "blue")
            retained_resources = self._discover_retained_resources(session, env_config)

            cleanup_results: Optional[List[CleanupResult]] = None
            if retained_resources:
                cleanup_results = self._prompt_cleanup(
                    retained_resources, session, no_interactive_failures
                )
            else:
                self._print(
                    "  No retained resources found — nothing to clean up.", "blue"
                )

            self._print("", "white")
            sys.exit(0)

        # 5. Classification and deletion ordering
        classified = self._classify_stacks_by_stage(stacks, stack_prefix)
        deletion_order = self._get_deletion_order(classified)

        # 6. Confirmation
        tenant_name = os.environ.get("TENANT_NAME", "")
        account = os.environ.get("AWS_ACCOUNT", "")
        self._confirm_destruction(tenant_name, deletion_order, account, confirm_destroy)

        # 7. Stage-by-stage deletion
        all_results: List[DeletionResult] = []
        aborted = False
        for stage_name, stage_stacks in deletion_order:
            self._print(f"  Deleting [{stage_name}] stacks...", "blue")
            results, should_exit = self._delete_stage_stacks(
                session,
                stage_name,
                stage_stacks,
                stack_delete_timeout,
                no_interactive_failures,
            )
            all_results.extend(results)
            if should_exit:
                aborted = True
                break

        # 8. DNS cleanup
        dns_result: Optional[DnsCleanupResult] = None
        if not aborted:
            should_cleanup = self._prompt_dns_cleanup(classified, skip_dns_cleanup)
            if should_cleanup:
                dns_result = self._delete_dns_delegation(
                    env_config, no_interactive_failures
                )
                if (
                    dns_result
                    and not dns_result.success
                    and "aborted" in dns_result.message.lower()
                ):
                    aborted = True

        # 9. Retained resources
        retained_resources: Optional[List[RetainedResource]] = None
        if not aborted:
            self._print("", "white")
            self._print("  Checking for retained resources...", "blue")
            retained_resources = self._discover_retained_resources(session, env_config)

        # 9b. Cleanup retained resources
        cleanup_results: Optional[List[CleanupResult]] = None
        if not aborted and retained_resources:
            cleanup_results = self._prompt_cleanup(
                retained_resources, session, no_interactive_failures
            )

        # 10. Summary report
        exit_code = self._display_summary_report(
            all_results,
            dns_result,
            retained_resources,
            cleanup_results=cleanup_results,
            partial=aborted,
        )
        sys.exit(exit_code)

    # ------------------------------------------------------------------
    # Cross-account target destroy: profile and session
    # ------------------------------------------------------------------

    def _build_stack_prefix(self, env_config: EnvironmentConfig) -> str:
        """Build the CloudFormation stack name prefix for discovery.

        Default: "{WORKLOAD_NAME}-{DEPLOYMENT_NAMESPACE}-"
        Subclasses override for different naming conventions.
        """
        workload_name = os.environ.get("WORKLOAD_NAME", "")
        deployment_namespace = os.environ.get("DEPLOYMENT_NAMESPACE", "")
        return f"{workload_name}-{deployment_namespace}-"

    def _select_target_profile(
        self, env_config: EnvironmentConfig, target_profile: Optional[str] = None
    ) -> str:
        """Interactive profile selection for target account operations.

        Shows the default profile from the deployment config and lets the
        user press Enter to accept or type a different name.
        """
        if target_profile is not None:
            return target_profile

        default_profile = env_config.extra.get("aws_profile", "default")
        response = input(
            f"  AWS profile for target account [{default_profile}]: "
        ).strip()
        return response if response else default_profile

    def _create_target_session(self, profile_name: str) -> boto3.Session:
        """Create a boto3 Session using the selected profile. Validates the profile exists."""
        try:
            session = boto3.Session(profile_name=profile_name)
            return session
        except ProfileNotFound:
            self._print(
                f"AWS profile '{profile_name}' not found. "
                "Please check your ~/.aws/config and ~/.aws/credentials files.",
                "red",
            )
            sys.exit(1)

    # ------------------------------------------------------------------
    # Cross-account target destroy: stack discovery and classification
    # ------------------------------------------------------------------

    def _discover_target_stacks(
        self, session: boto3.Session, stack_prefix: str
    ) -> List[dict]:
        """Discover CloudFormation stacks matching the prefix in the target account."""
        cf = session.client("cloudformation")
        paginator = cf.get_paginator("list_stacks")
        allowed_statuses = [
            "CREATE_COMPLETE",
            "UPDATE_COMPLETE",
            "UPDATE_ROLLBACK_COMPLETE",
            "ROLLBACK_COMPLETE",
            "IMPORT_COMPLETE",
            "IMPORT_ROLLBACK_COMPLETE",
            "DELETE_FAILED",
        ]
        stacks: List[dict] = []
        for page in paginator.paginate(StackStatusFilter=allowed_statuses):
            for s in page["StackSummaries"]:
                if s["StackName"].startswith(stack_prefix):
                    stacks.append(s)
        return stacks

    def _classify_stacks_by_stage(
        self, stacks: List[dict], stack_prefix: str
    ) -> Dict[str, List[dict]]:
        """Classify stacks into stage groups using the pipeline config.

        Reads the pipeline stages from config.json to determine which stacks
        belong to which stage.  Falls back to STAGE_KEYWORDS keyword matching
        if config.json is not available or a stack isn't found in any stage.
        """
        # Try to build stage→stack-name mapping from config.json
        stage_stack_names = self._load_pipeline_stage_map()

        classified: Dict[str, List[dict]] = {}
        for stack in stacks:
            stack_name = stack["StackName"]
            matched_stage = "unknown"

            # First: check pipeline config mapping
            if stage_stack_names:
                for stage_name, names in stage_stack_names.items():
                    if stack_name in names:
                        matched_stage = stage_name
                        break

            # Fallback: keyword matching
            if matched_stage == "unknown":
                suffix = stack_name[len(stack_prefix) :].lower()
                for stage, keywords in self.STAGE_KEYWORDS.items():
                    if any(kw in suffix for kw in keywords):
                        matched_stage = stage
                        break

            classified.setdefault(matched_stage, []).append(stack)
        return classified

    def _load_pipeline_stage_map(self) -> Dict[str, set]:
        """Read config.json pipeline stages and resolve stack names.

        Returns a dict of stage_name → set of resolved CloudFormation stack names.
        Returns empty dict if config.json is not available or has no pipeline stages.
        """
        config_path = self.script_dir / "config.json"
        if not config_path.exists():
            return {}

        try:
            with open(config_path, "r", encoding="utf-8") as fh:
                config = json.load(fh)
        except (json.JSONDecodeError, OSError):
            return {}

        # Find pipeline stages in the workload config
        deployments = config.get("workload", {}).get("deployments", [])
        stages = []
        for deployment in deployments:
            pipeline = deployment.get("pipeline", {})
            if pipeline.get("stages"):
                stages = pipeline["stages"]
                break

        if not stages:
            return {}

        stage_map: Dict[str, set] = {}
        for stage in stages:
            stage_name = stage.get("name", "")
            if not stage_name:
                continue
            stack_names: set = set()
            for stack_ref in stage.get("stacks", []):
                inherits = stack_ref.get("__inherits__", "")
                if inherits:
                    resolved_name = self._resolve_stack_name_from_config(inherits)
                    if resolved_name:
                        stack_names.add(resolved_name)
                elif stack_ref.get("name"):
                    stack_names.add(
                        self._resolve_placeholders_in_name(stack_ref["name"])
                    )
            if stack_names:
                stage_map[stage_name] = stack_names

        return stage_map

    def _resolve_stack_name_from_config(self, config_path: str) -> Optional[str]:
        """Read a stack config file and return the resolved stack name."""
        full_path = self.script_dir / config_path
        if not full_path.exists():
            return None
        try:
            with open(full_path, "r", encoding="utf-8") as fh:
                stack_config = json.load(fh)
            name = stack_config.get("name", "")
            if name:
                return self._resolve_placeholders_in_name(name)
        except (json.JSONDecodeError, OSError):
            pass
        return None

    def _resolve_placeholders_in_name(self, name: str) -> str:
        """Resolve {{PLACEHOLDER}} references in a name using env vars."""
        placeholder_re = re.compile(r"\{\{([A-Za-z_][A-Za-z0-9_]*)\}\}")
        return placeholder_re.sub(
            lambda m: os.environ.get(m.group(1), m.group(0)), name
        )

    def _get_deletion_order(
        self, classified: Dict[str, List[dict]]
    ) -> List[Tuple[str, List[dict]]]:
        """Return stages in reverse dependency order for deletion.

        Uses the pipeline stage order from config.json (reversed) if available.
        Falls back to DELETION_ORDER constant for keyword-classified stacks.
        """
        # Get pipeline stage order from config.json
        pipeline_order = self._get_pipeline_stage_order()

        if pipeline_order:
            # Reverse the pipeline order for deletion
            deletion_order = list(reversed(pipeline_order))
            # Add "unknown" at the front (delete unclassified stacks first)
            if "unknown" not in deletion_order:
                deletion_order.insert(0, "unknown")
        else:
            deletion_order = self.DELETION_ORDER

        ordered: List[Tuple[str, List[dict]]] = []
        for stage in deletion_order:
            if stage in classified:
                ordered.append((stage, classified[stage]))

        # Include any classified stages not in the deletion order
        for stage in classified:
            if stage not in deletion_order:
                ordered.append((stage, classified[stage]))

        return ordered

    def _get_pipeline_stage_order(self) -> List[str]:
        """Read the pipeline stage order from config.json.

        Returns a list of stage names in deployment order, or empty list
        if config.json is not available.
        """
        config_path = self.script_dir / "config.json"
        if not config_path.exists():
            return []

        try:
            with open(config_path, "r", encoding="utf-8") as fh:
                config = json.load(fh)
        except (json.JSONDecodeError, OSError):
            return []

        deployments = config.get("workload", {}).get("deployments", [])
        for deployment in deployments:
            pipeline = deployment.get("pipeline", {})
            stages = pipeline.get("stages", [])
            if stages:
                return [s["name"] for s in stages if s.get("name")]

        return []

    # ------------------------------------------------------------------
    # Cross-account target destroy: deletion execution
    # ------------------------------------------------------------------

    def _delete_single_stack(
        self, cf_client, stack_name: str, timeout: int
    ) -> Tuple[str, Optional[str]]:
        """Delete a single stack, handling DELETE_IN_PROGRESS from previous runs.

        Returns (final_status, error_reason).
        """
        try:
            resp = cf_client.describe_stacks(StackName=stack_name)
            current_status = resp["Stacks"][0]["StackStatus"]
            if current_status == "DELETE_IN_PROGRESS":
                self._print(
                    f"  {stack_name}: already DELETE_IN_PROGRESS, waiting...",
                    "blue",
                )
                return self._wait_for_stack_delete(cf_client, stack_name, timeout)
        except ClientError as e:
            if "does not exist" in str(e):
                return ("DELETE_COMPLETE", None)
            raise

        cf_client.delete_stack(StackName=stack_name)
        return self._wait_for_stack_delete(cf_client, stack_name, timeout)

    def _wait_for_stack_delete(
        self, cf_client, stack_name: str, timeout: int
    ) -> Tuple[str, Optional[str]]:
        """Poll describe_stacks until DELETE_COMPLETE, DELETE_FAILED, or timeout.

        Returns (final_status, error_reason).
        """
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                resp = cf_client.describe_stacks(StackName=stack_name)
                status = resp["Stacks"][0]["StackStatus"]
                if status == "DELETE_COMPLETE":
                    return ("DELETE_COMPLETE", None)
                if status == "DELETE_FAILED":
                    reason = resp["Stacks"][0].get("StackStatusReason", "Unknown")
                    return ("DELETE_FAILED", reason)
                self._print(f"  {stack_name}: {status}...", "white")
            except ClientError as e:
                if "does not exist" in str(e):
                    return ("DELETE_COMPLETE", None)
                raise
            time.sleep(10)
        return ("TIMEOUT", f"Exceeded {timeout}s timeout")

    def _prompt_failure_action(
        self,
        item_name: str,
        status: str,
        error_reason: str,
        no_interactive_failures: bool,
    ) -> str:
        """Present failure options to the user.

        Returns 'retry', 'continue', or 'exit'.
        """
        if no_interactive_failures:
            self._print(
                f"  {item_name}: {status} — {error_reason} (auto-continuing)",
                "yellow",
            )
            return "continue"

        self._print("", "white")
        self._print(f"  Stack deletion failed: {item_name}", "red")
        self._print(f"  Status: {status}", "red")
        self._print(f"  Reason: {error_reason}", "red")
        self._print("", "white")

        options = [
            "Wait/Retry — pause so you can fix the issue, then retry",
            "Continue — skip this and move on",
            "Exit — stop the entire destroy operation",
        ]
        idx = self._interactive_select("How would you like to proceed?", options)
        return ["retry", "continue", "exit"][idx]

    def _delete_stage_stacks(
        self,
        session: boto3.Session,
        stage_name: str,
        stacks: List[dict],
        timeout: int,
        no_interactive_failures: bool,
    ) -> Tuple[List[DeletionResult], bool]:
        """Delete all stacks in a stage group.

        Returns (results, should_exit). should_exit is True if user chose Exit.
        """
        cf_client = session.client("cloudformation")
        results: List[DeletionResult] = []

        for stack in stacks:
            stack_name = stack["StackName"]
            while True:
                status, reason = self._delete_single_stack(
                    cf_client, stack_name, timeout
                )
                if status == "DELETE_COMPLETE":
                    results.append(
                        DeletionResult(
                            stack_name=stack_name,
                            stage=stage_name,
                            status=status,
                            error_reason=None,
                        )
                    )
                    break

                action = self._prompt_failure_action(
                    stack_name, status, reason, no_interactive_failures
                )
                if action == "retry":
                    self._print(
                        f"  Press Enter when ready to retry {stack_name}...",
                        "blue",
                    )
                    if not no_interactive_failures:
                        input()
                    continue
                elif action == "exit":
                    results.append(
                        DeletionResult(
                            stack_name=stack_name,
                            stage=stage_name,
                            status=status,
                            error_reason=reason,
                        )
                    )
                    return (results, True)
                else:  # continue
                    results.append(
                        DeletionResult(
                            stack_name=stack_name,
                            stage=stage_name,
                            status=status,
                            error_reason=reason,
                        )
                    )
                    break

        return (results, False)

    # ------------------------------------------------------------------
    # Cross-account target destroy: confirmation and cleanup
    # ------------------------------------------------------------------

    def _confirm_destruction(
        self,
        tenant_name: str,
        stacks_by_stage: List[Tuple[str, List[dict]]],
        account: str,
        confirm_destroy: bool,
    ) -> bool:
        """Display warning and prompt user to type tenant name to confirm.

        Returns True if confirmed. Exits with code 1 if incorrect or cancelled.
        """
        if confirm_destroy:
            return True

        self._print("", "white")
        self._print("  ⚠  WARNING: This operation is IRREVERSIBLE", "red")
        self._print(
            f"  ⚠  You are about to destroy resources in account {account}",
            "red",
        )
        self._print("", "white")
        self._print("  Stacks to be deleted (in order):", "white")
        self._print("", "white")

        for stage_name, stage_stacks in stacks_by_stage:
            self._print(f"  [{stage_name}]", "blue")
            for stack in stage_stacks:
                self._print(f"    - {stack['StackName']}", "white")
            self._print("", "white")

        user_input = input(
            f'  Type the tenant name "{tenant_name}" to confirm: '
        ).strip()

        if user_input == tenant_name:
            return True

        self._print("", "white")
        self._print("  Confirmation failed — aborting destruction.", "red")
        sys.exit(1)

    def _prompt_dns_cleanup(
        self, classified_stacks: Dict[str, List[dict]], skip_dns_cleanup: bool
    ) -> bool:
        """Prompt user for DNS cleanup confirmation. Returns True if confirmed."""
        if skip_dns_cleanup:
            return False

        # Check if persistent-resources stage has any route53 stacks
        persistent_stacks = classified_stacks.get("persistent-resources", [])
        has_route53 = any(
            "route53" in s["StackName"].lower() for s in persistent_stacks
        )
        if not has_route53:
            return False

        response = input(
            "  Clean up DNS delegation records in management account? [y/N]: "
        ).strip()
        return response.lower() in ("y", "yes")

    def _delete_dns_delegation(
        self, env_config: EnvironmentConfig, no_interactive_failures: bool
    ) -> DnsCleanupResult:
        """Delete NS records from management account's parent zone."""
        zone_name = os.environ.get("HOSTED_ZONE_NAME", "")
        mgmt_role = os.environ.get("MANAGEMENT_ACCOUNT_ROLE_ARN", "")
        mgmt_zone_id = os.environ.get("MGMT_R53_HOSTED_ZONE_ID", "")

        while True:
            try:
                deleted = Route53Delegation().delete_ns_records(
                    hosted_zone_id=mgmt_zone_id,
                    record_name=zone_name,
                    role_arn=mgmt_role,
                )
                if deleted:
                    return DnsCleanupResult(
                        attempted=True,
                        success=True,
                        zone_name=zone_name,
                        message=f"Removed {zone_name} from parent zone",
                    )
                else:
                    self._print(
                        f"  DNS delegation for {zone_name} already cleaned up", "blue"
                    )
                    return DnsCleanupResult(
                        attempted=True,
                        success=True,
                        zone_name=zone_name,
                        message=f"{zone_name} already removed (idempotent)",
                    )
            except Exception as e:
                action = self._prompt_failure_action(
                    f"DNS cleanup ({zone_name})",
                    "FAILED",
                    str(e),
                    no_interactive_failures,
                )
                if action == "retry":
                    self._print(
                        "  Press Enter when ready to retry DNS cleanup...", "blue"
                    )
                    if not no_interactive_failures:
                        input()
                    continue
                elif action == "exit":
                    return DnsCleanupResult(
                        attempted=True,
                        success=False,
                        zone_name=zone_name,
                        message=f"DNS cleanup aborted: {e}",
                    )
                else:  # continue
                    return DnsCleanupResult(
                        attempted=True,
                        success=False,
                        zone_name=zone_name,
                        message=f"DNS cleanup skipped: {e}",
                    )

    def _discover_retained_resources(
        self, session: boto3.Session, env_config: EnvironmentConfig
    ) -> List[RetainedResource]:
        """Check for resources that survived stack deletion."""
        params = env_config.extra.get("parameters", {})
        workload = params.get("WORKLOAD_NAME", "")
        tenant = params.get("TENANT_NAME", "")
        prefix = f"{workload}-{tenant}"
        retained: List[RetainedResource] = []

        # 1. S3 Buckets — known names from config + prefix scan
        known_buckets = [
            v
            for k, v in params.items()
            if k.startswith("S3_") and k.endswith("_BUCKET_NAME")
        ]
        try:
            s3 = session.client("s3")
            resp = s3.list_buckets()
            for bucket in resp.get("Buckets", []):
                name = bucket["Name"]
                if name in known_buckets or name.startswith(prefix):
                    retained.append(
                        RetainedResource(resource_type="S3 Bucket", name=name)
                    )
        except Exception as e:
            self._print(f"  Warning: could not check S3 buckets: {e}", "yellow")

        # 2. DynamoDB Tables — known names from config + prefix scan
        known_tables = [
            v
            for k, v in params.items()
            if k.startswith("DYNAMODB_") and k.endswith("_TABLE_NAME")
        ]
        try:
            dynamodb = session.client("dynamodb")
            paginator = dynamodb.get_paginator("list_tables")
            for page in paginator.paginate():
                for table_name in page.get("TableNames", []):
                    if table_name in known_tables or table_name.startswith(prefix):
                        retained.append(
                            RetainedResource(
                                resource_type="DynamoDB Table", name=table_name
                            )
                        )
        except Exception as e:
            self._print(f"  Warning: could not check DynamoDB tables: {e}", "yellow")

        # 3. Cognito User Pools — prefix scan on pool name
        try:
            cognito = session.client("cognito-idp")
            paginator = cognito.get_paginator("list_user_pools")
            for page in paginator.paginate(MaxResults=60):
                for pool in page.get("UserPools", []):
                    if pool["Name"].startswith(prefix):
                        retained.append(
                            RetainedResource(
                                resource_type="Cognito User Pool", name=pool["Name"]
                            )
                        )
        except Exception as e:
            self._print(f"  Warning: could not check Cognito user pools: {e}", "yellow")

        # 4. Route53 Hosted Zones — check for tenant subdomain zone
        hosted_zone_name = params.get("HOSTED_ZONE_NAME", "")
        if hosted_zone_name:
            try:
                r53 = session.client("route53")
                resp = r53.list_hosted_zones_by_name(
                    DNSName=hosted_zone_name, MaxItems="1"
                )
                for zone in resp.get("HostedZones", []):
                    if zone["Name"].rstrip(".") == hosted_zone_name.rstrip("."):
                        retained.append(
                            RetainedResource(
                                resource_type="Route53 Hosted Zone",
                                name=hosted_zone_name,
                            )
                        )
            except Exception as e:
                self._print(f"  Warning: could not check Route53: {e}", "yellow")

        # 5. ECR Repositories — prefix scan
        try:
            ecr = session.client("ecr")
            paginator = ecr.get_paginator("describe_repositories")
            for page in paginator.paginate():
                for repo in page.get("repositories", []):
                    if repo["repositoryName"].startswith(prefix):
                        retained.append(
                            RetainedResource(
                                resource_type="ECR Repository",
                                name=repo["repositoryName"],
                            )
                        )
        except Exception as e:
            self._print(f"  Warning: could not check ECR repositories: {e}", "yellow")

        return retained

    # ------------------------------------------------------------------
    # Cross-account target destroy: summary report
    # ------------------------------------------------------------------

    def _display_summary_report(
        self,
        results: List[DeletionResult],
        dns_result: Optional[DnsCleanupResult] = None,
        retained_resources: Optional[List[RetainedResource]] = None,
        cleanup_results: Optional[List[CleanupResult]] = None,
        partial: bool = False,
    ) -> int:
        """Print summary table and return exit code."""
        separator = "  " + "─" * 50

        self._print("", "white")

        if partial:
            self._print("  ⚠ Destruction ABORTED by user", "red")
            self._print(separator, "white")
            self._print("  Partial Destruction Summary", "white")
        else:
            self._print("  Destruction Summary", "white")

        self._print(separator, "white")

        # Stack results
        for r in results:
            if r.status == "DELETE_COMPLETE":
                self._print(f"  ✓ {r.stack_name}    {r.status}", "white")
            else:
                reason = f" ({r.error_reason})" if r.error_reason else ""
                self._print(f"  ✗ {r.stack_name}    {r.status}{reason}", "red")

        self._print(separator, "white")

        # DNS status
        if dns_result and dns_result.attempted:
            if dns_result.success:
                self._print(f"  DNS Delegation: ✓ {dns_result.message}", "white")
            else:
                self._print(f"  DNS Delegation: ✗ {dns_result.message}", "red")
        elif partial:
            self._print("  DNS Delegation: not attempted", "white")

        self._print(separator, "white")

        # Cleanup results
        if cleanup_results:
            self._display_cleanup_summary(cleanup_results)

        # Retained resources
        if retained_resources is not None:
            if retained_resources:
                self._print("  Retained Resources:", "white")
                for res in retained_resources:
                    self._print(f"    ⚠ {res.resource_type:<20s}{res.name}", "yellow")
                self._print(
                    "  These resources were not destroyed and may require manual cleanup.",
                    "yellow",
                )
            else:
                self._print("  No retained resources detected", "white")
        elif partial:
            self._print(
                "  Retained Resources: not checked (operation aborted)", "white"
            )

        self._print(separator, "white")

        # Re-run hint for partial
        if partial:
            self._print(
                "  Re-run the destroy command to resume from where you left off.",
                "yellow",
            )

        # Determine exit code
        all_success = all(r.status == "DELETE_COMPLETE" for r in results)
        dns_ok = dns_result is None or dns_result.success
        exit_code = 0 if (all_success and dns_ok) else 1

        if partial:
            self._print(f"  Result: aborted — exit code {exit_code}", "white")
        elif exit_code == 0:
            self._print(
                f"  Result: all stacks deleted — exit code {exit_code}", "white"
            )
        else:
            failures = sum(1 for r in results if r.status != "DELETE_COMPLETE")
            self._print(
                f"  Result: {failures} failure(s) — exit code {exit_code}", "red"
            )

        self._print("", "white")
        return exit_code

    # ------------------------------------------------------------------
    # Cross-account target destroy: retained resource cleanup
    # ------------------------------------------------------------------

    def _delete_s3_bucket(
        self, session: boto3.Session, bucket_name: str
    ) -> CleanupResult:
        """Empty and delete an S3 bucket."""
        try:
            s3 = session.client("s3")
            # Empty all object versions and delete markers
            paginator = s3.get_paginator("list_object_versions")
            for page in paginator.paginate(Bucket=bucket_name):
                objects_to_delete = []
                for version in page.get("Versions", []):
                    objects_to_delete.append(
                        {"Key": version["Key"], "VersionId": version["VersionId"]}
                    )
                for marker in page.get("DeleteMarkers", []):
                    objects_to_delete.append(
                        {"Key": marker["Key"], "VersionId": marker["VersionId"]}
                    )
                if objects_to_delete:
                    # Batch delete (max 1000 per call)
                    for i in range(0, len(objects_to_delete), 1000):
                        batch = objects_to_delete[i : i + 1000]
                        s3.delete_objects(
                            Bucket=bucket_name, Delete={"Objects": batch, "Quiet": True}
                        )
            # Delete the bucket
            s3.delete_bucket(Bucket=bucket_name)
            self._print(f"  ✓ Deleted S3 Bucket: {bucket_name}", "green")
            return CleanupResult(
                resource_type="S3 Bucket", resource_name=bucket_name, status="DELETED"
            )
        except Exception as e:
            self._print(f"  ✗ Error deleting S3 Bucket {bucket_name}: {e}", "red")
            return CleanupResult(
                resource_type="S3 Bucket",
                resource_name=bucket_name,
                status="FAILED",
                error_reason=str(e),
            )

    def _delete_dynamodb_table(
        self, session: boto3.Session, table_name: str
    ) -> CleanupResult:
        """Delete a DynamoDB table, handling deletion protection."""
        try:
            dynamodb = session.client("dynamodb")
            resp = dynamodb.describe_table(TableName=table_name)
            protected = resp["Table"].get("DeletionProtectionEnabled", False)
            if protected:
                response = input(
                    f"  Deletion protection is enabled on '{table_name}'. Disable and delete? (y/N): "
                ).strip()
                if response.lower() not in ("y", "yes"):
                    self._print(
                        f"  ⊘ Skipped DynamoDB Table: {table_name} (deletion protection kept)",
                        "white",
                    )
                    return CleanupResult(
                        resource_type="DynamoDB Table",
                        resource_name=table_name,
                        status="SKIPPED",
                    )
                dynamodb.update_table(
                    TableName=table_name, DeletionProtectionEnabled=False
                )
                self._print(f"  Deletion protection disabled on {table_name}", "blue")
            dynamodb.delete_table(TableName=table_name)
            self._print(f"  ✓ Deleted DynamoDB Table: {table_name}", "green")
            return CleanupResult(
                resource_type="DynamoDB Table",
                resource_name=table_name,
                status="DELETED",
            )
        except Exception as e:
            self._print(f"  ✗ Error deleting DynamoDB Table {table_name}: {e}", "red")
            return CleanupResult(
                resource_type="DynamoDB Table",
                resource_name=table_name,
                status="FAILED",
                error_reason=str(e),
            )

    def _handle_unsupported_resource(self, resource: RetainedResource) -> CleanupResult:
        """Handle resource types that don't have automated deletion."""
        messages = {
            "Cognito User Pool": "Automated deletion of Cognito User Pools is not currently supported. Please delete manually or open a GitHub issue.",
            "Route53 Hosted Zone": "Automated deletion of Route53 Hosted Zones is not currently supported. Please delete manually or open a GitHub issue.",
            "ECR Repository": "Automated deletion of ECR Repositories is not currently supported. Please delete manually or open a GitHub issue.",
        }
        msg = messages.get(
            resource.resource_type,
            f"Automated deletion of {resource.resource_type} is not currently supported. Please delete manually or open a GitHub issue/contribution.",
        )
        self._print(f"  ⊘ {resource.name}: {msg}", "yellow")
        return CleanupResult(
            resource_type=resource.resource_type,
            resource_name=resource.name,
            status="UNSUPPORTED",
        )

    def _select_resources_for_cleanup(
        self, retained_resources: List[RetainedResource]
    ) -> List[RetainedResource]:
        """Walk through each retained resource and let the user select which to delete."""
        selected: List[RetainedResource] = []
        self._print("", "white")
        for resource in retained_resources:
            response = input(
                f"  Delete {resource.resource_type} '{resource.name}'? (y/N): "
            ).strip()
            if response.lower() in ("y", "yes"):
                selected.append(resource)
        return selected

    def _confirm_and_execute_cleanup(
        self, selected: List[RetainedResource], session: boto3.Session
    ) -> List[CleanupResult]:
        """Show batch summary, confirm, then execute deletions."""
        # Show what will be deleted
        self._print("", "white")
        self._print("  Resources selected for deletion:", "white")
        for r in selected:
            self._print(f"    - {r.resource_type}: {r.name}", "white")
        self._print("", "white")

        response = input("  Proceed with deletion? (y/N): ").strip()
        if response.lower() not in ("y", "yes"):
            self._print("  Cleanup cancelled.", "yellow")
            return []

        self._print("", "white")
        results: List[CleanupResult] = []
        handlers = {
            "S3 Bucket": lambda r: self._delete_s3_bucket(session, r.name),
            "DynamoDB Table": lambda r: self._delete_dynamodb_table(session, r.name),
        }
        for resource in selected:
            handler = handlers.get(resource.resource_type)
            if handler:
                try:
                    result = handler(resource)
                except Exception as e:
                    self._print(
                        f"  ✗ Unexpected error cleaning up {resource.name}: {e}", "red"
                    )
                    result = CleanupResult(
                        resource_type=resource.resource_type,
                        resource_name=resource.name,
                        status="FAILED",
                        error_reason=str(e),
                    )
            else:
                result = self._handle_unsupported_resource(resource)
            results.append(result)
        return results

    def _display_cleanup_summary(self, cleanup_results: List[CleanupResult]) -> None:
        """Print per-resource cleanup results."""
        if not cleanup_results:
            return
        separator = "  " + "─" * 50
        self._print("", "white")
        self._print("  Cleanup Results", "white")
        self._print(separator, "white")
        for r in cleanup_results:
            if r.status == "DELETED":
                self._print(f"  ✓ {r.resource_type}: {r.resource_name}", "green")
            elif r.status == "FAILED":
                reason = f" ({r.error_reason})" if r.error_reason else ""
                self._print(f"  ✗ {r.resource_type}: {r.resource_name}{reason}", "red")
            else:  # SKIPPED or UNSUPPORTED
                self._print(
                    f"  ⊘ {r.resource_type}: {r.resource_name} ({r.status.lower()})",
                    "white",
                )
        self._print(separator, "white")

    def _prompt_cleanup(
        self,
        retained_resources: List[RetainedResource],
        session: boto3.Session,
        no_interactive_failures: bool,
    ) -> Optional[List[CleanupResult]]:
        """Prompt to clean up retained resources. Returns None if skipped."""
        if no_interactive_failures:
            return None
        if not retained_resources:
            return None

        self._print("", "white")
        response = input(
            "  Would you like to clean up retained resources? (y/N): "
        ).strip()
        if response.lower() not in ("y", "yes"):
            return None

        selected = self._select_resources_for_cleanup(retained_resources)
        if not selected:
            self._print("  No resources selected for deletion.", "blue")
            return []

        results = self._confirm_and_execute_cleanup(selected, session)
        if results:
            self._display_cleanup_summary(results)
        return results

    # ------------------------------------------------------------------
    # Interactive helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _interactive_select(title: str, options: List[str]) -> int:
        """Present an arrow-key scrollable menu if possible, else numbered fallback.

        Returns the 0-based index of the selected option.
        """
        try:
            from simple_term_menu import TerminalMenu

            menu = TerminalMenu(options, title=title)
            idx = menu.show()
            if idx is None:
                # User pressed Escape / Ctrl-C
                print("\nAborted.")
                sys.exit(1)
            return idx
        except ImportError:
            # Fallback: numbered list
            print(title)
            for i, opt in enumerate(options, 1):
                print(f"  {i}) {opt}")
            raw = input(f"Enter choice [default 1]: ").strip() or "1"
            try:
                return int(raw) - 1
            except (ValueError, IndexError):
                print("Invalid choice.")
                sys.exit(1)

    def select_environment(self) -> EnvironmentConfig:
        """Prompt the user to select an environment (arrow-key menu).

        Shows descriptions alongside names when available from deployment configs.
        """
        envs = self.environments
        keys = list(envs.keys())
        options = []
        for key in keys:
            config = self._deployment_configs.get(key, {})
            description = config.get("description", "")
            if description:
                options.append(f"{key}: {description}")
            else:
                options.append(key)
        idx = self._interactive_select("Select deployment environment:", options)
        name = keys[idx]
        self._print(f"Using {name.upper()} environment...", "blue")
        return envs[name]

    def select_operation(self) -> str:
        """Prompt the user to select synth / deploy / diff / destroy (arrow-key menu).

        When the user selects "destroy", a sub-menu is presented with two
        options:
        - "Pipeline" → returns "destroy" (existing CDK destroy behavior)
        - "Target Resources" → returns "destroy-target" (cross-account flow)
        """
        ops = ["synth", "deploy", "diff", "destroy"]
        idx = self._interactive_select("Select operation:", ops)
        op = ops[idx]
        self._print(f"Using {op.upper()}...", "blue")

        if op != "destroy":
            return op

        destroy_options = ["Pipeline", "Target Resources"]
        idx = self._interactive_select("Select destroy target:", destroy_options)
        if idx == 0:
            self._print("Using PIPELINE destroy...", "blue")
            return "destroy"
        else:
            self._print("Using TARGET RESOURCES destroy...", "blue")
            return "destroy-target"

    def select_config_file(self, config_files: Optional[Dict[str, Dict]] = None) -> str:
        """Prompt the user to select a config file.

        Args:
            config_files: Mapping of ``"1"`` → ``{"name": "...", "file": "..."}``
                dicts.  Defaults to a single ``config.json`` option.
        """
        if not config_files:
            return "config.json"

        self._print("Select configuration:", "blue")
        for key, info in config_files.items():
            print(f"  {key}) {info['name']}")
        raw = input("Enter choice [default 1]: ").strip() or "1"
        info = config_files.get(raw, config_files.get("1"))
        self._print(f"Using {info['name']}...", "blue")
        return info["file"]

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def run(
        self,
        config_file: Optional[str] = None,
        environment_name: Optional[str] = None,
        operation: Optional[str] = None,
        dry_run: bool = False,
    ) -> None:
        """Execute the full deployment flow.

        Args:
            config_file: Path to config JSON.  Prompts if None.
            environment_name: Pre-selected environment name.  Prompts if None.
            operation: ``"synth"``, ``"deploy"``, ``"diff"``, ``"destroy"``,
                or ``"destroy-target"``.  Prompts if None.
            dry_run: Validate and display config without running CDK.
        """
        # Select environment
        if environment_name:
            if environment_name not in self.environments:
                self._print(f"Unknown environment '{environment_name}'.", "red")
                sys.exit(1)
            env_config = self.environments[environment_name]
            self._print(f"Using {environment_name.upper()} environment...", "blue")
        else:
            env_config = self.select_environment()

        # Store for mode-aware methods (load_env_file, required_vars, etc.)
        self._current_env_config = env_config

        # Load and apply env file
        env_vars = self.load_env_file(env_config.env_file)
        self.set_environment_variables(env_config, env_vars)

        # Select config file
        selected_config = config_file or "config.json"

        # Select operation
        selected_op = operation or self.select_operation()

        # If --destroy-target flag was set, force the operation
        if getattr(self, "_destroy_target", False):
            selected_op = "destroy-target"

        # For non-destroy operations, validate and run
        if selected_op not in ("destroy", "destroy-target"):
            self.validate_required_variables()
            self.display_configuration_summary(selected_config)

            if dry_run:
                self._print("Dry run — skipping CDK execution.", "yellow")
                return

            if selected_op == "synth":
                self.run_cdk_synth(selected_config)
                self._print(
                    "To deploy: cdk deploy --all --require-approval never", "blue"
                )
            elif selected_op == "deploy":
                self.run_cdk_deploy(selected_config)
            elif selected_op == "diff":
                self.run_cdk_diff(selected_config)
                self._print(
                    "To apply: cdk deploy --all --require-approval never", "blue"
                )
            return

        # Destroy operations: validate, confirm, then dispatch
        self.validate_required_variables()

        if selected_op == "destroy-target":
            # Target destroy: prompt for profile first, then show summary
            target_profile = getattr(self, "_target_profile", None)
            profile_name = self._select_target_profile(env_config, target_profile)
            self._print("", "white")
            self._print("  Target Destroy Configuration", "blue")
            self._print(
                f"    Environment    : {os.environ.get('ENVIRONMENT', 'N/A')}", "white"
            )
            self._print(
                f"    Target Account : {os.environ.get('AWS_ACCOUNT', 'N/A')}", "white"
            )
            self._print(
                f"    Region         : {os.environ.get('AWS_REGION', 'N/A')}", "white"
            )
            self._print(f"    Target Profile : {profile_name}", "white")
            self._print(
                f"    Workload       : {os.environ.get('WORKLOAD_NAME', 'N/A')}",
                "white",
            )
            self._print(
                f"    Tenant         : {os.environ.get('TENANT_NAME', 'N/A')}", "white"
            )
            self._print("", "white")
        else:
            self.display_configuration_summary(selected_config)

        if dry_run:
            self._print("Dry run — skipping CDK execution.", "yellow")
            return

        # Confirm before any destroy operation
        self._print("  ⚠  WARNING: You are about to DESTROY resources.", "red")
        response = input("  Are you sure? (y/N): ").strip()
        if response.lower() not in ("y", "yes"):
            self._print("  Aborted.", "yellow")
            sys.exit(1)

        # Dispatch destroy operations
        if selected_op == "destroy-target":
            self.run_target_destroy(
                env_config=env_config,
                target_profile=profile_name,
                confirm_destroy=getattr(self, "_confirm_destroy", False),
                skip_dns_cleanup=getattr(self, "_skip_dns_cleanup", False),
                no_interactive_failures=getattr(
                    self, "_no_interactive_failures", False
                ),
                stack_delete_timeout=getattr(self, "_stack_delete_timeout", 1800),
            )
        elif selected_op == "destroy":
            self.run_cdk_destroy(selected_config)

    @classmethod
    def main(cls, script_dir: Optional[Path] = None) -> None:
        """Parse args and run.  Call as ``MyCommand.main()`` from ``__main__``.

        Args:
            script_dir: Directory containing the deploy script, config.json,
                and deployments/ folder.  Defaults to cwd.
        """
        instance = cls(script_dir=script_dir)
        env_choices = list(instance.environments.keys())

        parser = argparse.ArgumentParser(
            description=f"CDK Deployment Command ({cls.__name__})"
        )
        parser.add_argument("--config", "-c", help="Configuration file to use")
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Validate configuration without running CDK",
        )
        parser.add_argument(
            "--environment",
            "-e",
            choices=env_choices,
            help="Skip environment selection prompt",
        )
        parser.add_argument(
            "--operation",
            "-o",
            choices=["synth", "deploy", "diff", "destroy"],
            help="Skip operation selection prompt",
        )

        # Cross-account destroy arguments
        parser.add_argument(
            "--destroy-target",
            action="store_true",
            help="Skip destroy sub-menu, go directly to target resource destruction",
        )
        parser.add_argument(
            "--target-profile",
            type=str,
            default=None,
            help="AWS profile for target account (skips profile prompt)",
        )
        parser.add_argument(
            "--confirm-destroy",
            action="store_true",
            help="Skip confirmation prompt (for CI/CD)",
        )
        parser.add_argument(
            "--skip-dns-cleanup",
            action="store_true",
            help="Skip DNS delegation cleanup prompt",
        )
        parser.add_argument(
            "--stack-delete-timeout",
            type=int,
            default=1800,
            help="Per-stack deletion timeout in seconds (default: 1800)",
        )
        parser.add_argument(
            "--no-interactive-failures",
            action="store_true",
            help="Disable interactive failure prompts; auto-continue on failures (for CI/CD)",
        )

        args = parser.parse_args()

        # Store cross-account destroy args on the instance for run() to access
        instance._destroy_target = args.destroy_target
        instance._target_profile = args.target_profile
        instance._confirm_destroy = args.confirm_destroy
        instance._skip_dns_cleanup = args.skip_dns_cleanup
        instance._stack_delete_timeout = args.stack_delete_timeout
        instance._no_interactive_failures = args.no_interactive_failures

        try:
            instance.run(
                config_file=args.config,
                environment_name=args.environment,
                operation=args.operation,
                dry_run=args.dry_run,
            )
        except KeyboardInterrupt:
            print()
            instance._print("Deployment cancelled by user.", "yellow")
            sys.exit(1)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _print(self, message: str, color: str = "white") -> None:
        _colors = {
            "red": "\033[0;31m",
            "green": "\033[0;32m",
            "yellow": "\033[0;33m",
            "blue": "\033[0;34m",
            "cyan": "\033[0;36m",
            "white": "\033[0m",
        }
        prefix = {"red": "✗ ", "green": "✓ ", "yellow": "⚠ ", "blue": "ℹ "}.get(
            color, ""
        )
        code = _colors.get(color, _colors["white"])
        reset = _colors["white"]
        print(f"{code}{prefix}{message}{reset}")

    def _run(self, cmd: List[str]) -> None:
        """Run *cmd* in script_dir, streaming output.  Raises SystemExit on failure."""
        try:
            result = subprocess.run(cmd, cwd=self.script_dir, env=os.environ.copy())
            if result.returncode != 0:
                self._print(f"Command failed: {' '.join(cmd)}", "red")
                sys.exit(result.returncode)
        except FileNotFoundError:
            self._print(f"Command not found: {cmd[0]}", "red")
            sys.exit(1)
