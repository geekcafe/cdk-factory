"""Monitor subcommand parser + dispatch (design §2.2).

``build_monitor_subparser`` builds an ``aws``-style subcommand parser
(``init | configure | deploy | synth | status``). ``dispatch`` constructs the
project's :class:`WizardDefinition` (via the command's ``wizard_definition``
factory) and routes to the :class:`WizardRunner` / ``command.run`` per the §2.2
table.

The monitor ``-e/--environment`` is deliberately FREE-FORM (``type=str``, NOT
``choices=``) so a first-run ``monitor init -e prod`` is accepted for an
environment that does not exist yet.
"""

from __future__ import annotations

import argparse
import sys


def build_monitor_subparser(prog: str = "monitor") -> argparse.ArgumentParser:
    """Return the monitor subcommand parser.

    ``monitor`` with no subcommand errors "subcommand required"; ``monitor
    <bad>`` errors within this parser (not the legacy parser).
    """
    parser = argparse.ArgumentParser(prog=prog, description="Guided monitor wizard")
    subparsers = parser.add_subparsers(dest="subcommand", required=True)

    def _add_env(sp):
        # FREE-FORM (not choices=) so a not-yet-existing env is accepted.
        sp.add_argument(
            "--environment", "-e", type=str, help="Environment name (e.g. prod)"
        )

    def _add_tenant(sp):
        # FREE-FORM (not choices=), like -e. The organization / account this
        # monitor deploys into; REQUIRED (resolved in dispatch, not by argparse,
        # so the migration + interactive-prompt paths can run).
        sp.add_argument(
            "--tenant",
            "-t",
            type=str,
            help="Tenant / organization name (e.g. geekcafe, aplos)",
        )

    # init
    sp_init = subparsers.add_parser("init", help="Full guided setup + optional deploy")
    _add_env(sp_init)
    _add_tenant(sp_init)
    sp_init.add_argument("--profile", type=str, help="AWS profile to inspect with")
    sp_init.add_argument("--region", type=str, help="AWS region")
    sp_init.add_argument("--answers", type=str, help="Path to a prepared answers file")
    sp_init.add_argument(
        "--non-interactive",
        action="store_true",
        help="Fail fast instead of prompting (requires --answers)",
    )

    # configure
    sp_cfg = subparsers.add_parser("configure", help="Re-run/edit answers; no deploy")
    _add_env(sp_cfg)
    _add_tenant(sp_cfg)
    sp_cfg.add_argument("--profile", type=str, help="AWS profile to inspect with")
    sp_cfg.add_argument("--region", type=str, help="AWS region")
    sp_cfg.add_argument("--answers", type=str, help="Path to a prepared answers file")
    sp_cfg.add_argument(
        "--non-interactive",
        action="store_true",
        help="Fail fast instead of prompting (requires --answers)",
    )

    # deploy
    sp_deploy = subparsers.add_parser("deploy", help="Deploy using saved answers")
    _add_env(sp_deploy)
    _add_tenant(sp_deploy)
    sp_deploy.add_argument(
        "--mode", "-m", choices=["pipeline", "stack"], help="Deployment shape"
    )
    sp_deploy.add_argument(
        "--dry-run", action="store_true", help="Validate without running CDK"
    )

    # synth
    sp_synth = subparsers.add_parser("synth", help="Synth only, using saved answers")
    _add_env(sp_synth)
    _add_tenant(sp_synth)
    sp_synth.add_argument(
        "--mode", "-m", choices=["pipeline", "stack"], help="Deployment shape"
    )

    # status
    sp_status = subparsers.add_parser(
        "status", help="Show resolved config (no AWS calls)"
    )
    _add_env(sp_status)
    _add_tenant(sp_status)

    return parser


def dispatch(command, subcommand: str, ns: argparse.Namespace) -> None:
    """Route a parsed monitor subcommand to the toolkit / command.

    ``status`` is resolved-config-only (NO AWS call, NIT-3). ``init``/``configure``
    run the guided flow via :class:`WizardRunner`. ``deploy``/``synth`` reuse the
    command's existing ``run`` with saved answers.

    A prompt cancellation (Ctrl-C / ESC) raised by the prompter as
    :class:`PromptCancelledError` (or a bare ``KeyboardInterrupt``) exits
    cleanly with a message and a non-zero code — never a traceback or an
    inescapable re-prompt loop.
    """
    from cdk_factory.wizard.prompts import PromptCancelledError

    try:
        _dispatch(command, subcommand, ns)
    except (PromptCancelledError, KeyboardInterrupt):
        command._print("\nCancelled by user — no changes written.", "yellow")
        sys.exit(130)  # 128 + SIGINT, conventional for Ctrl-C


