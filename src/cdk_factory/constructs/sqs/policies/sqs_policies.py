"""
Geek Cafe, LLC
Maintainers: Eric Wilson
MIT License.  See Project Root for the license information.
"""

from aws_cdk import aws_iam as iam, aws_sqs as sqs


class SqsPolicies:
    """Centralized SQS Policy Generation"""

    @staticmethod
    def get_tls_policy(queue: sqs.Queue) -> iam.PolicyStatement:
        tls_policy = iam.PolicyStatement(
            actions=[
                "sqs:SendMessage",
                "sqs:ReceiveMessage",
                "sqs:DeleteMessage",
                "sqs:GetQueueAttributes",
                "sqs:GetQueueUrl",
            ],
            effect=iam.Effect.ALLOW,
            principals=[iam.ArnPrincipal("*")],
            resources=[queue.queue_arn],
            conditions={"Bool": {"aws:SecureTransport": "true"}},
        )

        return tls_policy

    @staticmethod
    def get_receive_policy(queue: sqs.Queue) -> iam.PolicyStatement:
        policy = iam.PolicyStatement(
            actions=[
                "sqs:ReceiveMessage",
                "sqs:DeleteMessage",
                "sqs:GetQueueAttributes",
                "sqs:GetQueueUrl",
                "sqs:ChangeMessageVisibility",
            ],
            effect=iam.Effect.ALLOW,
            resources=[queue.queue_arn],
        )

        return policy
