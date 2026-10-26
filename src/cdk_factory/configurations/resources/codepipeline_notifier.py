"""
CodePipeline Notifier Configuration

Parses the ``codepipeline_notifier`` stack block into a config wrapper with
typed ``@property`` accessors, mirroring
``configurations/resources/codepipeline_monitor.py`` (``CodePipelineMonitorConfig``).

Describes the SELF-CONTAINED CodePipeline/CodeBuild failure monitor (the
``codepipeline_notifier_stack`` companion to ``codepipeline_monitor_stack``):
which pipelines to watch (none / all / selected), the per-channel routing
targets (Slack channel id + SNS emails), the central overview channel, the
pipeline → channel routing, the state → priority / deliver gate, the optional
CodeBuild and approval-rejection hooks, the Slack bot-token secret name, and the
packaged notifier Lambda sub-block.

Unlike ``CodePipelineMonitorConfig`` (which imports an adapter Lambda by ARN and
is purely about routing), this config owns the whole self-contained graph the
stack provisions: per-channel SNS topics, the EventBridge rule(s) targeting an
OWNED notifier Lambda, and scoped IAM. See the design doc §6/§8.

Geek Cafe, LLC
Maintainers: Eric Wilson
MIT License. See Project Root for the license information.
"""

from typing import Any, Dict, List


class CodePipelineNotifierCodeBuildConfig:
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


class CodePipelineNotifierApprovalRejectionConfig:
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
        """Whether the handler's approval-rejection branch is active (default False)."""
        return self._bool("enabled")

    @property
    def subscribe_action_execution(self) -> bool:
        """When true, widen the rule to the action-execution detail-type (default False)."""
        return self._bool("subscribe_action_execution")

    @property
    def treat_as(self) -> str:
        """How the handler treats a rejection (default ``'distinct_event'``)."""
        return str(self._config.get("treat_as", "distinct_event"))

    def to_dict(self) -> Dict[str, Any]:
        """The approval-rejection block as the handler env wire format.

        Mirrors the handler default ``{"enabled": false, "treat_as":
        "distinct_event"}`` (design §6.5).
        """
        return {"enabled": self.enabled, "treat_as": self.treat_as}


class CodePipelineNotifierPipelinesConfig:
    """The ``pipelines`` selection sub-block.

    ``mode`` is one of ``none`` / ``all`` / ``selected`` (default ``all``).
    ``names`` is honored only in ``selected`` mode; ``exclude_names`` is honored
    only in ``all`` mode. Semantics mirror
    ``CodePipelineMonitorPipelinesConfig`` exactly.
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


class CodePipelineNotifierChannelConfig:
    """A single named routing target = ``{slack_channel_id?, sns_emails[]?}``.

    A channel may be Slack-only, SNS-only, or both. A channel with NEITHER a
    non-empty ``slack_channel_id`` NOR at least one ``sns_emails`` address is
    useless and rejected at synth (design §6.2 step 2).
    """

    def __init__(self, name: str, config: Any) -> None:
        self.name = name
        self._config: Dict[str, Any] = config if isinstance(config, dict) else {}

    @property
    def slack_channel_id(self) -> str:
        """Slack channel id this channel posts to (empty => SNS-only)."""
        return str(self._config.get("slack_channel_id", "") or "")

    @property
    def mention(self) -> "str | None":
        """Opt-in broadcast mention for critical-failure Slack posts.

        ``"channel"`` (<!channel>), ``"here"`` (<!here>), or ``None`` (no
        mention). Empty/absent normalizes to ``None``. The value is NOT
        validated here — the SDK notifier cold-start parser is the fail-fast
        authority for channel shape (mirroring how priorities are validated in
        the stack but channel shape is passed through).
        """
        return str(self._config.get("mention") or "") or None

    @property
    def sns_emails(self) -> List[str]:
        """Email addresses subscribed to this channel's SNS topic."""
        value = self._config.get("sns_emails")
        if isinstance(value, list):
            return [str(item) for item in value if str(item)]
        return []


