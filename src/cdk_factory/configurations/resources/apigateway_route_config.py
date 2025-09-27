"""
Geek Cafe, LLC
Maintainers: Eric Wilson
MIT License.  See Project Root for the license information.
"""

from typing import Dict, Any


class ApiGatewayConfigRouteConfig:
    """API Gateway Configuration for Lambda Functions"""

    def __init__(self, config: Dict[str, Any]) -> None:
        self._config = config

    @property
    def route(self) -> str:
        """API Gateway route path"""
        return self._config.get("route", "")

    @property
    def method(self) -> str:
        """HTTP method"""
        return self._config.get("method", "GET").upper()

    @property
    def authorization_type(self) -> str:
        """Authorization type"""
        return self._config.get("authorization_type", "NONE")

    @property
    def cors(self) -> Dict[str, Any]:
        """CORS configuration"""
        return self._config.get("cors", {})

    @property
    def authorizer_id(self) -> str:
        """Authorizer ID for existing authorizers"""
        return self._config.get("authorizer_id", "")

    @property
    def api_key_required(self) -> bool:
        """Whether API key is required"""
        return self._config.get("api_key_required", False)

    @property
    def request_parameters(self) -> Dict[str, bool]:
        """Request parameters configuration"""
        return self._config.get("request_parameters", {})

    @property
    def routes(self) -> str:
        """API Gateway routes (alias for route)"""
        return self.route

    @property
    def api_gateway_id(self) -> str:
        """API Gateway ID for existing gateways"""
        return self._config.get("api_gateway_id", "")

    def __get(self, key: str) -> Any:
        """Helper method to get config values"""
        if self._config and isinstance(self._config, dict):
            return self._config.get(key)
        return None

    @property
    def user_pool_id(self) -> str | None:
        """User pool ID for existing authorizers"""
        return self._config.get("user_pool_id")

    @property
    def allow_public_override(self) -> bool:
        """Whether to allow public access when Cognito is available"""
        return str(self._config.get("allow_public_override", False)).lower() == "true"

    @property
    def dictionary(self) -> Dict[str, Any]:
        """Access to the underlying configuration dictionary"""
        return self._config
