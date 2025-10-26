"""
Unit tests for Lambda@Edge IP Gate handler
Tests the Lambda function logic with proper mocking
"""

import pytest
import json
import sys
from pathlib import Path
from unittest.mock import Mock, patch, mock_open

# Add the Lambda handler to the path
lambda_path = Path(__file__).parent.parent.parent / "src" / "cdk_factory" / "lambdas" / "edge" / "ip_gate"
sys.path.insert(0, str(lambda_path))

import handler


def create_cloudfront_event(client_ip: str, uri: str = "/") -> dict:
    """Helper to create a CloudFront origin-request event"""
    return {
        "Records": [{
            "cf": {
                "request": {
                    "clientIp": client_ip,
                    "headers": {},
                    "uri": uri,
                    "method": "GET"
                }
            }
        }]
    }


def create_mock_context(function_name: str = "tech-talk-dev-ip-gate"):
    """Helper to create a mock Lambda context"""
    context = Mock()
    context.function_name = function_name
    context.invoked_function_arn = f"arn:aws:lambda:us-east-1:123456789012:function:{function_name}:1"
    return context


def create_runtime_config(env: str = "dev", function_name: str = "ip-gate"):
    """Helper to create runtime config"""
    return {
        'environment': env,
        'function_name': function_name,
        'region': 'us-east-1'
    }


def create_ssm_params(gate_enabled='true', allow_cidrs='', maint_host='maintenance.cloudfront.net', response_mode='redirect'):
    """Helper to create SSM parameter dict"""
    return {
        '/dev/tech-talk-dev-ip-gate/gate-enabled': gate_enabled,
        '/dev/tech-talk-dev-ip-gate/allow-cidrs': allow_cidrs,
        '/dev/tech-talk-dev-ip-gate/maint-cf-host': maint_host,
        '/dev/tech-talk-dev-ip-gate/response-mode': response_mode
    }


class TestIPGateAllowlist:
    """Test IP allowlist functionality"""
    
    @patch('builtins.open', new_callable=mock_open)
    @patch('handler.get_ssm_parameter')
    def test_allows_whitelisted_single_ip(self, mock_ssm, mock_file):
        """IP in allowlist should pass through to origin"""
        # Mock runtime_config.json
        mock_file.return_value.read.return_value = json.dumps(create_runtime_config())
        
        # Mock SSM parameters
        ssm_params = create_ssm_params(allow_cidrs='203.0.113.10/32')
        mock_ssm.side_effect = lambda param_name, region=None, default=None: ssm_params.get(param_name, default or '')
        
        event = create_cloudfront_event("203.0.113.10")
        context = create_mock_context()
        result = handler.lambda_handler(event, context)
        
        # Should return the original request (not a redirect)
        assert result == event['Records'][0]['cf']['request']
    
    @patch('builtins.open', new_callable=mock_open)
    @patch('handler.get_ssm_parameter')
    def test_allows_whitelisted_cidr_range(self, mock_ssm, mock_file):
        """IP in CIDR range should pass through"""
        mock_file.return_value.read.return_value = json.dumps(create_runtime_config())
        ssm_params = create_ssm_params(allow_cidrs='198.51.100.0/24')
        mock_ssm.side_effect = lambda param_name, region=None, default=None: ssm_params.get(param_name, default or '')
        
        event = create_cloudfront_event("198.51.100.50")
        context = create_mock_context()
        result = handler.lambda_handler(event, context)
        
        assert result == event['Records'][0]['cf']['request']
    
    @patch('builtins.open', new_callable=mock_open)
    @patch('handler.get_ssm_parameter')
    def test_blocks_non_whitelisted_ip(self, mock_ssm, mock_file):
        """IP not in allowlist should redirect to maintenance"""
        mock_file.return_value.read.return_value = json.dumps(create_runtime_config())
        ssm_params = create_ssm_params(allow_cidrs='203.0.113.10/32')
        mock_ssm.side_effect = lambda param_name, region=None, default=None: ssm_params.get(param_name, default or '')
        
        event = create_cloudfront_event("192.0.2.1")
        context = create_mock_context()
        result = handler.lambda_handler(event, context)
        
        # Should be a 302 redirect
        assert result['status'] == '302'
        assert result['headers']['location'][0]['value'] == 'https://maintenance.cloudfront.net'
    
    @patch('builtins.open', new_callable=mock_open)
    @patch('handler.get_ssm_parameter')
    def test_allows_multiple_cidrs(self, mock_ssm, mock_file):
        """Multiple CIDR ranges in allowlist"""
        mock_file.return_value.read.return_value = json.dumps(create_runtime_config())
        ssm_params = create_ssm_params(allow_cidrs='203.0.113.10/32,198.51.100.0/24,192.0.2.0/24')
        mock_ssm.side_effect = lambda param_name, region=None, default=None: ssm_params.get(param_name, default or '')
        
        context = create_mock_context()
        
        # Test IP from first CIDR
        event1 = create_cloudfront_event("203.0.113.10")
        result1 = handler.lambda_handler(event1, context)
        assert result1 == event1['Records'][0]['cf']['request']
        
        # Test IP from second CIDR
        event2 = create_cloudfront_event("198.51.100.100")
        result2 = handler.lambda_handler(event2, context)
        assert result2 == event2['Records'][0]['cf']['request']


