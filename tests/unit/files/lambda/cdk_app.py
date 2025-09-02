#!/usr/bin/env python3
"""
CDK App entry point for testing Lambda stack with existing API Gateway
"""

import os
from pathlib import Path
from cdk_factory.app import CdkAppFactory


class TestLambdaApp:
    """Test Lambda App for reproducing ValidationError"""

    def __init__(self):
        self.name = "TestLambdaApp"

    def synth(self):
        """Synth the lambda stack"""
        print("Synthesizing", self.name)
        path = str(Path(__file__).parent)
        config_path = os.path.join(path, "sample_config.json")
        
        if not os.path.exists(config_path):
            raise FileNotFoundError(f"Config file not found: {config_path}")

        # Set up CDK output directory
        outdir = "./cdk.out"
        
        # Create the factory
        factory = CdkAppFactory(
            config_path=config_path,
            runtime_directory=path,
            outdir=outdir
        )
        
        # Synthesize the CDK app
        cdk_app_file = "./cdk_app.py"
        cloud_assembly = factory.synth(
            paths=[path],
            cdk_app_file=cdk_app_file
        )
        
        return cloud_assembly


def main():
    """Run the app"""
    app = TestLambdaApp()
    app.synth()


if __name__ == "__main__":
    main()
