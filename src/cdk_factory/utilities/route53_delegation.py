"""
Cross-Account Route53 DNS Delegation Utility

Automates subdomain delegation between a management account (parent zone)
and a deployment account (child zone). This is a common pattern for
multi-account AWS organizations where:

  1. A management account owns the root domain (e.g., example.com)
  2. Each deployment account owns a subdomain (e.g., dev.example.com)
  3. NS records in the parent zone delegate to the child zone's name servers

Usage as a CLI (called from pipeline steps):

    export TARGET_ACCOUNT_ROLE_ARN="arn:aws:iam::111111111111:role/CrossAccountRole"
    export MANAGEMENT_ACCOUNT_ROLE_ARN="arn:aws:iam::222222222222:role/CrossAccountRole"
    export TARGET_R53_ZONE_NAME="dev.example.com"
    export MGMT_R53_HOSTED_ZONE_ID="Z0123456789"
    python -m cdk_factory.utilities.route53_delegation

Usage as a library:

    from cdk_factory.utilities.route53_delegation import Route53Delegation
    delegation = Route53Delegation()
    delegation.delegate(
        target_role_arn="arn:aws:iam::111...:role/Role",
        management_role_arn="arn:aws:iam::222...:role/Role",
        target_zone_name="dev.example.com",
        management_zone_id="Z0123456789",
    )
"""

import os
import sys
import logging
from typing import List, Optional

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)


class Route53Delegation:
    """Cross-account Route53 DNS delegation."""

    def _get_client(self, service: str, role_arn: Optional[str] = None):
        """Get a boto3 client, optionally assuming a cross-account role."""
        if role_arn:
            sts = boto3.client("sts")
            creds = sts.assume_role(
                RoleArn=role_arn,
                RoleSessionName=f"route53-delegation-{service}",
            )["Credentials"]
            return boto3.client(
                service,
                aws_access_key_id=creds["AccessKeyId"],
                aws_secret_access_key=creds["SecretAccessKey"],
                aws_session_token=creds["SessionToken"],
            )
        return boto3.client(service)

    def get_hosted_zone_id_by_name(
        self, zone_name: str, role_arn: Optional[str] = None
    ) -> Optional[str]:
        """Look up a hosted zone ID by its DNS name."""
        client = self._get_client("route53", role_arn)
        zones = client.list_hosted_zones_by_name(DNSName=zone_name)["HostedZones"]
        for zone in zones:
            if zone["Name"] == zone_name.rstrip(".") + ".":
                return zone["Id"].split("/")[-1]
        return None

    def get_ns_records(
        self, hosted_zone_id: str, role_arn: Optional[str] = None
    ) -> List[str]:
        """Get the NS records for a hosted zone."""
        client = self._get_client("route53", role_arn)
        records = client.list_resource_record_sets(HostedZoneId=hosted_zone_id)
        ns_records = []
        for record_set in records["ResourceRecordSets"]:
            if record_set["Type"] == "NS":
                for record in record_set["ResourceRecords"]:
                    ns_records.append(record["Value"])
        return ns_records

    def upsert_ns_records(
        self,
        hosted_zone_id: str,
        record_name: str,
        ns_records: List[str],
        ttl: int = 300,
        role_arn: Optional[str] = None,
    ) -> None:
        """Create or update NS delegation records in a hosted zone."""
        client = self._get_client("route53", role_arn)
        try:
            client.change_resource_record_sets(
                HostedZoneId=hosted_zone_id,
                ChangeBatch={
                    "Changes": [
                        {
                            "Action": "UPSERT",
                            "ResourceRecordSet": {
                                "Name": record_name,
                                "Type": "NS",
                                "TTL": ttl,
                                "ResourceRecords": [{"Value": ns} for ns in ns_records],
                            },
                        }
                    ]
                },
            )
            logger.info(f"NS records upserted for {record_name}")
        except ClientError as e:
            logger.error(f"Failed to upsert NS records for {record_name}: {e}")
            raise

    def get_ssm_parameter(
        self, parameter_name: str, role_arn: Optional[str] = None
    ) -> Optional[str]:
        """Read an SSM parameter, optionally via cross-account role."""
        client = self._get_client("ssm", role_arn)
        try:
            return client.get_parameter(Name=parameter_name, WithDecryption=True)[
                "Parameter"
            ]["Value"]
        except ClientError as e:
            if e.response["Error"]["Code"] == "ParameterNotFound":
                logger.warning(f"SSM parameter not found: {parameter_name}")
                return None
            raise

    def delegate(
        self,
        target_role_arn: str,
        management_role_arn: str,
        target_zone_name: str,
        management_zone_id: str,
        target_zone_id: Optional[str] = None,
        target_zone_id_ssm_parameter: Optional[str] = None,
        ttl: int = 300,
    ) -> None:
        """
        Perform cross-account DNS delegation.

        1. Resolve the target hosted zone ID (from arg, SSM, or DNS lookup)
        2. Get NS records from the target zone (deployment account)
        3. Upsert NS delegation records in the management zone (management account)

        Args:
            target_role_arn: IAM role ARN to assume in the deployment account
            management_role_arn: IAM role ARN to assume in the management account
            target_zone_name: DNS name of the child zone (e.g., dev.example.com)
            management_zone_id: Hosted zone ID of the parent zone in the management account
            target_zone_id: Optional explicit hosted zone ID for the child zone
            target_zone_id_ssm_parameter: Optional SSM parameter path to look up the child zone ID
            ttl: TTL for the NS delegation records (default 300)
        """
        # Step 1: Resolve target hosted zone ID
        ssm_zone_id = None
        if target_zone_id_ssm_parameter:
            logger.info(
                f"Looking up target zone ID from SSM: {target_zone_id_ssm_parameter}"
            )
            ssm_zone_id = self.get_ssm_parameter(
                target_zone_id_ssm_parameter, role_arn=target_role_arn
            )

        if target_zone_id and ssm_zone_id:
            if target_zone_id != ssm_zone_id:
                raise RuntimeError(
                    f"Conflict: TARGET_HOSTED_ZONE_ID='{target_zone_id}' does not match "
                    f"SSM parameter '{target_zone_id_ssm_parameter}' value='{ssm_zone_id}'. "
                    "Provide only one, or ensure they agree."
                )
            logger.info(
                f"Both target_zone_id and SSM parameter provided and agree: {target_zone_id}"
            )
        elif not target_zone_id and ssm_zone_id:
            target_zone_id = ssm_zone_id

        if not target_zone_id:
            logger.info(f"Looking up target zone ID by name: {target_zone_name}")
            target_zone_id = self.get_hosted_zone_id_by_name(
                target_zone_name, role_arn=target_role_arn
            )

        if not target_zone_id:
            raise RuntimeError(
                f"Unable to resolve hosted zone ID for '{target_zone_name}'. "
                "Provide target_zone_id, target_zone_id_ssm_parameter, or ensure "
                "the zone exists in the target account."
            )

        logger.info(f"Target zone: {target_zone_name} ({target_zone_id})")

        # Step 2: Get NS records from the target zone
        ns_records = self.get_ns_records(target_zone_id, role_arn=target_role_arn)
        if not ns_records:
            raise RuntimeError(
                f"No NS records found for zone {target_zone_id}. "
                "The hosted zone may not exist or may not have NS records."
            )
        logger.info(f"Target NS records: {ns_records}")

        # Step 3: Upsert NS delegation in the management zone
        logger.info(
            f"Delegating {target_zone_name} in management zone {management_zone_id}"
        )
        self.upsert_ns_records(
            hosted_zone_id=management_zone_id,
            record_name=target_zone_name,
            ns_records=ns_records,
            ttl=ttl,
            role_arn=management_role_arn,
        )
        logger.info(f"Delegation complete: {target_zone_name} → {management_zone_id}")


