import os
import datetime
import aws_cdk
import cdk_nag
from aws_cdk import (
    NestedStack,
    Stack,
)
from aws_lambda_powertools import Logger
from constructs import Construct, IConstruct
from cdk_factory.utilities.git_utilities import GitUtilities

logger = Logger(__name__)


class StackBase(Stack):
    """Standardized a Base Stack"""

    def __init__(
        self, scope: Construct | None = None, id: str | None = None, **kwargs
    ) -> None:
        super().__init__(scope, id, **kwargs)

        StackStandards.set_standards(scope=self)


class NestedStackBase(NestedStack):
    """Use Nested Stacks"""

    def __init__(
        self,
        scope: Construct,  # | None = None,
        id: str,  # | None = None,  # pylint: disable=w0622
        **kwargs,
    ) -> None:
        super().__init__(scope, id, **kwargs)

        StackStandards.set_standards(scope=self)


class StackStandards:
    """Stack Standards"""

    @staticmethod
    def set_standards(scope: Construct):
        aws_cdk.Aspects.of(scope).add(cdk_nag.AwsSolutionsChecks(verbose=True))
        company_name = os.getenv("COMPANY_NAME", "NA")
        workload_name = os.getenv("WORKLOAD_NAME", "NA")
        aws_cdk.Tags.of(scope).add("Company", company_name)
        aws_cdk.Tags.of(scope).add("WorkloadName", workload_name)

        version = os.getenv("VERSION", GitUtilities.get_version_tag())
        aws_cdk.Tags.of(scope).add("ApplicationVersion", version)
        git_hash = GitUtilities.get_git_commit_hash()
        if git_hash:
            aws_cdk.Tags.of(scope).add("ApplicationGitHash", git_hash)
        
        # Add CDK Factory version for tracking and debugging
        from cdk_factory.version import __version__
        aws_cdk.Tags.of(scope).add("CdkFactoryVersion", __version__)
        
        aws_cdk.Tags.of(scope).add(
            "DeploymentDateUTC", str(datetime.datetime.now(datetime.UTC))
        )

    @staticmethod
    def nag_auto_resources(scope: Construct):
        """NAG Resources Suppression"""

        StackStandards.nag_auto_resource_by_id(
            scope, "BucketNotificationsHandler050a0587b7544547bf325f094a3db834"
        )

    @staticmethod
    def nag_auto_resource_by_id(scope: Construct, resource_id: str) -> None:
        """NAG Resources Suppression"""
        try:
            # StackStandards.list_node_ids(scope)
            construct = StackStandards.find_construct(
                scope=scope, find_node_id=resource_id
            )
            if not construct:
                return
            cdk_nag.NagSuppressions.add_resource_suppressions(
                construct=construct,  # scope.node.find_child(id=resource_id),
                suppressions=[
                    cdk_nag.NagPackSuppression(
                        id="AwsSolutions-IAM4",
                        reason="The CDK Internal resource does not need nag rules.",
                        applies_to=[
                            "Policy::arn:<AWS::Partition>:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
                        ],
                    ),
                    cdk_nag.NagPackSuppression(
                        id="AwsSolutions-IAM5",
                        reason="The CDK Internal resource does not need nag rules.",
                        applies_to=["Resource::*"],
                    ),
                ],
                apply_to_children=True,
            )
        except Exception as e:  # pylint: disable=w0718
            logger.warning(
                {
                    "warning": "An attempt to create a nag on a resource failed.  Possible reason.  This resource is not being deployed.",
                    "resource_id": resource_id,
                    "exception": str(e),
                }
            )

    @staticmethod
    def list_node_ids(scope: Construct):
        """
        Recursively list all node IDs in a given scope.

        :param scope: The root construct scope to start the traversal.
        :return: A list of node IDs.
        """
        node_ids = []

        def _recursive_list_node_ids(construct: Construct | IConstruct):
            node_ids.append(construct.node.id)
            for child in construct.node.children:
                _recursive_list_node_ids(child)

        _recursive_list_node_ids(scope)

        return node_ids

    @staticmethod
    def find_construct(scope: Construct, find_node_id: str):
        """
        Recursively list all node IDs in a given scope.

        :param scope: The root construct scope to start the traversal.
        :return: A list of node IDs.
        """

        def _recursive_list_node_ids(
            construct: Construct | IConstruct,
        ) -> Construct | IConstruct | None:
            node_id = construct.node.id

            if find_node_id.lower() in str(node_id).lower():
                return construct

            for child in construct.node.children:
                result = _recursive_list_node_ids(child)
                if result:
                    return result

            return None

        result = _recursive_list_node_ids(scope)

        return result
