import os
import unittest
from pathlib import Path

from cdk_factory.configurations.cdk_config import CdkConfig


class JsonUtilityTests(unittest.TestCase):
    """Json Utility Tests"""

    def test_json_utility_loading(self):
        """Test Json Loading"""
        website_config_path = os.path.join(
            Path(__file__).parent,
            "files",
        )

        cdk_context = {
            "AccountNumber": "123456789",
            "AccountName": "My Account",
            "AccountRegion": "us-east-1",
            "CodeRepoName": "company/my-repo-name",
            "CodeRepoConnectorArn": "aws::repo_arn",
            "SiteBucketName": "my-bucket",
            "HostedZoneId": "zone1234",
            "HostedZoneName": "dev.example.com",
        }
        cdk_config: CdkConfig = CdkConfig(
            config_path="website_config.json",
            cdk_context=cdk_context,
            runtime_directory=website_config_path,
        )
        self.assertIsNotNone(cdk_config)


if __name__ == "__main__":
    unittest.main()
