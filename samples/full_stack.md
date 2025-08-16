# AWS CDK (Python) skeleton: ALB + ASG (Docker on EC2) + RDS (private) + NAT + VPC Endpoints

This is a **minimal-but-production‑ready** starting point for your stack:

* Public **ALB**
* Private **Auto Scaling Group** of EC2 instances pulling a **versioned ECR image tag** and running Docker
* **RDS (PostgreSQL)** in private isolated subnets
* **NAT** for egress, **VPC Endpoints** for ECR/S3/SSM/Logs
* Sensible security groups and IAM

> You can paste these files into a fresh `cdk init app --language python` repo.

---

## 1) Project layout

```
my-webapp-infra/
├─ cdk.json
├─ requirements.txt
├─ app.py
└─ my_webapp_infra/
   ├─ __init__.py
   └─ webapp_stack.py
```

---

## 2) `requirements.txt`

```txt
aws-cdk-lib==2.204.0
constructs>=10.0.0,<11.0.0
boto3>=1.34.0
pyyaml
```

---

## 3) `cdk.json`

```json
{
  "app": "python3 app.py",
  "context": {
    "env_name": "dev",
    "domain_name": "example.com",        
    "hosted_zone_id": "",               
    "alb_cert_arn": "",                 
    "ecr_account_id": "123456789012",
    "ecr_region": "us-east-1",
    "ecr_repo": "myapp",
    "ecr_tag": "1.4.7",
    "vpc_cidr": "10.0.0.0/16",
    "nat_gateways": 2,
    "instance_type": "t3.small",
    "desired_capacity": 2,
    "min_capacity": 2,
    "max_capacity": 6,
    "db_name": "appdb",
    "db_instance_class": "t3.micro",
    "db_engine_version": "16"
  }
}
```

> Fill in `alb_cert_arn` (optional, for HTTPS) and `hosted_zone_id` if you want Route 53 records created. Otherwise it will expose the ALB DNS only.

---

## 4) `app.py`

```python
#!/usr/bin/env python3
import os
import aws_cdk as cdk
from my_webapp_infra.webapp_stack import WebAppStack

app = cdk.App()

stack = WebAppStack(
    app,
    "WebAppStack",
    env=cdk.Environment(
        account=os.environ.get("CDK_DEFAULT_ACCOUNT"),
        region=os.environ.get("CDK_DEFAULT_REGION"),
    ),
)

cdk.Tags.of(stack).add("Project", "MyWebApp")
cdk.Tags.of(stack).add("Environment", app.node.try_get_context("env_name") or "dev")

app.synth()
```

---

## 5) `my_webapp_infra/webapp_stack.py`