class TestGateToggle:
    """Test gate enable/disable functionality"""
    
    @patch('builtins.open', new_callable=mock_open)
    @patch('handler.get_ssm_parameter')
    def test_gate_disabled_allows_all(self, mock_ssm, mock_file):
        """When gate is disabled, all IPs should pass through"""
        mock_file.return_value.read.return_value = json.dumps(create_runtime_config())
        ssm_params = create_ssm_params(gate_enabled='false', allow_cidrs='203.0.113.10/32')
        mock_ssm.side_effect = lambda param_name, region=None, default=None: ssm_params.get(param_name, default or '')
        
        # Test with non-whitelisted IP
        event = create_cloudfront_event("192.0.2.1")
        context = create_mock_context()
        result = handler.lambda_handler(event, context)
        
        # Should pass through (not redirect to maintenance)
        assert result == event['Records'][0]['cf']['request']
    
    @patch('builtins.open', new_callable=mock_open)
    @patch('handler.get_ssm_parameter')
    def test_gate_enabled_enforces_allowlist(self, mock_ssm, mock_file):
        """When gate is enabled, allowlist is enforced"""
        mock_file.return_value.read.return_value = json.dumps(create_runtime_config())
        ssm_params = create_ssm_params(allow_cidrs='203.0.113.10/32')
        mock_ssm.side_effect = lambda param_name, region=None, default=None: ssm_params.get(param_name, default or '')
        
        event = create_cloudfront_event("192.0.2.1")
        context = create_mock_context()
        result = handler.lambda_handler(event, context)
        
        # Should redirect to maintenance
        assert result['status'] == '302'


class TestURINormalization:
    """Test that URIs are NOT normalized - the new handler does redirects not origin rewrites"""
    
    @patch('builtins.open', new_callable=mock_open)
    @patch('handler.get_ssm_parameter')
    def test_directory_request_normalized(self, mock_ssm, mock_file):
        """URI should remain unchanged - we redirect, not rewrite"""
        mock_file.return_value.read.return_value = json.dumps(create_runtime_config())
        ssm_params = create_ssm_params(allow_cidrs='203.0.113.10/32')
        mock_ssm.side_effect = lambda param_name, region=None, default=None: ssm_params.get(param_name, default or '')
        
        event = create_cloudfront_event("192.0.2.1", uri="/about/")
        context = create_mock_context()
        result = handler.lambda_handler(event, context)
        
        # New handler does 302 redirect, doesn't rewrite URIs
        assert result['status'] == '302'
    
    @patch('builtins.open', new_callable=mock_open)
    @patch('handler.get_ssm_parameter')
    def test_path_without_extension_normalized(self, mock_ssm, mock_file):
        """Path without extension gets redirected"""
        mock_file.return_value.read.return_value = json.dumps(create_runtime_config())
        ssm_params = create_ssm_params(allow_cidrs='203.0.113.10/32')
        mock_ssm.side_effect = lambda param_name, region=None, default=None: ssm_params.get(param_name, default or '')
        
        event = create_cloudfront_event("192.0.2.1", uri="/about")
        context = create_mock_context()
        result = handler.lambda_handler(event, context)
        
        assert result['status'] == '302'
    
    @patch('builtins.open', new_callable=mock_open)
    @patch('handler.get_ssm_parameter')
    def test_file_request_not_normalized(self, mock_ssm, mock_file):
        """File requests also get redirected if IP blocked"""
        mock_file.return_value.read.return_value = json.dumps(create_runtime_config())
        ssm_params = create_ssm_params(allow_cidrs='203.0.113.10/32')
        mock_ssm.side_effect = lambda param_name, region=None, default=None: ssm_params.get(param_name, default or '')
        
        event = create_cloudfront_event("192.0.2.1", uri="/styles.css")
        context = create_mock_context()
        result = handler.lambda_handler(event, context)
        
        assert result['status'] == '302'


