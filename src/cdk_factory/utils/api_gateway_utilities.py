from typing import List
from aws_lambda_powertools import Logger
from aws_cdk import aws_apigateway as api_gateway

logger = Logger(service="cdk-factory-apigateway-utils")

class ApiGatewayUtilities:
    """Api Gateway Utilities"""

    @staticmethod
    def bind_mock_for_cors(
        resource: api_gateway.Resource,
        route: str,
        http_method_list: List[str] | None = None,
        origins_list: List[str] | None = None,
    ):
        """Create a Mock which will serve as our CORS config"""
        if not http_method_list:
            http_method_list = ["OPTIONS"]
        if not origins_list:
            origins_list = ["*"]
        # known methods
        http_method_list = ["DELETE", "GET", "HEAD", "OPTIONS", "PATCH", "POST", "PUT"]
        http_method_list = [x.upper() for x in http_method_list]
        origins_list = [x.lower() for x in origins_list]
        origins = ",".join(origins_list)
        if "OPTIONS" not in http_method_list:
            http_method_list.append("OPTIONS")
        try:
            http_methods = ",".join(http_method_list)
            options_integration = api_gateway.MockIntegration(
                integration_responses=[
                    {
                        "statusCode": "200",
                        "responseParameters": {
                            "method.response.header.Access-Control-Allow-Headers": "'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token'",
                            "method.response.header.Access-Control-Allow-Methods": f"'{http_methods}'",
                            "method.response.header.Access-Control-Allow-Origin": f"'{origins}'",
                        },
                    }
                ],
                passthrough_behavior=api_gateway.PassthroughBehavior.NEVER,
                request_templates={"application/json": '{"statusCode": 200}'},
            )
            options_method = resource.add_method(
                "OPTIONS",
                options_integration,
                method_responses=[
                    {
                        "statusCode": "200",
                        "responseParameters": {
                            "method.response.header.Access-Control-Allow-Headers": True,
                            "method.response.header.Access-Control-Allow-Methods": True,
                            "method.response.header.Access-Control-Allow-Origin": True,
                        },
                    }
                ],
            )
            ApiGatewayUtilities.add_nag_suppression(
                options_method,
                apig4_reason="OPTIONS method does not require authorization",
                cog4_reason="OPTIONS method does not require authorization or Cognito",
            )
        except Exception as e:
            if "Error: There is already a Construct with name 'OPTIONS'" in str(e):
                logger.error(
                    {
                        "route": route,
                        "error": str(e),
                        "notes": (
                            "This is a OPTIONS mock resource for CORS. "
                            "It's entirely possible the OPTION was already created. "
                            "For example, there is a POST and a GET (defined by differnt resources), "
                            "then the OPTIONS is attempted to be created twice."
                        ),
                    }
                )
            else:
                logger.error({"route": route, "error": str(e)})
                raise e

    @staticmethod
    def add_nag_suppression(
        method: api_gateway.Method, apig4_reason: str, cog4_reason: str
    ):
        """Add CFN Nag suppression for API Gateway"""
        try:
            resource = method.node.find_child("Resource")
            if resource and resource.cfn_options:
                resource.cfn_options.metadata = {
                    "cdk_nag": {
                        "rules_to_suppress": [
                            {"id": "AwsSolutions-APIG4", "reason": apig4_reason},
                            {"id": "AwsSolutions-COG4", "reason": cog4_reason},
                        ]
                    }
                }
            else:
                print("resource.cfn_options.metadata not found")
        except Exception as e:
            print(f"Error: {e}")
