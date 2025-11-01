"""
Unit tests for the CloudFront Stack - No Mocking, Real CDK Synthesis
Follows established testing patterns with pytest fixtures and real CDK synthesis.
"""

import pytest
import aws_cdk as cdk
from aws_cdk import App
from aws_cdk.assertions import Template, Match

from cdk_factory.configurations.deployment import DeploymentConfig
from cdk_factory.configurations.stack import StackConfig
from cdk_factory.stack_library.cloudfront.cloudfront_stack import CloudFrontStack
from cdk_factory.workload.workload_factory import WorkloadConfig


class TestCloudFrontStack:
    """Test CloudFront stack with real CDK synthesis"""

    @pytest.fixture
    def app(self):
        """Create CDK App for testing"""
        return App()

    @pytest.fixture
    def workload_config(self):
        """Create a basic workload config"""
        return WorkloadConfig(
            {
                "workload": {
                    "name": "test-workload",
                    "devops": {"name": "test-devops"},
                }
            }
        )

    @pytest.fixture
    def deployment_config(self, workload_config):
        """Create a deployment config"""
        return DeploymentConfig(
            workload=workload_config.dictionary,
            deployment={
                "name": "test-deployment",
                "environment": "test",
                "account": "123456789012",
                "region": "us-east-1",
            },
        )

    def test_minimal_cloudfront_distribution(
        self, app, deployment_config, workload_config
    ):
        """Test CloudFront distribution with minimal configuration"""
        stack_config = StackConfig(
            {
                "cloudfront": {
                    "name": "test-distribution",
                    "comment": "Test CloudFront distribution",
                    "enabled": True,
                    "origins": [
                        {
                            "id": "alb-origin",
                            "type": "custom",
                            "domain_name": "example-alb.us-east-1.elb.amazonaws.com",
                            "protocol_policy": "https-only",
                        }
                    ],
                    "default_cache_behavior": {
                        "target_origin_id": "alb-origin",
                        "viewer_protocol_policy": "redirect-to-https",
                        "allowed_methods": ["GET", "HEAD"],
                        "cached_methods": ["GET", "HEAD"],
                    },
                }
            },
            workload=workload_config.dictionary,
        )

        stack = CloudFrontStack(
            app,
            "TestMinimalCloudFront",
            env=cdk.Environment(account="123456789012", region="us-east-1"),
        )
        stack.build(
            stack_config=stack_config,
            deployment=deployment_config,
            workload=workload_config,
        )
        template = Template.from_stack(stack)

        # Verify CloudFront Distribution exists
        template.has_resource("AWS::CloudFront::Distribution", {})

        # Verify distribution properties
        template.has_resource_properties(
            "AWS::CloudFront::Distribution",
            {
                "DistributionConfig": Match.object_like(
                    {
                        "Enabled": True,
                        "Comment": "Test CloudFront distribution",
                    }
                )
            },
        )

        # Verify origin configuration
        template.has_resource_properties(
            "AWS::CloudFront::Distribution",
            {
                "DistributionConfig": Match.object_like(
                    {
                        "Origins": Match.array_with(
                            [
                                Match.object_like(
                                    {
                                        "DomainName": "example-alb.us-east-1.elb.amazonaws.com",
                                        "Id": "alb-origin",
                                    }
                                )
                            ]
                        )
                    }
                )
            },
        )

        assert stack.cf_config.name == "test-distribution"
        assert stack.distribution is not None

    def test_cloudfront_with_custom_origin(
        self, app, deployment_config, workload_config
    ):
        """Test CloudFront with custom origin configuration"""
        stack_config = StackConfig(
            {
                "cloudfront": {
                    "name": "custom-origin-distribution",
                    "origins": [
                        {
                            "id": "api-origin",
                            "type": "custom",
                            "domain_name": "api.example.com",
                            "protocol_policy": "https-only",
                            "https_port": 443,
                            "origin_ssl_protocols": ["TLSv1.2"],
                            "custom_headers": {"X-Custom-Header": "custom-value"},
                        }
                    ],
                    "default_cache_behavior": {
                        "target_origin_id": "api-origin",
                        "viewer_protocol_policy": "https-only",
                        "allowed_methods": [
                            "GET",
                            "HEAD",
                            "OPTIONS",
                            "PUT",
                            "POST",
                            "PATCH",
                            "DELETE",
                        ],
                    },
                }
            },
            workload=workload_config.dictionary,
        )

        stack = CloudFrontStack(
            app,
            "TestCustomOrigin",
            env=cdk.Environment(account="123456789012", region="us-east-1"),
        )
        stack.build(
            stack_config=stack_config,
            deployment=deployment_config,
            workload=workload_config,
        )
        template = Template.from_stack(stack)

        # Verify custom origin configuration
        template.has_resource_properties(
            "AWS::CloudFront::Distribution",
            {
                "DistributionConfig": Match.object_like(
                    {
                        "Origins": Match.array_with(
                            [
                                Match.object_like(
                                    {
                                        "DomainName": "api.example.com",
                                        "CustomOriginConfig": Match.object_like(
                                            {
                                                "OriginProtocolPolicy": "https-only",
                                                "OriginSSLProtocols": ["TLSv1.2"],
                                            }
                                        ),
                                    }
                                )
                            ]
                        )
                    }
                )
            },
        )

    def test_cloudfront_with_aliases_and_certificate(
        self, app, deployment_config, workload_config
    ):
        """Test CloudFront with domain aliases and certificate"""
        stack_config = StackConfig(
            {
                "cloudfront": {
                    "name": "alias-distribution",
                    "aliases": ["www.example.com", "example.com"],
                    "certificate": {
                        "arn": "arn:aws:acm:us-east-1:123456789012:certificate/abc-123"
                    },
                    "origins": [
                        {
                            "id": "web-origin",
                            "type": "custom",
                            "domain_name": "web.example.com",
                        }
                    ],
                    "default_cache_behavior": {
                        "target_origin_id": "web-origin",
                    },
                }
            },
            workload=workload_config.dictionary,
        )

        stack = CloudFrontStack(
            app,
            "TestAliases",
            env=cdk.Environment(account="123456789012", region="us-east-1"),
        )
        stack.build(
            stack_config=stack_config,
            deployment=deployment_config,
            workload=workload_config,
        )
        template = Template.from_stack(stack)

        # Verify aliases
        template.has_resource_properties(
            "AWS::CloudFront::Distribution",
            {
                "DistributionConfig": Match.object_like(
                    {
                        "Aliases": ["www.example.com", "example.com"],
                    }
                )
            },
        )

        # Verify certificate configuration
        template.has_resource_properties(
            "AWS::CloudFront::Distribution",
            {
                "DistributionConfig": Match.object_like(
                    {
                        "ViewerCertificate": Match.object_like(
                            {
                                "AcmCertificateArn": "arn:aws:acm:us-east-1:123456789012:certificate/abc-123",
                            }
                        )
                    }
                )
            },
        )

        assert stack.certificate is not None

    def test_cloudfront_with_cache_policy(
        self, app, deployment_config, workload_config
    ):
        """Test CloudFront with custom cache policy"""
        stack_config = StackConfig(
            {
                "cloudfront": {
                    "name": "cache-policy-distribution",
                    "origins": [
                        {
                            "id": "cached-origin",
                            "type": "custom",
                            "domain_name": "cache.example.com",
                        }
                    ],
                    "default_cache_behavior": {
                        "target_origin_id": "cached-origin",
                        "cache_policy": {"name": "CachingDisabled"},
                    },
                }
            },
            workload=workload_config.dictionary,
        )

        stack = CloudFrontStack(
            app,
            "TestCachePolicy",
            env=cdk.Environment(account="123456789012", region="us-east-1"),
        )
        stack.build(
            stack_config=stack_config,
            deployment=deployment_config,
            workload=workload_config,
        )
        template = Template.from_stack(stack)

        # Verify cache policy is configured
        template.has_resource_properties(
            "AWS::CloudFront::Distribution",
            {
                "DistributionConfig": Match.object_like(
                    {
                        "DefaultCacheBehavior": Match.object_like(
                            {
                                "CachePolicyId": Match.any_value(),
                            }
                        )
                    }
                )
            },
        )

    def test_cloudfront_with_lambda_edge(self, app, deployment_config, workload_config):
        """
        Test CloudFront with Lambda@Edge associations

        This test validates that Lambda@Edge functions can be attached to CloudFront distributions.
        This is the underlying functionality used by the `enable_ip_gating` convenience flag in
        CloudFrontDistributionConstruct (used by StaticWebsiteStack).
        """
        stack_config = StackConfig(
            {
                "cloudfront": {
                    "name": "lambda-edge-distribution",
                    "origins": [
                        {
                            "id": "edge-origin",
                            "type": "custom",
                            "domain_name": "edge.example.com",
                        }
                    ],
                    "default_cache_behavior": {
                        "target_origin_id": "edge-origin",
                        "lambda_edge_associations": [
                            {
                                "event_type": "origin-request",
                                "lambda_arn": "arn:aws:lambda:us-east-1:123456789012:function:edge-function:1",
                                "include_body": False,
                            }
                        ],
                    },
                }
            },
            workload=workload_config.dictionary,
        )

        stack = CloudFrontStack(
            app,
            "TestLambdaEdge",
            env=cdk.Environment(account="123456789012", region="us-east-1"),
        )
        stack.build(
            stack_config=stack_config,
            deployment=deployment_config,
            workload=workload_config,
        )
        template = Template.from_stack(stack)

        # Verify Lambda@Edge association
        template.has_resource_properties(
            "AWS::CloudFront::Distribution",
            {
                "DistributionConfig": Match.object_like(
                    {
                        "DefaultCacheBehavior": Match.object_like(
                            {
                                "LambdaFunctionAssociations": Match.array_with(
                                    [
                                        Match.object_like(
                                            {
                                                "EventType": "origin-request",
                                                "LambdaFunctionARN": "arn:aws:lambda:us-east-1:123456789012:function:edge-function:1",
                                            }
                                        )
                                    ]
                                )
                            }
                        )
                    }
                )
            },
        )

    def test_cloudfront_with_error_responses(
        self, app, deployment_config, workload_config
    ):
        """Test CloudFront with custom error responses"""
        stack_config = StackConfig(
            {
                "cloudfront": {
                    "name": "error-response-distribution",
                    "origins": [
                        {
                            "id": "error-origin",
                            "type": "custom",
                            "domain_name": "errors.example.com",
                        }
                    ],
                    "default_cache_behavior": {
                        "target_origin_id": "error-origin",
                    },
                    "custom_error_responses": [
                        {
                            "error_code": 404,
                            "response_http_status": 200,
                            "response_page_path": "/index.html",
                            "error_caching_min_ttl": 10,
                        },
                        {
                            "error_code": 500,
                            "error_caching_min_ttl": 0,
                        },
                    ],
                }
            },
            workload=workload_config.dictionary,
        )

        stack = CloudFrontStack(
            app,
            "TestErrorResponses",
            env=cdk.Environment(account="123456789012", region="us-east-1"),
        )
        stack.build(
            stack_config=stack_config,
            deployment=deployment_config,
            workload=workload_config,
        )
        template = Template.from_stack(stack)

        # Verify error responses
        template.has_resource_properties(
            "AWS::CloudFront::Distribution",
            {
                "DistributionConfig": Match.object_like(
                    {
                        "CustomErrorResponses": Match.array_with(
                            [
                                Match.object_like(
                                    {
                                        "ErrorCode": 404,
                                        "ResponseCode": 200,
                                        "ResponsePagePath": "/index.html",
                                    }
                                )
                            ]
                        )
                    }
                )
            },
        )

    def test_cloudfront_with_ssm_exports(self, app, deployment_config, workload_config):
        """Test CloudFront with SSM parameter exports"""
        stack_config = StackConfig(
            {
                "cloudfront": {
                    "name": "ssm-export-distribution",
                    "origins": [
                        {
                            "id": "ssm-origin",
                            "type": "custom",
                            "domain_name": "ssm.example.com",
                        }
                    ],
                    "default_cache_behavior": {
                        "target_origin_id": "ssm-origin",
                    },
                    "ssm": {
                        "exports": {
                            "distribution_id": "/test/cloudfront/distribution-id",
                            "distribution_domain": "/test/cloudfront/domain",
                        },
                    },
                }
            },
            workload=workload_config.dictionary,
        )

        stack = CloudFrontStack(
            app,
            "TestSSMExports",
            env=cdk.Environment(account="123456789012", region="us-east-1"),
        )
        stack.build(
            stack_config=stack_config,
            deployment=deployment_config,
            workload=workload_config,
        )
        template = Template.from_stack(stack)

        # Verify SSM parameters exist
        template.resource_count_is("AWS::SSM::Parameter", 2)

        template.has_resource_properties(
            "AWS::SSM::Parameter",
            {
                "Name": "/test/cloudfront/distribution-id",
                "Type": "String",
            },
        )

        template.has_resource_properties(
            "AWS::SSM::Parameter",
            {
                "Name": "/test/cloudfront/domain",
                "Type": "String",
            },
        )

    def test_cloudfront_requires_origins(self, app, deployment_config, workload_config):
        """Test that CloudFront requires at least one origin"""
        stack_config = StackConfig(
            {
                "cloudfront": {
                    "name": "no-origin-distribution",
                    "origins": [],
                    "default_cache_behavior": {},
                }
            },
            workload=workload_config.dictionary,
        )

        stack = CloudFrontStack(
            app,
            "TestNoOrigins",
            env=cdk.Environment(account="123456789012", region="us-east-1"),
        )
        with pytest.raises(ValueError, match="At least one origin is required"):
            stack.build(
                stack_config=stack_config,
                deployment=deployment_config,
                workload=workload_config,
            )

    def test_cloudfront_with_price_class(self, app, deployment_config, workload_config):
        """Test CloudFront with custom price class"""
        stack_config = StackConfig(
            {
                "cloudfront": {
                    "name": "price-class-distribution",
                    "price_class": "PriceClass_100",
                    "origins": [
                        {
                            "id": "price-origin",
                            "type": "custom",
                            "domain_name": "price.example.com",
                        }
                    ],
                    "default_cache_behavior": {
                        "target_origin_id": "price-origin",
                    },
                }
            },
            workload=workload_config.dictionary,
        )

        stack = CloudFrontStack(
            app,
            "TestPriceClass",
            env=cdk.Environment(account="123456789012", region="us-east-1"),
        )
        stack.build(
            stack_config=stack_config,
            deployment=deployment_config,
            workload=workload_config,
        )
        template = Template.from_stack(stack)

        # Verify price class
        template.has_resource_properties(
            "AWS::CloudFront::Distribution",
            {
                "DistributionConfig": Match.object_like(
                    {
                        "PriceClass": "PriceClass_100",
                    }
                )
            },
        )

    def test_cloudfront_with_http_version(
        self, app, deployment_config, workload_config
    ):
        """Test CloudFront with HTTP version configuration"""
        stack_config = StackConfig(
            {
                "cloudfront": {
                    "name": "http-version-distribution",
                    "http_version": "http2_and_3",
                    "origins": [
                        {
                            "id": "http-origin",
                            "type": "custom",
                            "domain_name": "http.example.com",
                        }
                    ],
                    "default_cache_behavior": {
                        "target_origin_id": "http-origin",
                    },
                }
            },
            workload=workload_config.dictionary,
        )

        stack = CloudFrontStack(
            app,
            "TestHTTPVersion",
            env=cdk.Environment(account="123456789012", region="us-east-1"),
        )
        stack.build(
            stack_config=stack_config,
            deployment=deployment_config,
            workload=workload_config,
        )
        template = Template.from_stack(stack)

        # Verify HTTP version (CloudFormation uses lowercase without underscores)
        template.has_resource_properties(
            "AWS::CloudFront::Distribution",
            {
                "DistributionConfig": Match.object_like(
                    {
                        "HttpVersion": "http2and3",
                    }
                )
            },
        )

        # But the config value uses underscores to match CDK enum naming
        assert stack.cf_config.http_version == "http2_and_3"