def main():
    """CLI entry point for pipeline steps."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    target_role_arn = os.getenv("TARGET_ACCOUNT_ROLE_ARN")
    management_role_arn = os.getenv("MANAGEMENT_ACCOUNT_ROLE_ARN")
    target_zone_name = os.getenv("TARGET_R53_ZONE_NAME")
    management_zone_id = os.getenv("MGMT_R53_HOSTED_ZONE_ID")
    target_zone_id = os.getenv("TARGET_HOSTED_ZONE_ID")
    target_zone_id_ssm = os.getenv("TARGET_HOSTED_ZONE_ID_SSM_PARAMETER_NAME")

    if not target_role_arn:
        print("ERROR: TARGET_ACCOUNT_ROLE_ARN is required", file=sys.stderr)
        sys.exit(1)
    if not management_role_arn:
        print("ERROR: MANAGEMENT_ACCOUNT_ROLE_ARN is required", file=sys.stderr)
        sys.exit(1)
    if not target_zone_name:
        print("ERROR: TARGET_R53_ZONE_NAME is required", file=sys.stderr)
        sys.exit(1)
    if not management_zone_id:
        print("ERROR: MGMT_R53_HOSTED_ZONE_ID is required", file=sys.stderr)
        sys.exit(1)

    # Normalize "None" string to actual None
    if target_zone_id and target_zone_id.lower() == "none":
        target_zone_id = None

    delegation = Route53Delegation()
    delegation.delegate(
        target_role_arn=target_role_arn,
        management_role_arn=management_role_arn,
        target_zone_name=target_zone_name,
        management_zone_id=management_zone_id,
        target_zone_id=target_zone_id,
        target_zone_id_ssm_parameter=target_zone_id_ssm,
    )


if __name__ == "__main__":
    main()
