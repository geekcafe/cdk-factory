"""
CodePipeline Monitor Configuration

Parses the ``codepipeline_monitor`` stack block into a small config wrapper with
typed ``@property`` accessors, mirroring
``configurations/resources/appsync_events.py`` (``AppSyncEventsConfig``).

Describes a config-driven CodePipeline (and optional CodeBuild) state-change
monitor: which pipelines to watch (none / all / selected), which detail-types
and states to match, how states map to priorities, and the optional CodeBuild
and approval-rejection hooks. Consumed by the ``codepipeline_monitor_stack``,
which builds its own ``events.Rule`` + ``aws_events_targets.LambdaFunction``
target against an adapter Lambda imported by ARN from SSM.

Rule-relevant keys (used by the stack) are ``adapter_lambda_arn_ssm_path``,
``event_bus_name``, ``pipelines``, ``detail_types``, the state keys of
``state_priority_map``, and the ``codebuild`` / ``approval_rejection`` blocks.
Other keys (``tenant_id``, ``slack``, ``console_base_url`` ...) are adapter-facing
and ignored here. Unknown keys are ignored.

Geek Cafe, LLC
Maintainers: Eric Wilson
MIT License. See Project Root for the license information.
"""

from typing import Any, Dict, List


class CodePipelineMonitorCodeBuildConfig:
    """Optional ``codebuild`` sub-block.

    When ``enabled`` is true the stack builds an additional ``events.Rule`` for
    ``aws.codebuild`` build state-change events.
    """

    def __init__(self, config: Any) -> None:
        self._config: Dict[str, Any] = config if isinstance(config, dict) else {}

    @property
    def enabled(self) -> bool:
        """Whether to build the CodeBuild rule (default False)."""
        value = self._config.get("enabled", False)
        if isinstance(value, bool):
            return value
        return str(value).lower() == "true"

    @property
    def detail_types(self) -> List[str]:
        """CodeBuild detail-types to match (default build state change)."""
        value = self._config.get("detail_types")
        if isinstance(value, list) and value:
            return [str(item) for item in value]
        return ["CodeBuild Build State Change"]

    @property
    def build_status_priority_map(self) -> Dict[str, str]:
        """build-status -> priority map (default ``{'FAILED': 'critical'}``)."""
        value = self._config.get("build_status_priority_map")
        if isinstance(value, dict) and value:
            return {str(k): str(v) for k, v in value.items()}
        return {"FAILED": "critical"}


class CodePipelineMonitorApprovalRejectionConfig:
    """Optional ``approval_rejection`` sub-block (hook only, OFF by default)."""

    def __init__(self, config: Any) -> None:
        self._config: Dict[str, Any] = config if isinstance(config, dict) else {}

    def _bool(self, key: str) -> bool:
        value = self._config.get(key, False)
        if isinstance(value, bool):
            return value
        return str(value).lower() == "true"

    @property
    def enabled(self) -> bool:
        """Whether the adapter's approval-rejection branch is active (default False)."""
        return self._bool("enabled")

    @property
    def subscribe_action_execution(self) -> bool:
        """When true, widen the rule to the action-execution detail-type (default False)."""
        return self._bool("subscribe_action_execution")

    @property
    def treat_as(self) -> str:
        """How the adapter treats a rejection (default ``'distinct_event'``)."""
        return str(self._config.get("treat_as", "distinct_event"))

    @property
    def distinct_event_type(self) -> str:
        """Event type emitted for a rejection (default ``'cicd.pipeline.rejected'``)."""
        return str(self._config.get("distinct_event_type", "cicd.pipeline.rejected"))