```python
from typing import Optional
import json
from aws_cdk import (
    Stack,
    Duration,
    CfnOutput,
    aws_ec2 as ec2,
    aws_elasticloadbalancingv2 as elbv2,
    aws_autoscaling as autoscaling,
    aws_iam as iam,
    aws_rds as rds,
    aws_logs as logs,
    aws_route53 as route53,
    aws_route53_targets as targets,
)
from constructs import Construct


class WebAppStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # ---- Context / parameters ----
        ctx = self.node.try_get_context
        env_name = ctx("env_name") or "dev"
        vpc_cidr = ctx("vpc_cidr") or "10.0.0.0/16"
        nat_gateways = int(ctx("nat_gateways") or 2)

        ecr_account = ctx("ecr_account_id")
        ecr_region = ctx("ecr_region") or self.region
        ecr_repo = ctx("ecr_repo") or "myapp"
        ecr_tag = ctx("ecr_tag") or "latest"

        instance_type = ec2.InstanceType.of(
            ec2.InstanceClass[ctx("instance_type").split(".")[0].upper()],
            ec2.InstanceSize[ctx("instance_type").split(".")[1].upper()],
        ) if ctx("instance_type") else ec2.InstanceType("t3.small")

        desired_capacity = int(ctx("desired_capacity") or 2)
        min_capacity = int(ctx("min_capacity") or 2)
        max_capacity = int(ctx("max_capacity") or 6)

        db_name = ctx("db_name") or "appdb"
        db_engine_version = rds.PostgresEngineVersion.of(major_version=ctx("db_engine_version") or "16")
        db_instance_class = ctx("db_instance_class") or "t3.micro"

        domain_name = ctx("domain_name")
        hosted_zone_id = ctx("hosted_zone_id")
        alb_cert_arn = ctx("alb_cert_arn")  # optional

        # ---- VPC ----
        vpc = ec2.Vpc(
            self, "Vpc",
            ip_addresses=ec2.IpAddresses.cidr(vpc_cidr),
            max_azs=2,
            nat_gateways=nat_gateways,
            subnet_configuration=[
                ec2.SubnetConfiguration(name="public", subnet_type=ec2.SubnetType.PUBLIC, cidr_mask=24),
                ec2.SubnetConfiguration(name="app", subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS, cidr_mask=24),
                ec2.SubnetConfiguration(name="db", subnet_type=ec2.SubnetType.PRIVATE_ISOLATED, cidr_mask=24),
            ],
        )

        # ---- VPC Endpoints ----
        # Gateway endpoint for S3 (ECR layers)
        vpc.add_gateway_endpoint("S3Endpoint", service=ec2.GatewayVpcEndpointAwsService.S3)
        # Interface endpoints commonly used by EC2 for mgmt and ECR pulls
        for svc in [
            ec2.InterfaceVpcEndpointAwsService.ECR,
            ec2.InterfaceVpcEndpointAwsService.ECR_DOCKER,
            ec2.InterfaceVpcEndpointAwsService.SECRETS_MANAGER,
            ec2.InterfaceVpcEndpointAwsService.CLOUDWATCH_LOGS,
            ec2.InterfaceVpcEndpointAwsService.EC2_MESSAGES,
            ec2.InterfaceVpcEndpointAwsService.SSM,
            ec2.InterfaceVpcEndpointAwsService.SSM_MESSAGES,
        ]:
            vpc.add_interface_endpoint(f"Endpoint{svc.name}", service=svc)

        # ---- Security Groups ----
        alb_sg = ec2.SecurityGroup(self, "AlbSG", vpc=vpc, description="ALB SG", allow_all_outbound=True)
        alb_sg.add_ingress_rule(ec2.Peer.any_ipv4(), ec2.Port.tcp(80), "HTTP from Internet")
        # 443 will be opened only if a cert is provided

        app_sg = ec2.SecurityGroup(self, "AppSG", vpc=vpc, description="App EC2 SG", allow_all_outbound=True)
        db_sg = ec2.SecurityGroup(self, "DbSG", vpc=vpc, description="DB SG", allow_all_outbound=False)

        # App receives from ALB on 8080
        app_port = ec2.Port.tcp(8080)
        app_sg.add_ingress_rule(alb_sg, app_port, "From ALB to app port")

        # DB allows from App SG only (Postgres 5432)
        db_sg.add_ingress_rule(app_sg, ec2.Port.tcp(5432), "App to DB")

        # ---- RDS ----
        db_subnets = ec2.SubnetSelection(subnet_group_name="db")
        db_instance = rds.DatabaseInstance(
            self, "Rds",
            engine=rds.DatabaseInstanceEngine.postgres(version=db_engine_version),
            vpc=vpc,
            vpc_subnets=db_subnets,
            instance_type=ec2.InstanceType.of(ec2.InstanceClass.BURSTABLE3, ec2.InstanceSize.MICRO)
            if db_instance_class == "t3.micro" else ec2.InstanceType(db_instance_class),
            credentials=rds.Credentials.from_generated_secret(username="appuser", secret_name=f"/{env_name}/db/creds"),
            database_name=db_name,
            multi_az=False,
            allocated_storage=20,
            storage_encrypted=True,
            security_groups=[db_sg],
            deletion_protection=False,
            backup_retention=Duration.days(7),
            cloudwatch_logs_exports=["postgresql"],
            enable_performance_insights=True,
            removal_policy=None,  # keep default (RETAIN) for safety in prod; change as needed
        )

        # ---- IAM role for EC2 ----
        instance_role = iam.Role(
            self, "AppInstanceRole",
            assumed_by=iam.ServicePrincipal("ec2.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("AmazonEC2ContainerRegistryReadOnly"),
                iam.ManagedPolicy.from_aws_managed_policy_name("AmazonSSMManagedInstanceCore"),
                iam.ManagedPolicy.from_aws_managed_policy_name("CloudWatchAgentServerPolicy"),
            ],
        )
        # Allow reading our DB secret
        if db_instance.secret is not None:
            db_instance.secret.grant_read(instance_role)

        # ---- User data (install docker, pull tag, run) ----
        user_data = ec2.UserData.for_linux()
        user_data.add_commands(
            "set -euxo pipefail",
            "dnf -y update",
            "dnf -y install docker jq",
            "systemctl enable --now docker",
            f"ACCOUNT_ID={ecr_account or self.account}",
            f"REGION={ecr_region}",
            f"REPO={ecr_repo}",
            f"TAG={ecr_tag}",
            "aws ecr get-login-password --region $REGION | docker login --username AWS --password-stdin ${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com",
            "docker pull ${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com/${REPO}:${TAG}",
            # Fetch DB creds from Secrets Manager created by RDS
            f"DB_SECRET_ARN={db_instance.secret.secret_arn if db_instance.secret else ''}",
            "if [ -n \"$DB_SECRET_ARN\" ]; then DB_JSON=$(aws secretsmanager get-secret-value --secret-id $DB_SECRET_ARN --query SecretString --output text --region $REGION); fi",
            "if [ -n \"$DB_SECRET_ARN\" ]; then DB_HOST=$(echo $DB_JSON | jq -r .host); DB_USER=$(echo $DB_JSON | jq -r .username); DB_PASS=$(echo $DB_JSON | jq -r .password); DB_NAME=$(echo $DB_JSON | jq -r .dbname); fi",
            # Run container on 8080
            "docker run -d --name myapp -p 8080:8080 "
            "-e DB_HOST=\"$DB_HOST\" -e DB_USER=\"$DB_USER\" -e DB_PASS=\"$DB_PASS\" -e DB_NAME=\"$DB_NAME\" "
            "--restart=always ${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com/${REPO}:${TAG}",
        )

        # ---- Launch Template & ASG ----
        ami = ec2.MachineImage.latest_amazon_linux2023()
        lt = ec2.LaunchTemplate(
            self, "LaunchTemplate",
            machine_image=ami,
            instance_type=instance_type,
            role=instance_role,
            security_group=app_sg,
            user_data=user_data,
            detailed_monitoring=True,
        )

        asg = autoscaling.AutoScalingGroup(
            self, "Asg",
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(subnet_group_name="app"),
            min_capacity=min_capacity,
            max_capacity=max_capacity,
            desired_capacity=desired_capacity,
            launch_template=lt,
            health_check=autoscaling.HealthCheck.elb(grace=Duration.minutes(5)),
        )

        # ---- ALB + Target Group ----
        alb = elbv2.ApplicationLoadBalancer(
            self, "Alb",
            vpc=vpc,
            internet_facing=True,
            vpc_subnets=ec2.SubnetSelection(subnet_group_name="public"),
            security_group=alb_sg,
        )

        # Target group on app port
        tg = elbv2.ApplicationTargetGroup(
            self, "AppTg",
            vpc=vpc,
            port=8080,
            protocol=elbv2.ApplicationProtocol.HTTP,
            target_type=elbv2.TargetType.INSTANCE,
            health_check=elbv2.HealthCheck(
                path="/healthz",
                healthy_http_codes="200-399",
                interval=Duration.seconds(30),
            ),
        )
        tg.add_target(asg)

        # HTTP listener (redirect to HTTPS if cert provided)
        http_listener = alb.add_listener("HttpListener", port=80, open=True)
        if alb_cert_arn:
            https_listener = alb.add_listener(
                "HttpsListener", port=443, open=True,
                certificates=[elbv2.ListenerCertificate.from_arn(alb_cert_arn)],
                default_action=elbv2.ListenerAction.forward([tg])
            )
            http_listener.add_action(
                "RedirectToHttps",
                action=elbv2.ListenerAction.redirect(protocol="HTTPS", port="443", permanent=True)
            )
        else:
            http_listener.add_target_groups("DefaultTg", target_groups=[tg])

        # Optional: Route 53
        if domain_name and hosted_zone_id:
            zone = route53.HostedZone.from_hosted_zone_attributes(
                self, "HostedZone",
                hosted_zone_id=hosted_zone_id,
                zone_name=domain_name,
            )
            route53.ARecord(
                self, "AlbAliasRecord",
                zone=zone,
                target=route53.RecordTarget.from_alias(targets.LoadBalancerTarget(alb)),
            )

        # ---- Outputs ----
        CfnOutput(self, "AlbDnsName", value=alb.load_balancer_dns_name)
        CfnOutput(self, "DbEndpoint", value=db_instance.db_instance_endpoint_address)
```

