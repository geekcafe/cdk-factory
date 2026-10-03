"""
Shared helpers for the chatops cdk-factory synth tests.

Loads the self-contained sample workload config at samples/chatops/config.json,
resolves the template placeholders ({{WORKLOAD_NAME}}, {{DEPLOYMENT_NAMESPACE}},
{{AWS_ACCOUNT}}, {{AWS_REGION}}), and exposes the individual stack configs.

No AWS calls — pure JSON/string manipulation.
"""

import json
from pathlib import Path
from typing import Any, Dict

REPO_ROOT = Path(__file__).resolve().parents[2]
CHATOPS_CONFIG_PATH = REPO_ROOT / "samples" / "chatops" / "config.json"
SQS_QUEUE_CONFIG_PATH = (
    REPO_ROOT / "configs" / "stacks" / "sqs" / "chatops-slack-queue.json"
)

SQS_STACK_NAME = "chatops-sqs"
LAMBDA_STACK_NAME = "chatops-lambdas"
EVENTBRIDGE_STACK_NAME = "chatops-eventbridge"


def _resolve_placeholders(
    obj: Any, workload: str, env: str, account: str, region: str
) -> Any:
    """Resolve the known template placeholders in a JSON-serializable object."""
    text = json.dumps(obj)
    text = (
        text.replace("{{WORKLOAD_NAME}}", workload)
        .replace("{{DEPLOYMENT_NAMESPACE}}", env)
        .replace("{{AWS_ACCOUNT}}", account)
        .replace("{{AWS_REGION}}", region)
    )
    return json.loads(text)


def load_chatops_config(
    workload: str = "myapp",
    env: str = "dev",
    account: str = "111122223333",
    region: str = "us-east-1",
) -> Dict[str, Any]:
    """Load and placeholder-resolve the chatops sample workload config."""
    raw = json.loads(CHATOPS_CONFIG_PATH.read_text(encoding="utf-8"))
    return _resolve_placeholders(raw, workload, env, account, region)


def find_stack(config: Dict[str, Any], stack_name: str) -> Dict[str, Any]:
    """Return the stack dict with the given name from a resolved workload config."""
    for stack in config["workload"]["stacks"]:
        if stack.get("name") == stack_name:
            return stack
    raise KeyError(f"stack '{stack_name}' not found in chatops config")


def find_lambda(config: Dict[str, Any], lambda_name: str) -> Dict[str, Any]:
    """Return a Lambda resource dict by name from the lambda stack."""
    lambda_stack = find_stack(config, LAMBDA_STACK_NAME)
    for resource in lambda_stack.get("resources", []):
        if resource.get("name") == lambda_name:
            return resource
    raise KeyError(f"lambda '{lambda_name}' not found in chatops config")