class CodePipelineMonitorPipelinesConfig:
    """The ``pipelines`` selection sub-block.

    ``mode`` is one of ``none`` / ``all`` / ``selected`` (default ``all``).
    ``names`` is honored only in ``selected`` mode; ``exclude_names`` is honored
    only in ``all`` mode.
    """

    _VALID_MODES = {"none", "all", "selected"}

    def __init__(self, config: Any) -> None:
        self._config: Dict[str, Any] = config if isinstance(config, dict) else {}

    @property
    def mode(self) -> str:
        """Selection mode (``none`` | ``all`` | ``selected``; default ``all``)."""
        mode = str(self._config.get("mode", "all")).lower()
        if mode not in self._VALID_MODES:
            return "all"
        return mode

    @property
    def names(self) -> List[str]:
        """Pipeline names to watch; ``[]`` unless ``mode == 'selected'``."""
        if self.mode != "selected":
            return []
        value = self._config.get("names")
        if isinstance(value, list):
            return [str(item) for item in value]
        return []

    @property
    def exclude_names(self) -> List[str]:
        """Pipeline names to exclude; ``[]`` unless ``mode == 'all'``."""
        if self.mode != "all":
            return []
        value = self._config.get("exclude_names")
        if isinstance(value, list):
            return [str(item) for item in value]
        return []


class CodePipelineMonitorConfig:
    """CodePipeline monitor stack configuration.

    Parses the ``codepipeline_monitor`` block. The top-level ``enabled`` flag and
    the stack ``name`` are read from the surrounding stack dict (so this wrapper
    accepts the whole stack dict, like ``AppSyncEventsConfig`` accepts the
    ``appsync_events`` sub-block). To mirror ``AppSyncEventsConfig`` exactly,
    this class is constructed from the ``codepipeline_monitor`` sub-block, while
    ``name`` / ``enabled`` are passed in separately by the stack.
    """

    def __init__(self, config: Dict[str, Any]) -> None:
        self._config: Dict[str, Any] = config if isinstance(config, dict) else {}

    @property
    def adapter_lambda_arn_ssm_path(self) -> str:
        """SSM path to the adapter Lambda ARN (resolved as a deploy-time token)."""
        return str(self._config.get("adapter_lambda_arn_ssm_path", ""))

    @property
    def event_bus_name(self) -> str:
        """Event bus the rules attach to (default ``'default'``)."""
        return str(self._config.get("event_bus_name", "default"))

    @property
    def pipelines(self) -> CodePipelineMonitorPipelinesConfig:
        """The pipeline-selection sub-block."""
        return CodePipelineMonitorPipelinesConfig(self._config.get("pipelines", {}))

    @property
    def detail_types(self) -> List[str]:
        """CodePipeline detail-types to match (default pipeline-execution)."""
        value = self._config.get("detail_types")
        if isinstance(value, list) and value:
            return [str(item) for item in value]
        return ["CodePipeline Pipeline Execution State Change"]

    @property
    def state_priority_map(self) -> Dict[str, str]:
        """state -> priority map (default ``{'FAILED': 'critical'}``)."""
        value = self._config.get("state_priority_map")
        if isinstance(value, dict) and value:
            return {str(k): str(v) for k, v in value.items()}
        return {"FAILED": "critical"}

    @property
    def codebuild(self) -> CodePipelineMonitorCodeBuildConfig:
        """The optional CodeBuild sub-block."""
        return CodePipelineMonitorCodeBuildConfig(self._config.get("codebuild", {}))

    @property
    def approval_rejection(self) -> CodePipelineMonitorApprovalRejectionConfig:
        """The optional approval-rejection sub-block (OFF by default)."""
        return CodePipelineMonitorApprovalRejectionConfig(
            self._config.get("approval_rejection", {})
        )

    @property
    def ssm(self) -> Dict[str, Any]:
        """SSM export passthrough (e.g. ``{"namespace": "<prefix>"}``)."""
        ssm = self._config.get("ssm", {})
        return ssm if isinstance(ssm, dict) else {}

    def is_enabled(self, stack_enabled: bool = True) -> bool:
        """Return ``False`` when ``mode == 'none'`` or the stack is disabled.

        ``stack_enabled`` carries the top-level ``enabled`` flag from the stack
        dict (the stack passes ``stack_config.dictionary.get('enabled', True)``).
        """
        if not stack_enabled:
            return False
        return self.pipelines.mode != "none"
