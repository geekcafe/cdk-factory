"""
Geek Cafe, LLC
Maintainers: Eric Wilson
MIT License.  See Project Root for the license information.
"""


from typing import Dict, Any


class ApiGatewayConfig:
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

    def __get(self, key: str) -> Any:
        """Helper method to get config values"""
        if self._config and isinstance(self._config, dict):
            return self._config.get(key)
        return None
