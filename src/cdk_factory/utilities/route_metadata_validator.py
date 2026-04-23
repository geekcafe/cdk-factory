"""
Route Metadata Validator for API Gateway Route Discovery.
Validates route metadata at both export (LambdaStack) and import (ApiGatewayStack) time.

Maintainers: Eric Wilson
MIT License. See Project Root for the license information.
"""

from typing import Dict, Any

VALID_HTTP_METHODS = {"GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"}


class RouteMetadataValidator:
    """Validates API Gateway route metadata from Lambda resource configs."""

    @staticmethod
    def validate_route(route: str, lambda_name: str) -> None:
        """Validate a single route path. Raises ValueError if invalid."""
        if not route or not isinstance(route, str):
            raise ValueError(
                f"Lambda '{lambda_name}': route must be a non-empty string, got: {route!r}"
            )
        if not route.startswith("/"):
            raise ValueError(
                f"Lambda '{lambda_name}': route must start with '/', got: '{route}'"
            )

    @staticmethod
    def validate_method(method: str, lambda_name: str) -> None:
        """Validate an HTTP method. Raises ValueError if invalid."""
        if not method or not isinstance(method, str):
            raise ValueError(
                f"Lambda '{lambda_name}': method must be a non-empty string, got: {method!r}"
            )
        if method.upper() not in VALID_HTTP_METHODS:
            raise ValueError(
                f"Lambda '{lambda_name}': method must be one of {VALID_HTTP_METHODS}, got: '{method}'"
            )

    @staticmethod
    def validate_route_metadata(metadata: Dict[str, Any], lambda_name: str) -> None:
        """Validate a complete route metadata dict."""
        RouteMetadataValidator.validate_route(metadata.get("route", ""), lambda_name)
        RouteMetadataValidator.validate_method(metadata.get("method", ""), lambda_name)
        for sub_route in metadata.get("routes", []):
            RouteMetadataValidator.validate_route(
                sub_route.get("route", ""), lambda_name
            )
            RouteMetadataValidator.validate_method(
                sub_route.get("method", ""), lambda_name
            )
