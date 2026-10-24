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

    # init
    sp_init = subparsers.add_parser("init", help="Full guided setup + optional deploy")
    _add_env(sp_init)
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
    sp_deploy.add_argument(
        "--mode", "-m", choices=["pipeline", "stack"], help="Deployment shape"
    )
    sp_deploy.add_argument(
        "--dry-run", action="store_true", help="Validate without running CDK"
    )

    # synth
    sp_synth = subparsers.add_parser("synth", help="Synth only, using saved answers")
    _add_env(sp_synth)
    sp_synth.add_argument(
        "--mode", "-m", choices=["pipeline", "stack"], help="Deployment shape"
    )

    # status
    sp_status = subparsers.add_parser(
        "status", help="Show resolved config (no AWS calls)"
    )
    _add_env(sp_status)

    return parser


def dispatch(command, subcommand: str, ns: argparse.Namespace) -> None:
    """Route a parsed monitor subcommand to the toolkit / command.

    ``status`` is resolved-config-only (NO AWS call, NIT-3). ``init``/``configure``
    run the guided flow via :class:`WizardRunner`. ``deploy``/``synth`` reuse the
    command's existing ``run`` with saved answers.
    """
    from cdk_factory.wizard.answers_store import AnswersStore
    from cdk_factory.wizard.wizard_base import WizardRunner

    definition = command.wizard_definition()
    environment = getattr(ns, "environment", None) or "default"
    store = AnswersStore(command.script_dir, environment)

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
        cli_overrides = {
            "environment": environment,
            "aws": _aws_overrides(ns, prior),
        }
        merged = store.merge_defaults(prior, cli_overrides)
        if answers_file:
            import json

            with open(answers_file, "r", encoding="utf-8") as fh:
                merged = store.merge_defaults(merged, json.load(fh))
        WizardRunner().run(command, definition, merged)
        return

    if subcommand in ("deploy", "synth"):
        operation = "deploy" if subcommand == "deploy" else "synth"
        answers = store.load() or {}
        mode = getattr(ns, "mode", None) or answers.get("mode")
        command.run(
            environment_name=getattr(ns, "environment", None),
            operation=operation,
            dry_run=getattr(ns, "dry_run", False),
            mode=mode,
        )
        return

    if subcommand == "status":
        _print_status(command, store, environment)
        return

    command._print(f"Unknown monitor subcommand: {subcommand}", "red")
    sys.exit(2)


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


def _print_status(command, store, environment: str) -> None:
    """Print the resolved answers (no AWS call, NIT-3)."""
    answers = store.load()
    if answers is None:
        command._print(
            f"No saved answers for environment '{environment}'. Run 'monitor init' first.",
            "yellow",
        )
        return
    command._print(f"Resolved configuration for '{environment}':", "blue")
    import json

    print(json.dumps(answers, indent=4))