---

## 6) How to use

```bash
# 1) New repo
mkdir my-webapp-infra && cd my-webapp-infra
cdk init app --language python

# 2) Replace generated files with the ones above
#    (keep the virtualenv that CDK created)

python -m pip install -r requirements.txt

# 3) Bootstrap (per account/region once)
cdk bootstrap aws://$CDK_DEFAULT_ACCOUNT/$CDK_DEFAULT_REGION

# 4) Make sure your ECR has the image:tag referenced in cdk.json
#    e.g., 123456789012.dkr.ecr.us-east-1.amazonaws.com/myapp:1.4.7

# 5) Deploy
cdk deploy WebAppStack
```

### Updating to a new image tag

* Change `context.ecr_tag` in `cdk.json` and `cdk deploy` to roll the ASG with **Instance Refresh** (since the LT user-data changes).
  Alternatively, keep tag constant (e.g., `prod`) and **re-tag** the same digest in ECR—then trigger an **instance refresh** manually (`aws autoscaling start-instance-refresh`).

---

## 7) Notes & options

* **WAF**: Attach AWS WAF to the ALB for extra protection.
* **HTTPS only**: Provide `alb_cert_arn` (same region as ALB) to auto-redirect 80→443.
* **Logs**: Add ALB access logs to S3 and CloudWatch Agent/Fluent Bit for container logs.
* **RDS sizing**: Bump instance/storage and enable Multi‑AZ for prod.
* **SSH-less ops**: Use SSM (already enabled) instead of SSH. Set `blockDeviceMappings`/EBS size on the Launch Template if needed.
* **App port**: Change from 8080 if your container differs; update SG, TG, and user-data run command accordingly.

```
```