class CodePipelineNotifierConfig:
    """CodePipeline notifier stack configuration.

    Parses the ``codepipeline_notifier`` block. The top-level ``enabled`` flag
    and the stack ``name`` are read from the surrounding stack dict (so this
    wrapper is constructed from the ``codepipeline_notifier`` sub-block, like
    ``CodePipelineMonitorConfig``).
    """

    def __init__(self, config: Dict[str, Any]) -> None:
        self._config: Dict[str, Any] = config if isinstance(config, dict) else {}

    @property
    def pipelines(self) -> CodePipelineNotifierPipelinesConfig:
        """The pipeline-selection sub-block."""
        return CodePipelineNotifierPipelinesConfig(self._config.get("pipelines", {}))

    @property
    def detail_types(self) -> List[str]:
        """CodePipeline detail-types to match (default pipeline-execution)."""
        value = self._config.get("detail_types")
        if isinstance(value, list) and value:
            return [str(item) for item in value]
        return ["CodePipeline Pipeline Execution State Change"]

    @property
    def slack_bot_token_secret_name(self) -> str:
        """Secrets Manager secret name holding the Slack bot token."""
        return str(self._config.get("slack_bot_token_secret_name", "") or "")

    @property
    def channels(self) -> Dict[str, CodePipelineNotifierChannelConfig]:
        """Named routing targets (``name -> {slack_channel_id, sns_emails[]}``)."""
        raw = self._config.get("channels", {})
        if not isinstance(raw, dict):
            return {}
        return {
            str(name): CodePipelineNotifierChannelConfig(str(name), cfg)
            for name, cfg in raw.items()
        }

    @property
    def central(self) -> str:
        """Channel name that receives every *delivered* in-scope notice."""
        return str(self._config.get("central", "") or "")

    @property
    def pipeline_routes(self) -> Dict[str, List[str]]:
        """``pipeline_name -> [channel_name, ...]`` team routing (central always added)."""
        raw = self._config.get("pipeline_routes", {})
        if not isinstance(raw, dict):
            return {}
        routes: Dict[str, List[str]] = {}
        for pipeline, channels in raw.items():
            if isinstance(channels, list):
                routes[str(pipeline)] = [str(c) for c in channels]
            else:
                routes[str(pipeline)] = []
        return routes

    @property
    def state_priority_map(self) -> Dict[str, str]:
        """state -> priority map (default ``{'FAILED': 'critical'}``)."""
        value = self._config.get("state_priority_map")
        if isinstance(value, dict) and value:
            return {str(k): str(v) for k, v in value.items()}
        return {"FAILED": "critical"}

    @property
    def deliver_priorities(self) -> List[str]:
        """Priorities that actually deliver (default ``['critical']``)."""
        value = self._config.get("deliver_priorities")
        if isinstance(value, list) and value:
            return [str(item) for item in value]
        return ["critical"]

    @property
    def codebuild(self) -> CodePipelineNotifierCodeBuildConfig:
        """The optional CodeBuild sub-block."""
        return CodePipelineNotifierCodeBuildConfig(self._config.get("codebuild", {}))

    @property
    def approval_rejection(self) -> CodePipelineNotifierApprovalRejectionConfig:
        """The optional approval-rejection sub-block (OFF by default)."""
        return CodePipelineNotifierApprovalRejectionConfig(
            self._config.get("approval_rejection", {})
        )

    @property
    def lambda_config(self) -> Dict[str, Any]:
        """The ``lambda`` packaging sub-block (raw dict for ``LambdaFunctionConfig``)."""
        value = self._config.get("lambda", {})
        return value if isinstance(value, dict) else {}

    @property
    def console_base_url(self) -> str:
        """Console URL template (default region-templated AWS console base)."""
        return str(
            self._config.get(
                "console_base_url", "https://{region}.console.aws.amazon.com"
            )
        )

    @property
    def ssm(self) -> Dict[str, Any]:
        """SSM export passthrough (e.g. ``{"namespace": "<prefix>"}``)."""
        ssm = self._config.get("ssm", {})
        return ssm if isinstance(ssm, dict) else {}

    def is_enabled(self, stack_enabled: bool = True) -> bool:
        """Return ``False`` when ``mode == 'none'`` or the stack is disabled.

        Mirrors ``CodePipelineMonitorConfig.is_enabled`` EXACTLY: ``False`` when
        ``stack_enabled is False`` OR ``pipelines.mode == 'none'``.
        """
        if not stack_enabled:
            return False
        return self.pipelines.mode != "none"
