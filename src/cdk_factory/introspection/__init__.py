"""Introspection modules for CDK configuration parsing and service discovery.

This package provides reusable capabilities for parsing CDK Lambda resource
configuration files, building service dependency graphs, and resolving live
AWS resources. Any project using cdk-factory can consume these capabilities.
"""

from cdk_factory.introspection.aws_introspector import (
    AwsCredentialError,
    AwsIntrospector,
    ResolvedLambda,
    select_best_log_group,
)
from cdk_factory.introspection.config_parser import (
    LambdaConfig,
    QueueConfig,
    parse_lambda_configs,
    resolve_template_variables,
)
from cdk_factory.introspection.drift_detector import (
    DriftReport,
    detect_drift,
)
from cdk_factory.introspection.service_graph import (
    QueueEdge,
    ServiceGraph,
    ServiceNode,
    build_service_graph,
)

__all__ = [
    "AwsCredentialError",
    "AwsIntrospector",
    "ResolvedLambda",
    "select_best_log_group",
    "LambdaConfig",
    "QueueConfig",
    "parse_lambda_configs",
    "resolve_template_variables",
    "DriftReport",
    "detect_drift",
    "ServiceNode",
    "QueueEdge",
    "ServiceGraph",
    "build_service_graph",
]