class TestXViewerIPHeader:
    """Test that viewer IP header is NOT added - new handler doesn't inject headers"""
    
    @patch('builtins.open', new_callable=mock_open)
    @patch('handler.get_ssm_parameter')
    def test_header_injected_for_allowed_ip(self, mock_ssm, mock_file):
        """Allowed IPs pass through"""
        mock_file.return_value.read.return_value = json.dumps(create_runtime_config())
        ssm_params = create_ssm_params(allow_cidrs='203.0.113.10/32')
        mock_ssm.side_effect = lambda param_name, region=None, default=None: ssm_params.get(param_name, default or '')
        
        event = create_cloudfront_event("203.0.113.10")
        context = create_mock_context()
        result = handler.lambda_handler(event, context)
        
        # New handler returns original request for allowed IPs
        assert result == event['Records'][0]['cf']['request']
    
    @patch('builtins.open', new_callable=mock_open)
    @patch('handler.get_ssm_parameter')
    def test_header_injected_for_blocked_ip(self, mock_ssm, mock_file):
        """Blocked IPs get redirected"""
        mock_file.return_value.read.return_value = json.dumps(create_runtime_config())
        ssm_params = create_ssm_params(allow_cidrs='203.0.113.10/32')
        mock_ssm.side_effect = lambda param_name, region=None, default=None: ssm_params.get(param_name, default or '')
        
        event = create_cloudfront_event("192.0.2.1")
        context = create_mock_context()
        result = handler.lambda_handler(event, context)
        
        # Blocked IPs get 302 redirect
        assert result['status'] == '302'


class TestEdgeCases:
    """Test edge cases and error handling"""
    
    @patch('builtins.open', new_callable=mock_open)
    @patch('handler.get_ssm_parameter')
    def test_invalid_cidr_ignored(self, mock_ssm, mock_file):
        """Invalid CIDR in list should be ignored, not crash"""
        mock_file.return_value.read.return_value = json.dumps(create_runtime_config())
        ssm_params = create_ssm_params(allow_cidrs='203.0.113.10/32,invalid-cidr,198.51.100.0/24')
        mock_ssm.side_effect = lambda param_name, region=None, default=None: ssm_params.get(param_name, default or '')
        
        # IP in valid CIDR should still work (198.51.100.0/24)
        event = create_cloudfront_event("198.51.100.50")
        context = create_mock_context()
        result = handler.lambda_handler(event, context)
        
        # Should pass through (not be a redirect)
        assert result == event['Records'][0]['cf']['request']
    
    @patch('builtins.open', new_callable=mock_open)
    @patch('handler.get_ssm_parameter')
    def test_missing_maint_host_passes_through(self, mock_ssm, mock_file):
        """If SSM fetch fails, should pass through (fail open)"""
        mock_file.return_value.read.return_value = json.dumps(create_runtime_config())
        # SSM call raises exception
        mock_ssm.side_effect = Exception("SSM error")
        
        event = create_cloudfront_event("192.0.2.1")
        context = create_mock_context()
        result = handler.lambda_handler(event, context)
        
        # Should pass through due to error (fail open)
        assert result == event['Records'][0]['cf']['request']
    
    @patch('builtins.open', new_callable=mock_open)
    @patch('handler.get_ssm_parameter')
    def test_empty_allowlist_blocks_all(self, mock_ssm, mock_file):
        """Empty allowlist should block all traffic when gate enabled"""
        mock_file.return_value.read.return_value = json.dumps(create_runtime_config())
        ssm_params = create_ssm_params(allow_cidrs='')
        mock_ssm.side_effect = lambda param_name, region=None, default=None: ssm_params.get(param_name, default or '')
        
        event = create_cloudfront_event("203.0.113.10")
        context = create_mock_context()
        result = handler.lambda_handler(event, context)
        
        # Should redirect to maintenance
        assert result['status'] == '302'


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
