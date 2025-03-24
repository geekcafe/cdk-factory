import os
import unittest
from pathlib import Path

from cdk_factory.configurations.cdk_config import CdkConfig


class JsonUtilityTests(unittest.TestCase):
    """Json Utility Tests"""

    def test_json_utility_loading(self):
        """Test Json Loading"""
        website_config_path = os.path.join(
            Path(__file__).parent, "files", "website_config.json"
        )
        if not os.path.exists(website_config_path):
            raise FileNotFoundError(f"File {website_config_path} does not exist")

        cdk_context = {
            "AccountNumber": "123456789",
            "AccountName": "My Account",
            "AccountRegion": "us-east-1",
            "CodeRepoName": "company/my-repo-name",
            "CodeRepoArn": "aws::repo_arn",
            "SiteBucketName": "my-bucket",
            "HostedZoneId": "zone1234",
            "HostedZoneName": "dev.example.com",
        }
        cdk_config: CdkConfig = CdkConfig(website_config_path, cdk_context=cdk_context)
        self.assertIsNotNone(cdk_config)


if __name__ == "__main__":
    unittest.main()
