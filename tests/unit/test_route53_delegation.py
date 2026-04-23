"""
Unit tests for Route53Delegation utility with mocked boto3 calls.
"""

import pytest
from unittest.mock import patch, MagicMock

from cdk_factory.utilities.route53_delegation import Route53Delegation


class TestRoute53Delegation:
    """Test Route53Delegation with mocked boto3."""

    @patch.object(Route53Delegation, "_get_client")
    def test_delegate_happy_path(self, mock_get_client):
        """Verify full delegation flow: resolve zone → get NS → upsert."""
        mock_r53 = MagicMock()
        mock_r53.list_hosted_zones_by_name.return_value = {
            "HostedZones": [{"Name": "dev.example.com.", "Id": "/hostedzone/Z111"}]
        }
        mock_r53.list_resource_record_sets.return_value = {
            "ResourceRecordSets": [
                {
                    "Type": "NS",
                    "ResourceRecords": [
                        {"Value": "ns-1.awsdns.com."},
                        {"Value": "ns-2.awsdns.com."},
                    ],
                }
            ]
        }
        mock_r53.change_resource_record_sets.return_value = {}

        mock_get_client.return_value = mock_r53

        delegation = Route53Delegation()
        delegation.delegate(
            target_role_arn="arn:aws:iam::111:role/Role",
            management_role_arn="arn:aws:iam::222:role/Role",
            target_zone_name="dev.example.com",
            management_zone_id="Z222",
        )

        # Verify zone lookup was called
        mock_r53.list_hosted_zones_by_name.assert_called_once()
        # Verify NS records were fetched
        mock_r53.list_resource_record_sets.assert_called_once()
        # Verify upsert was called
        mock_r53.change_resource_record_sets.assert_called_once()

    @patch.object(Route53Delegation, "_get_client")
    def test_delegate_zone_not_found(self, mock_get_client):
        """Verify RuntimeError when zone cannot be resolved."""
        mock_r53 = MagicMock()
        mock_r53.list_hosted_zones_by_name.return_value = {"HostedZones": []}
        mock_get_client.return_value = mock_r53

        delegation = Route53Delegation()
        with pytest.raises(RuntimeError, match="Unable to resolve hosted zone ID"):
            delegation.delegate(
                target_role_arn="arn:aws:iam::111:role/Role",
                management_role_arn="arn:aws:iam::222:role/Role",
                target_zone_name="missing.example.com",
                management_zone_id="Z222",
            )

    @patch.object(Route53Delegation, "_get_client")
    def test_delegate_no_ns_records(self, mock_get_client):
        """Verify RuntimeError when no NS records found."""
        mock_r53 = MagicMock()
        mock_r53.list_hosted_zones_by_name.return_value = {
            "HostedZones": [{"Name": "dev.example.com.", "Id": "/hostedzone/Z111"}]
        }
        mock_r53.list_resource_record_sets.return_value = {
            "ResourceRecordSets": [
                {"Type": "A", "ResourceRecords": [{"Value": "1.2.3.4"}]}
            ]
        }
        mock_get_client.return_value = mock_r53

        delegation = Route53Delegation()
        with pytest.raises(RuntimeError, match="No NS records found"):
            delegation.delegate(
                target_role_arn="arn:aws:iam::111:role/Role",
                management_role_arn="arn:aws:iam::222:role/Role",
                target_zone_name="dev.example.com",
                management_zone_id="Z222",
            )

    @patch.object(Route53Delegation, "_get_client")
    def test_get_hosted_zone_id_found(self, mock_get_client):
        """Verify correct zone ID is returned for matching zone."""
        mock_r53 = MagicMock()
        mock_r53.list_hosted_zones_by_name.return_value = {
            "HostedZones": [{"Name": "dev.example.com.", "Id": "/hostedzone/Z111"}]
        }
        mock_get_client.return_value = mock_r53

        delegation = Route53Delegation()
        zone_id = delegation.get_hosted_zone_id_by_name("dev.example.com")
        assert zone_id == "Z111"

    @patch.object(Route53Delegation, "_get_client")
    def test_get_hosted_zone_id_not_found(self, mock_get_client):
        """Verify None is returned when zone does not exist."""
        mock_r53 = MagicMock()
        mock_r53.list_hosted_zones_by_name.return_value = {"HostedZones": []}
        mock_get_client.return_value = mock_r53

        delegation = Route53Delegation()
        zone_id = delegation.get_hosted_zone_id_by_name("missing.example.com")
        assert zone_id is None

    @patch.object(Route53Delegation, "_get_client")
    def test_delegate_with_ssm_parameter(self, mock_get_client):
        """Verify zone ID is read from SSM before DNS lookup."""
        mock_ssm_client = MagicMock()
        mock_ssm_client.get_parameter.return_value = {"Parameter": {"Value": "Z333"}}

        mock_r53 = MagicMock()
        mock_r53.list_resource_record_sets.return_value = {
            "ResourceRecordSets": [
                {
                    "Type": "NS",
                    "ResourceRecords": [{"Value": "ns-1.awsdns.com."}],
                }
            ]
        }
        mock_r53.change_resource_record_sets.return_value = {}

        def side_effect(service, role_arn=None):
            if service == "ssm":
                return mock_ssm_client
            return mock_r53

        mock_get_client.side_effect = side_effect

        delegation = Route53Delegation()
        delegation.delegate(
            target_role_arn="arn:aws:iam::111:role/Role",
            management_role_arn="arn:aws:iam::222:role/Role",
            target_zone_name="dev.example.com",
            management_zone_id="Z222",
            target_zone_id_ssm_parameter="/my/zone/id",
        )

        # SSM was called to get zone ID
        mock_ssm_client.get_parameter.assert_called_once_with(
            Name="/my/zone/id", WithDecryption=True
        )
        # NS records were fetched using the SSM-resolved zone ID
        mock_r53.list_resource_record_sets.assert_called_once_with(HostedZoneId="Z333")
        # Zone name lookup was NOT called (SSM provided the ID)
        mock_r53.list_hosted_zones_by_name.assert_not_called()

    @patch.object(Route53Delegation, "_get_client")
    def test_delegate_conflict_between_explicit_and_ssm(self, mock_get_client):
        """Verify RuntimeError when explicit zone ID and SSM value disagree."""
        mock_ssm_client = MagicMock()
        mock_ssm_client.get_parameter.return_value = {
            "Parameter": {"Value": "Z999-FROM-SSM"}
        }

        mock_r53 = MagicMock()

        def side_effect(service, role_arn=None):
            if service == "ssm":
                return mock_ssm_client
            return mock_r53

        mock_get_client.side_effect = side_effect

        delegation = Route53Delegation()
        with pytest.raises(RuntimeError, match="Conflict"):
            delegation.delegate(
                target_role_arn="arn:aws:iam::111:role/Role",
                management_role_arn="arn:aws:iam::222:role/Role",
                target_zone_name="dev.example.com",
                management_zone_id="Z222",
                target_zone_id="Z111-EXPLICIT",
                target_zone_id_ssm_parameter="/my/zone/id",
            )

    @patch.object(Route53Delegation, "_get_client")
    def test_delegate_explicit_and_ssm_agree(self, mock_get_client):
        """Verify no error when explicit zone ID and SSM value match."""
        mock_ssm_client = MagicMock()
        mock_ssm_client.get_parameter.return_value = {"Parameter": {"Value": "Z111"}}

        mock_r53 = MagicMock()
        mock_r53.list_resource_record_sets.return_value = {
            "ResourceRecordSets": [
                {
                    "Type": "NS",
                    "ResourceRecords": [{"Value": "ns-1.awsdns.com."}],
                }
            ]
        }
        mock_r53.change_resource_record_sets.return_value = {}

        def side_effect(service, role_arn=None):
            if service == "ssm":
                return mock_ssm_client
            return mock_r53

        mock_get_client.side_effect = side_effect

        delegation = Route53Delegation()
        delegation.delegate(
            target_role_arn="arn:aws:iam::111:role/Role",
            management_role_arn="arn:aws:iam::222:role/Role",
            target_zone_name="dev.example.com",
            management_zone_id="Z222",
            target_zone_id="Z111",
            target_zone_id_ssm_parameter="/my/zone/id",
        )

        # Both were resolved, no error raised, delegation proceeded
        mock_r53.change_resource_record_sets.assert_called_once()