def _dispatch(command, subcommand: str, ns: argparse.Namespace) -> None:
    """Inner dispatch body (see :func:`dispatch` for the cancellation wrapper)."""
    from cdk_factory.wizard.answers_store import AnswersStore
    from cdk_factory.wizard.wizard_base import WizardRunner

    definition = command.wizard_definition()
    environment = getattr(ns, "environment", None) or "default"

    # TENANT is resolved FIRST, unconditionally, for every subcommand — so
    # deploy/synth/status also require --tenant (or a migratable prior) and
    # cannot silently fall back to a bare-env answers/.env file. The composed
    # file_key is the single discriminator for both persisted artifacts.
    tenant = _resolve_tenant(command, ns, environment)
    file_key = f"{tenant}-{environment}"
    store = AnswersStore(command.script_dir, file_key)

    if subcommand in ("init", "configure"):
        non_interactive = getattr(ns, "non_interactive", False)
        answers_file = getattr(ns, "answers", None)
        if non_interactive and not answers_file:
            command._print(
                "monitor init/configure in non-interactive mode requires --answers FILE.",
                "red",
            )
            sys.exit(2)

        prior = store.load()
        # Fallback: no saved answers file, but the project's derived config may
        # already exist (e.g. a deployment rendered via a non-wizard path). Seed
        # prompts from it so re-running is edit-in-place, not start-from-blank.
        if not prior:
            reconstructed = definition.load_prior_from_derived(file_key)
            if reconstructed:
                command._print(
                    "No saved answers found; seeding from the existing "
                    "configuration for this tenant/environment.",
                    "blue",
                )
                prior = reconstructed
        cli_overrides = {
            "environment": environment,  # bare env -> ENVIRONMENT scalar
            "tenant": tenant,  # org      -> TENANT_NAME scalar
            "aws": _aws_overrides(ns, prior),
        }
        merged = store.merge_defaults(prior, cli_overrides)
        if answers_file:
            import json

            with open(answers_file, "r", encoding="utf-8") as fh:
                merged = store.merge_defaults(merged, json.load(fh))
        WizardRunner().run(command, definition, merged, file_key=file_key)
        return

    if subcommand in ("deploy", "synth"):
        operation = "deploy" if subcommand == "deploy" else "synth"
        answers = store.load() or {}
        mode = getattr(ns, "mode", None) or answers.get("mode")
        command.run(
            environment_name=file_key,
            operation=operation,
            dry_run=getattr(ns, "dry_run", False),
            mode=mode,
        )
        return

    if subcommand == "status":
        _print_status(command, store, file_key)
        return

    command._print(f"Unknown monitor subcommand: {subcommand}", "red")
    sys.exit(2)


def _resolve_tenant(command, ns: argparse.Namespace, environment: str) -> str:
    """Resolve the required tenant: CLI ``--tenant`` -> legacy migration -> fail/prompt.

    Order:
      1. ``--tenant`` given → use it (stripped).
      2. No ``--tenant`` → try the one-time legacy-answers migration (§5.5); if it
         yields a tenant, use it.
      3. Non-interactive (``--non-interactive`` OR not a TTY) → fail fast with the
         self-documenting error, exit 2. NEVER invents a tenant.
      4. TTY → prompt "Tenant / organization name" (re-prompt until non-empty).
    """
    tenant = getattr(ns, "tenant", None)
    if tenant and tenant.strip():
        return tenant.strip()

    # Authoritative non-interactive signal on ALL five subcommands:
    # --non-interactive exists only on init/configure (defaults False elsewhere);
    # the TTY check is what catches a scripted deploy/synth/status with no tenant.
    non_interactive = getattr(ns, "non_interactive", False) or not sys.stdin.isatty()

    migrated = _migrate_legacy_answers(command, environment, non_interactive)
    if migrated:
        return migrated

    if non_interactive:
        command._print(
            "--tenant is required: the organization / account name this monitor "
            "is deployed into (e.g. --tenant geekcafe, --tenant aplos)",
            "red",
        )
        sys.exit(2)

    return _prompt_tenant(command)


def _prompt_tenant(command) -> str:
    """Prompt for a non-empty tenant on a TTY (re-prompt until non-empty)."""
    from cdk_factory.wizard.wizard_base import command_prompt

    prompt = command_prompt(command)
    while True:
        value = (prompt.text("Tenant / organization name", default="") or "").strip()
        if value:
            return value


def _migrate_legacy_answers(command, environment: str, non_interactive: bool):
    """One-time migration of a legacy bare-``<env>`` answers file to ``<tenant>-<env>``.

    Returns the operator-supplied tenant when a legacy file was migrated, else
    ``None``. NEVER fabricates a tenant — on no-TTY it returns ``None`` so the
    caller fails fast.
    """
    from cdk_factory.wizard.answers_store import AnswersStore

    legacy = AnswersStore(command.script_dir, environment)  # OLD bare-env key
    if not legacy.path.exists():
        return None
    if non_interactive:
        return None  # caller fails fast; do NOT invent a tenant

    tenant = _prompt_tenant(command)
    old = legacy.load() or {}
    old["tenant"] = tenant
    AnswersStore(command.script_dir, f"{tenant}-{environment}").save(old)  # NEW key
    command._print(
        f"Migrated answers {legacy.path.name} -> "
        f"{tenant}-{environment}.answers.json (original left in place).",
        "green",
    )
    return tenant


def _aws_overrides(ns: argparse.Namespace, prior) -> dict:
    """Build the aws-section overrides from CLI args, falling back to prior."""
    prior_aws = {}
    if isinstance(prior, dict) and isinstance(prior.get("aws"), dict):
        prior_aws = prior["aws"]
    return {
        "profile": getattr(ns, "profile", None) or prior_aws.get("profile"),
        "region": getattr(ns, "region", None) or prior_aws.get("region"),
        "account": prior_aws.get("account"),
    }


def _print_status(command, store, file_key: str) -> None:
    """Print the resolved answers (no AWS call, NIT-3)."""
    answers = store.load()
    if answers is None:
        command._print(
            f"No saved answers for '{file_key}'. Run 'monitor init' first.",
            "yellow",
        )
        return
    command._print(f"Resolved configuration for '{file_key}':", "blue")
    import json

    print(json.dumps(answers, indent=4))
