"""
Geek Cafe, LLC
Maintainers: Eric Wilson
MIT License.  See Project Root for the license information.
"""

from typing import List

from aws_cdk import aws_iam as iam


from cdk_factory.configurations.pipeline import PipelineConfig
from cdk_factory.configurations.workload import WorkloadConfig
from cdk_factory.configurations.deployment import DeploymentConfig


class CodeBuildPolicy:
    """Code Build Policy Information"""

    def code_build_policies(
        self, pipeline: PipelineConfig, code_artifact_access_role: iam.Role
    ) -> List[iam.PolicyStatement]:
        """
        Generate the Code Build Polices
        """
        workload: WorkloadConfig = WorkloadConfig(pipeline.workload)
        code_build_policy = []

        if workload.management and workload.management.cross_account_role_arn:
            code_build_policy.append(
                # policy assumption on management account
                iam.PolicyStatement(
                    effect=iam.Effect.ALLOW,
                    actions=["sts:AssumeRole"],
                    resources=[workload.management.cross_account_role_arn],
                )
            )

        deployment: DeploymentConfig
        for deployment in pipeline.deployments:
            # target accounts
            if deployment.enabled:
                # CDK deploy role
                cdk_role_name = f"cdk-hnb659fds-deploy-role-{deployment.account}-{deployment.region}"
                policy = iam.PolicyStatement(
                    effect=iam.Effect.ALLOW,
                    actions=["sts:AssumeRole"],
                    resources=[
                        f"arn:aws:iam::{deployment.account}:role/{cdk_role_name}"
                    ],
                )
                code_build_policy.append(policy)

        # Cross-account role ARNs declared in the pipeline config
        # (e.g., for DNS delegation, SSM lookups in target accounts)
        for role_arn in pipeline.cross_account_role_arns:
            code_build_policy.append(
                iam.PolicyStatement(
                    effect=iam.Effect.ALLOW,
                    actions=["sts:AssumeRole"],
                    resources=[role_arn],
                )
            )

        # add the ability to read and write to ecr

        policy = iam.PolicyStatement(
            effect=iam.Effect.ALLOW,
            actions=["ecr:*"],
            resources=[
                (
                    "arn:aws:ecr:"
                    f"{workload.devops.region}:"
                    f"{workload.devops.account}:repository/*"
                )
            ],
        )
        code_build_policy.append(policy)

        policy = iam.PolicyStatement(
            sid="ElasticContainerRegistryPolicy",
            actions=[
                "ecr:BatchCheckLayerAvailability",
                "ecr:CompleteLayerUpload",
                "ecr:GetAuthorizationToken",
                "ecr:InitiateLayerUpload",
                "ecr:PutImage",
                "ecr:UploadLayerPart",
            ],
            resources=["*"],
            effect=iam.Effect.ALLOW,
        )
        code_build_policy.append(policy)

        policy = iam.PolicyStatement(
            sid="SSMPolicy",
            effect=iam.Effect.ALLOW,
            actions=["ssm:*"],
            resources=["*"],
        )
        code_build_policy.append(policy)

        policy = iam.PolicyStatement(
            sid="CodeArtifactPolicy",
            effect=iam.Effect.ALLOW,
            actions=[
                "codeartifact:GetAuthorizationToken",
                "codeartifact:GetRepositoryEndpoint",
                "codeartifact:ReadFromRepository",
                "codeartifact:PublishPackageVersion",
                "codeartifact:PutPackageMetadata",
                "sts:GetServiceBearerToken",
            ],
            resources=["*"],
        )
        code_build_policy.append(policy)

        # allow it to assume the code artifact role
        # which it will use to pass credentials to the docker build
        assume_codeartifact_role_policy = iam.PolicyStatement(
            effect=iam.Effect.ALLOW,
            actions=["sts:AssumeRole"],
            resources=[f"{code_artifact_access_role.role_arn}"],
        )
        code_build_policy.append(assume_codeartifact_role_policy)

        # add ec2 policy
        policy = iam.PolicyStatement(
            sid="EC2Policy",
            effect=iam.Effect.ALLOW,
            actions=["ec2:*"],
            resources=["*"],
        )
        code_build_policy.append(policy)

        # S3 permissions for deployment scripts (error pages, static assets, etc.)
        # TODO: tighten security
        s3_policy = iam.PolicyStatement(
            sid="S3Policy",
            actions=[
                "s3:*",
            ],
            resources=["*"],
            effect=iam.Effect.ALLOW,
        )
        code_build_policy.append(s3_policy)

        # TODO: allow users to add their own policies

        # Cross-account Lambda updater: allow CodeBuild to assume the
        # DevOpsLambdaDeployRole (or legacy DevOpsCrossAccountAccessRole)
        # in any target account.
        # The lambda_image_updater reads docker-images.json which may
        # target deployment accounts not listed in the pipeline config.
        # The target role's trust policy controls who can actually assume it.
        cross_account_lambda_updater_policy = iam.PolicyStatement(
            sid="AssumeRoleLambdaUpdater",
            effect=iam.Effect.ALLOW,
            actions=["sts:AssumeRole"],
            resources=[
                "arn:aws:iam::*:role/DevOpsLambdaDeployRole",
                "arn:aws:iam::*:role/DevOpsCrossAccountAccessRole",
            ],
        )
        code_build_policy.append(cross_account_lambda_updater_policy)

        # AppSync Events api-key seeder (post-deploy step
        # `cdk_factory.utilities.appsync_key_seeder`). OPT-IN ONLY: these two
        # statements are added only when the pipeline config sets
        # `enable_appsync_key_seeder: true`. Default OFF, so pipelines that do
        # not run the seeder get no additional AppSync/Secrets Manager
        # permissions on the shared CodeBuild role — a consumer opts into its
        # own grant. Scope: list/create/get the realtime AppSync Events publish
        # key, and read/write the single realtime api-key secret the publisher
        # reads (trailing `*` covers the Secrets Manager random-suffix).
        #
        # NOTE on the AppSync Resource being "*": appsync:ListApiKeys /
        # CreateApiKey / GetApiKey do NOT support resource-level scoping — their
        # resource-type column is empty in the AWS Service Authorization
        # Reference for AppSync, so the only Resource value that matches them is
        # "*". A scoped ARN like `apis/*` (or the Events `/v1/apis/<id>/apikeys`
        # shape IAM evaluates against) never matches these actions and yields a
        # misleading "no identity-based policy allows the action" denial even
        # when the statement is present. The grant is kept safe by pairing the
        # unavoidable "*" resource with this narrow, single-purpose key-mgmt
        # action set on an opt-in post-deploy seeder role.
        if pipeline.enable_appsync_key_seeder:
            appsync_key_seeder_policy = iam.PolicyStatement(
                sid="AppSyncEventsApiKeySeeder",
                effect=iam.Effect.ALLOW,
                actions=[
                    "appsync:ListApiKeys",
                    "appsync:CreateApiKey",
                    "appsync:GetApiKey",
                ],
                # These actions are not resource-scopable (see NOTE above); "*"
                # is the only Resource that matches them.
                resources=["*"],
            )
            code_build_policy.append(appsync_key_seeder_policy)

            realtime_api_key_secret_policy = iam.PolicyStatement(
                sid="RealtimeApiKeySecretSeeder",
                effect=iam.Effect.ALLOW,
                actions=[
                    "secretsmanager:GetSecretValue",
                    "secretsmanager:PutSecretValue",
                ],
                resources=[
                    (
                        "arn:aws:secretsmanager:"
                        f"{workload.devops.region}:"
                        f"{workload.devops.account}:secret:realtime/appsync-events/api-key*"
                    )
                ],
            )
            code_build_policy.append(realtime_api_key_secret_policy)

        return code_build_policy
