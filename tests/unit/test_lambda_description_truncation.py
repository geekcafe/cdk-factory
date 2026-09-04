"""
Unit tests for LambdaFunctionConfig.description truncation.

AWS Lambda limits the function description to 256 characters. The config
property truncates longer values (with an ellipsis) so a slightly-too-long
description never fails a deployment.
"""

from cdk_factory.configurations.resources.lambda_function import LambdaFunctionConfig


MAX_LENGTH = 256


def test_short_description_is_unchanged():
    desc = "A perfectly reasonable description."
    cfg = LambdaFunctionConfig({"name": "fn", "description": desc})
    assert cfg.description == desc


def test_description_at_limit_is_unchanged():
    desc = "x" * MAX_LENGTH
    cfg = LambdaFunctionConfig({"name": "fn", "description": desc})
    assert cfg.description == desc
    assert len(cfg.description) == MAX_LENGTH


def test_description_over_limit_is_truncated_with_ellipsis():
    desc = "y" * (MAX_LENGTH + 50)
    cfg = LambdaFunctionConfig({"name": "fn", "description": desc})
    result = cfg.description
    assert len(result) == MAX_LENGTH
    assert result.endswith("...")
    # The prefix is preserved up to the ellipsis budget.
    assert result[: MAX_LENGTH - 3] == "y" * (MAX_LENGTH - 3)


def test_real_world_261_char_description_is_truncated():
    # The original failing description was 261 characters.
    desc = (
        "Analysis Workflow: On-demand Package Generation - SQS consumer that "
        "builds a downloadable package for an execution that has none (e.g. "
        "legacy data cleaning runs). Runs the same packaging strategy as the "
        "workflow packaging step and records the generation status."
    )
    assert len(desc) > MAX_LENGTH  # sanity: this is the over-limit case
    cfg = LambdaFunctionConfig({"name": "fn", "description": desc})
    assert len(cfg.description) == MAX_LENGTH
    assert cfg.description.endswith("...")


def test_missing_description_falls_back_to_default():
    cfg = LambdaFunctionConfig({"name": "my-fn"})
    assert cfg.description == "Lambda Function for my-fn"
