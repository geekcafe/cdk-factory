"""
Lambda@Edge Configuration for CDK-Factory
Geek Cafe, LLC
Maintainers: Eric Wilson
MIT License. See Project Root for the license information.
"""
from typing import Dict, Optional
from cdk_factory.configurations.enhanced_base_config import EnhancedBaseConfig


class LambdaEdgeConfig(EnhancedBaseConfig):
    """
    Configuration class for Lambda@Edge functions.
    Lambda@Edge has specific constraints:
    - Must be deployed in us-east-1
    - Max timeout: 5 seconds for origin-request/response, 30s for viewer-request/response
    - Max memory: 10GB (but typically use 128-512MB for edge functions)
    - Must use versioned functions (not $LATEST)
    """

    def __init__(self, config: dict = None, deployment=None) -> None:
        super().__init__(
            config or {},
            resource_type="lambda_edge",
            resource_name=config.get("name", "lambda-edge") if config else "lambda-edge"
        )
        self._config = config or {}
        self._deployment = deployment

    @property
    def name(self) -> str:
        """Function name"""
        return self._config.get("name", "lambda-edge")

    @property
    def handler(self) -> str:
        """Handler function (e.g., 'handler.lambda_handler')"""
        return self._config.get("handler", "handler.lambda_handler")

    @property
    def runtime(self) -> str:
        """Lambda runtime (e.g., 'python3.11')"""
        return self._config.get("runtime", "python3.11")

    @property
    def memory_size(self) -> int:
        """Memory size in MB (128-10240)"""
        return int(self._config.get("memory_size", 128))

    @property
    def timeout(self) -> int:
        """Timeout in seconds
        viewer-request: 5s
        viewer-response: 5s
        ---
        origin-request: 30s
        origin-response: 30s
        
        
        """
        timeout = int(self._config.get("timeout", 5))

        event_type = self.event_type
        if event_type == "viewer-request" or event_type == "viewer-response":
            if timeout > 5:
                raise ValueError("Lambda@Edge viewer timeout cannot exceed 5 seconds. Value was set to {}".format(timeout))
        else:
            if timeout > 30:
                raise ValueError("Lambda@Edge origin timeout cannot exceed 30 seconds. Value was set to {}".format(timeout))
        return timeout

    @property
    def code_path(self) -> str:
        """Path to Lambda function code directory"""
        return self._config.get("code_path", "./lambdas/cloudfront/ip_gate")

    @property
    def environment(self) -> Dict[str, str]:
        """Environment variables for the Lambda function"""
        return self._config.get("environment", {})

    @property
    def description(self) -> str:
        """Function description"""
        return self._config.get("description", "Lambda@Edge function")

    @property
    def event_type(self) -> str:
        """
        Lambda@Edge event type:
        - viewer-request: Executes when CloudFront receives a request from viewer
        - origin-request: Executes before CloudFront forwards request to origin
        - origin-response: Executes after CloudFront receives response from origin
        - viewer-response: Executes before CloudFront returns response to viewer
        """
        return self._config.get("event_type", "origin-request")

    @property
    def publish_version(self) -> bool:
        """Whether to publish a new version (required for Lambda@Edge)"""
        return self._config.get("publish_version", True)

    @property
    def include_body(self) -> bool:
        """Whether to include request body in origin-request events"""
        return self._config.get("include_body", False)

    @property
    def tags(self) -> Dict[str, str]:
        """Tags to apply to the Lambda function"""
        return self._config.get("tags", {})
