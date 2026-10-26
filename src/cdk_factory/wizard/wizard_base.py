"""Generic wizard contract + runner (design §2.3, §2.9).

``WizardDefinition`` is the shape-agnostic contract a project supplies to drive
the toolkit; it knows nothing about Slack/SNS/notifier specifics. ``WizardRunner``
drives the five guided steps using the passed-in command instance's existing
``select_deployment_mode``/``run``/``run_post_deploy_steps``, the inspector, the
prompt port, and the :class:`AnswersStore`.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Optional

from cdk_factory.wizard.answers_store import AnswersStore
from cdk_factory.wizard.aws_inspectors import AwsInspector
from cdk_factory.wizard.connection_flow import resolve_usable_connection
from cdk_factory.wizard.prompts import PromptPort


class WizardDefinition(ABC):
    """Project-supplied hooks the generic toolkit drives.

    A concrete definition declares WHAT the project asks and HOW answers map to
    its own config files. It stays generic/shape-agnostic — no notifier/Slack/SNS
    knowledge lives in this base class.
    """

    @abstractmethod
    def secret_id(self) -> str:
        """Secrets Manager id for the project's post-deploy secret."""

    @abstractmethod
    def read_workload_name(self) -> str:
        """Resolved workload name (e.g. from the project's config.json)."""

    @abstractmethod
    def read_repo_owner(self) -> Optional[str]:
        """Git repo owner used to rank connections (or ``None``)."""

    @abstractmethod
    def collect_answers(
        self,
        command,
        prompt: PromptPort,
        inspector: AwsInspector,
        prior: Optional[dict],
    ) -> dict:
        """Run the project's question set and return a plain answers dict.

        The definition owns its typed model internally; the value returned here
        is the JSON-able dict persisted by :class:`AnswersStore`.
        """

    @abstractmethod
    def apply_to_notifier_json(self, answers: dict) -> None:
        """Read-modify-write the project's derived config from *answers*.

        Must preserve every unmapped key verbatim (OPEN-FINDINGS NIT-3).
        """

    @abstractmethod
    def to_env_scalars(self, answers: dict) -> dict:
        """Return the flat ``.env.<env>`` scalars derived from *answers*."""

    def load_prior_from_derived(self, file_key: str) -> Optional[dict]:
        """Reconstruct prior answers from the project's DERIVED config, or None.

        Optional fallback used by ``init``/``configure`` when no
        ``.monitor/<file_key>.answers.json`` exists but the project's derived
        config (which the wizard renders) DOES — e.g. a deployment made via a
        non-wizard path, or before the answers file was persisted. Returning a
        reconstructed answers dict lets the wizard seed its prompts with the
        live config instead of starting blank.

        Default: ``None`` (no reconstruction). A project overrides this to read
        its rendered artifact (for the monitor, ``.monitor/<file_key>
        .notifier.json``) back into answers-shaped defaults.
        """
        return None

    # Optional round-trip helpers; defaults are identity passthroughs so a
    # definition that already works in dict-space need not override them.
    def to_dict(self, answers: dict) -> dict:
        return dict(answers)

    def from_dict(self, data: dict) -> dict:
        return dict(data)

    def review_rows(self, answers: dict) -> List[List[str]]:
        """Return rows for the review table; default renders top-level scalars."""
        rows: List[List[str]] = []
        for key, value in answers.items():
            if isinstance(value, (dict, list)):
                value = str(value)
            rows.append([str(key), str(value)])
        return rows


class WizardRunner:
    """Drives the five guided steps against a command + definition."""

    def run(
        self, command, definition: WizardDefinition, answers: dict, *, file_key: str
    ) -> dict:
        """Execute the full ``monitor init`` flow.

        Args:
            command: The :class:`CdkDeploymentCommand` instance (reused for
                ``select_deployment_mode``/``run``/``write_env_scalars``).
            definition: The project's :class:`WizardDefinition`.
            answers: In-memory answers dict (prior answers merged by the caller).
            file_key: The single discriminator for the two persisted artifacts
                (``.monitor/<file_key>.answers.json`` and ``.env.<file_key>``).
                Keyword-only with NO default so no caller can silently fall back
                to the bare environment — the only caller is
                ``cdk_factory.wizard.cli.dispatch``, which passes
                ``f"{tenant}-{environment}"``. ``to_env_scalars`` still emits the
                bare ``ENVIRONMENT`` scalar (the ``{{ENVIRONMENT}}`` naming
                segment); ``file_key`` only names the two files.

        Returns:
            The final answers dict (also persisted when the operator confirms).
        """
        prompt: PromptPort = command_prompt(command)
        inspector = command_inspector(command, answers)
        store = AnswersStore(command.script_dir, file_key)

        # Steps 1-4: delegate the project-specific question set to the definition.
        answers = definition.collect_answers(command, prompt, inspector, answers)

        # Deploy mode (reuse existing selection semantics). The preselected
        # default follows the project's configured DEPLOYMENT_MODE default so the
        # prompt matches the config.json / non-interactive default.
        if not answers.get("mode"):
            answers["mode"] = command.select_deployment_mode(
                default=command._configured_default_mode()
            )

        # Pipeline-mode connection resolution.
        if answers.get("mode") == "pipeline":
            result = resolve_usable_connection(
                inspector,
                prompt,
                preferred_arn=answers.get("connection_arn"),
                repo_owner=definition.read_repo_owner(),
                provider_hint=answers.get("provider_hint"),
            )
            answers["connection_arn"] = result.arn
        else:
            answers["connection_arn"] = None

        # Persist incrementally before the review/confirm.
        store.save(answers)

        # Step 5: review + write + optional deploy.
        prompt.table(
            "Review",
            ["Field", "Value"],
            definition.review_rows(answers),
        )
        if not prompt.confirm("Write config and continue?", default=True):
            return answers

        command.write_env_scalars(
            file_key,
            definition.to_env_scalars(answers),
        )
        definition.apply_to_notifier_json(answers)
        store.save(answers)

        if prompt.confirm("Run synth now?", default=False):
            command.run(
                environment_name=file_key,
                operation="synth",
                mode=answers.get("mode"),
            )
        if prompt.confirm("Deploy now?", default=False):
            command.run(
                environment_name=file_key,
                operation="deploy",
                mode=answers.get("mode"),
            )
        return answers


def command_prompt(command) -> PromptPort:
    """Return the prompt port a command exposes, or a fresh QuestionaryPrompter."""
    existing = getattr(command, "wizard_prompt", None)
    if existing is not None:
        return existing
    from cdk_factory.wizard.prompts import QuestionaryPrompter  # lazy

    return QuestionaryPrompter()


def command_inspector(command, answers: dict) -> AwsInspector:
    """Return the inspector a command exposes, or build a lazy default one."""
    existing = getattr(command, "wizard_inspector", None)
    if existing is not None:
        return existing
    aws = answers.get("aws", {}) if isinstance(answers.get("aws"), dict) else {}
    return AwsInspector(profile=aws.get("profile"), region=aws.get("region"))
