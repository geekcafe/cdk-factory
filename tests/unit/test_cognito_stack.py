import pytest
from aws_cdk import App
from aws_cdk import aws_cognito as cognito
from cdk_factory.stack_library.cognito.cognito_stack import CognitoStack
from cdk_factory.configurations.resources.cognito import CognitoConfig
from cdk_factory.configurations.stack import StackConfig
from cdk_factory.configurations.deployment import DeploymentConfig
from cdk_factory.workload.workload_factory import WorkloadConfig


def test_cognito_stack_minimal():
    app = App()
    dummy_workload = WorkloadConfig(
        {
            "workload": {"name": "dummy-workload", "devops": {"name": "dummy-devops"}},
        }
    )
    stack_config = StackConfig(
        {
            "cognito": {
                "user_pool_name": "TestUserPool",
                "self_sign_up_enabled": True,
                "sign_in_aliases": {"email": True},
                "password_policy": {"min_length": 10},
            }
        },
        workload=dummy_workload.dictionary,
    )

    dc = DeploymentConfig(
        workload=dummy_workload.dictionary,
        deployment={"name": "dummy-deployment"},
    )

    stack = CognitoStack(app, "TestCognitoStack")
    stack.build(stack_config, dc, dummy_workload)

    resources = [c for c in stack.node.children if isinstance(c, cognito.UserPool)]
    assert len(resources) == 1
    user_pool: cognito.UserPool = resources[0]
    assert user_pool.stack.cognito_config.user_pool_name == "TestUserPool"
    assert user_pool.stack.cognito_config.sign_in_aliases.get("email") is True
    assert user_pool.stack.cognito_config.self_sign_up_enabled is True
    assert user_pool.stack.cognito_config.password_policy.get("min_length") == 10


def test_cognito_stack_full_config():
    app = App()
    dummy_workload = WorkloadConfig(
        {
            "workload": {"name": "dummy-workload", "devops": {"name": "dummy-devops"}},
        }
    )
    stack_config = StackConfig(
        {
            "cognito": {
                "user_pool_name": "FullUserPool",
                "self_sign_up_enabled": False,
                "sign_in_case_sensitive": False,
                "sign_in_aliases": {
                    "username": True,
                    "email": True,
                    "phone": True,
                    "preferred_username": True,
                },
                "auto_verify": {"email": True, "phone": True},
                "password_policy": {
                    "min_length": 12,
                    "require_uppercase": True,
                    "require_lowercase": True,
                    "require_digits": True,
                    "require_symbols": True,
                },
                "mfa": "OPTIONAL",
                "mfa_second_factor": {"sms": True, "otp": True},
                "account_recovery": "EMAIL_ONLY",
                "deletion_protection": True,
                "ssm": {
                    "user_pool_arn_path": "dev/workload/cognito/user-pool-arn",
                    "user_pool_id_path": "dev/workload/cognito/user-pool-id",
                    "user_pool_name_path": "dev/workload/cognito/user-pool-name",
                },
            }
        },
        workload=dummy_workload.dictionary,
    )
    deployment = DeploymentConfig(
        workload=dummy_workload.dictionary,
        deployment={"name": "dummy-deployment"},
    )
    workload = dummy_workload

    stack = CognitoStack(app, "FullCognitoStack")
    stack.build(stack_config, deployment, workload)

    resources = [c for c in stack.node.children if isinstance(c, cognito.UserPool)]
    assert len(resources) == 1
    user_pool = resources[0]
    assert user_pool.stack.cognito_config.user_pool_name == "FullUserPool"
    assert user_pool.stack.cognito_config.sign_in_aliases.get("email") is True
    assert user_pool.stack.cognito_config.self_sign_up_enabled is False
    assert user_pool.stack.cognito_config.password_policy.get("min_length") == 12
    assert user_pool.stack.cognito_config.mfa == "OPTIONAL"
    assert user_pool.stack.cognito_config.mfa_second_factor.get("sms") is True
    assert user_pool.stack.cognito_config.mfa_second_factor.get("otp") is True
    assert user_pool.stack.cognito_config.account_recovery == "EMAIL_ONLY"
    assert user_pool.stack.cognito_config.deletion_protection is True
    assert user_pool.stack.cognito_config.device_tracking is None
    assert user_pool.stack.cognito_config.email is None
    assert user_pool.stack.cognito_config.enable_sms_role is None
