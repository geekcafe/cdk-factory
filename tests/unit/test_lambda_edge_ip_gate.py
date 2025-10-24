"""
Unit tests for Lambda@Edge IP Gate handler
Tests the Lambda function logic without mocking
"""

import pytest
import os
import sys
from pathlib import Path

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
                    "origin": {}
                }
            }
        }]
    }


class TestIPGateAllowlist:
    """Test IP allowlist functionality"""
    
    def test_allows_whitelisted_single_ip(self, monkeypatch):
        """IP in allowlist should pass through to origin"""
        monkeypatch.setenv("GATE_ENABLED", "true")
        monkeypatch.setenv("ALLOW_CIDRS", "203.0.113.10/32")
        monkeypatch.setenv("MAINT_CF_HOST", "maintenance.cloudfront.net")
        
        event = create_cloudfront_event("203.0.113.10")
        result = handler.lambda_handler(event, None)
        
        # Should pass through to original origin (not rewritten to maintenance)
        assert 'custom' not in result.get('origin', {})
        # Should have X-Viewer-IP header
        assert 'x-viewer-ip' in result['headers']
        assert result['headers']['x-viewer-ip'][0]['value'] == "203.0.113.10"
    
    def test_allows_whitelisted_cidr_range(self, monkeypatch):
        """IP in CIDR range should pass through"""
        monkeypatch.setenv("GATE_ENABLED", "true")
        monkeypatch.setenv("ALLOW_CIDRS", "198.51.100.0/24")
        monkeypatch.setenv("MAINT_CF_HOST", "maintenance.cloudfront.net")
        
        event = create_cloudfront_event("198.51.100.50")
        result = handler.lambda_handler(event, None)
        
        assert 'custom' not in result.get('origin', {})
        assert 'x-viewer-ip' in result['headers']
    
    def test_blocks_non_whitelisted_ip(self, monkeypatch):
        """IP not in allowlist should redirect to maintenance"""
        monkeypatch.setenv("GATE_ENABLED", "true")
        monkeypatch.setenv("ALLOW_CIDRS", "203.0.113.10/32")
        monkeypatch.setenv("MAINT_CF_HOST", "maintenance.cloudfront.net")
        
        event = create_cloudfront_event("192.0.2.1")
        result = handler.lambda_handler(event, None)
        
        # Should be redirected to maintenance site
        assert 'custom' in result['origin']
        assert result['origin']['custom']['domainName'] == "maintenance.cloudfront.net"
        assert result['origin']['custom']['protocol'] == "https"
        
        # Host header should be updated
        assert result['headers']['host'][0]['value'] == "maintenance.cloudfront.net"
    
    def test_allows_multiple_cidrs(self, monkeypatch):
        """Multiple CIDR ranges in allowlist"""
        monkeypatch.setenv("GATE_ENABLED", "true")
        monkeypatch.setenv("ALLOW_CIDRS", "203.0.113.10/32,198.51.100.0/24,192.0.2.0/24")
        monkeypatch.setenv("MAINT_CF_HOST", "maintenance.cloudfront.net")
        
        # Test IP from first CIDR
        event1 = create_cloudfront_event("203.0.113.10")
        result1 = handler.lambda_handler(event1, None)
        assert 'custom' not in result1.get('origin', {})
        
        # Test IP from second CIDR
        event2 = create_cloudfront_event("198.51.100.100")
        result2 = handler.lambda_handler(event2, None)
        assert 'custom' not in result2.get('origin', {})
        
        # Test IP from third CIDR
        event3 = create_cloudfront_event("192.0.2.50")
        result3 = handler.lambda_handler(event3, None)
        assert 'custom' not in result3.get('origin', {})


class TestGateToggle:
    """Test gate enable/disable functionality"""
    
    def test_gate_disabled_allows_all(self, monkeypatch):
        """When gate is disabled, all IPs should pass through"""
        monkeypatch.setenv("GATE_ENABLED", "false")
        monkeypatch.setenv("ALLOW_CIDRS", "203.0.113.10/32")
        monkeypatch.setenv("MAINT_CF_HOST", "maintenance.cloudfront.net")
        
        # Test with non-whitelisted IP
        event = create_cloudfront_event("192.0.2.1")
        result = handler.lambda_handler(event, None)
        
        # Should pass through (not redirect to maintenance)
        assert 'custom' not in result.get('origin', {})
        assert 'x-viewer-ip' in result['headers']
    
    def test_gate_enabled_enforces_allowlist(self, monkeypatch):
        """When gate is enabled, allowlist is enforced"""
        monkeypatch.setenv("GATE_ENABLED", "true")
        monkeypatch.setenv("ALLOW_CIDRS", "203.0.113.10/32")
        monkeypatch.setenv("MAINT_CF_HOST", "maintenance.cloudfront.net")
        
        event = create_cloudfront_event("192.0.2.1")
        result = handler.lambda_handler(event, None)
        
        # Should redirect to maintenance
        assert 'custom' in result['origin']


class TestURINormalization:
    """Test URI normalization for maintenance site"""
    
    def test_directory_request_normalized(self, monkeypatch):
        """Directory path should get index.html appended"""
        monkeypatch.setenv("GATE_ENABLED", "true")
        monkeypatch.setenv("ALLOW_CIDRS", "203.0.113.10/32")
        monkeypatch.setenv("MAINT_CF_HOST", "maintenance.cloudfront.net")
        
        event = create_cloudfront_event("192.0.2.1", uri="/about/")
        result = handler.lambda_handler(event, None)
        
        assert result['uri'] == "/about/index.html"
    
    def test_path_without_extension_normalized(self, monkeypatch):
        """Path without extension should get /index.html"""
        monkeypatch.setenv("GATE_ENABLED", "true")
        monkeypatch.setenv("ALLOW_CIDRS", "203.0.113.10/32")
        monkeypatch.setenv("MAINT_CF_HOST", "maintenance.cloudfront.net")
        
        event = create_cloudfront_event("192.0.2.1", uri="/about")
        result = handler.lambda_handler(event, None)
        
        assert result['uri'] == "/about/index.html"
    
    def test_file_request_not_normalized(self, monkeypatch):
        """File requests with extensions should not be modified"""
        monkeypatch.setenv("GATE_ENABLED", "true")
        monkeypatch.setenv("ALLOW_CIDRS", "203.0.113.10/32")
        monkeypatch.setenv("MAINT_CF_HOST", "maintenance.cloudfront.net")
        
        event = create_cloudfront_event("192.0.2.1", uri="/styles.css")
        result = handler.lambda_handler(event, None)
        
        assert result['uri'] == "/styles.css"


class TestXViewerIPHeader:
    """Test X-Viewer-IP header injection"""
    
    def test_header_injected_for_allowed_ip(self, monkeypatch):
        """X-Viewer-IP header should be added for allowed IPs"""
        monkeypatch.setenv("GATE_ENABLED", "true")
        monkeypatch.setenv("ALLOW_CIDRS", "203.0.113.10/32")
        monkeypatch.setenv("MAINT_CF_HOST", "maintenance.cloudfront.net")
        
        event = create_cloudfront_event("203.0.113.10")
        result = handler.lambda_handler(event, None)
        
        assert 'x-viewer-ip' in result['headers']
        assert result['headers']['x-viewer-ip'][0]['key'] == 'X-Viewer-IP'
        assert result['headers']['x-viewer-ip'][0]['value'] == "203.0.113.10"
    
    def test_header_injected_for_blocked_ip(self, monkeypatch):
        """X-Viewer-IP header should be added even for blocked IPs"""
        monkeypatch.setenv("GATE_ENABLED", "true")
        monkeypatch.setenv("ALLOW_CIDRS", "203.0.113.10/32")
        monkeypatch.setenv("MAINT_CF_HOST", "maintenance.cloudfront.net")
        
        event = create_cloudfront_event("192.0.2.1")
        result = handler.lambda_handler(event, None)
        
        assert 'x-viewer-ip' in result['headers']
        assert result['headers']['x-viewer-ip'][0]['value'] == "192.0.2.1"


class TestEdgeCases:
    """Test edge cases and error handling"""
    
    def test_invalid_cidr_ignored(self, monkeypatch):
        """Invalid CIDR in list should be ignored, not crash"""
        monkeypatch.setenv("GATE_ENABLED", "true")
        monkeypatch.setenv("ALLOW_CIDRS", "203.0.113.10/32,invalid-cidr,198.51.100.0/24")
        monkeypatch.setenv("MAINT_CF_HOST", "maintenance.cloudfront.net")
        
        # IP in valid CIDR should still work
        event = create_cloudfront_event("198.51.100.50")
        result = handler.lambda_handler(event, None)
        
        assert 'custom' not in result.get('origin', {})
    
    def test_missing_maint_host_passes_through(self, monkeypatch):
        """If maintenance host not configured, should pass through (safety)"""
        monkeypatch.setenv("GATE_ENABLED", "true")
        monkeypatch.setenv("ALLOW_CIDRS", "203.0.113.10/32")
        monkeypatch.setenv("MAINT_CF_HOST", "")
        
        event = create_cloudfront_event("192.0.2.1")
        result = handler.lambda_handler(event, None)
        
        # Should pass through due to missing maintenance host (safety)
        assert 'custom' not in result.get('origin', {})
    
    def test_empty_allowlist_blocks_all(self, monkeypatch):
        """Empty allowlist should block all traffic when gate enabled"""
        monkeypatch.setenv("GATE_ENABLED", "true")
        monkeypatch.setenv("ALLOW_CIDRS", "")
        monkeypatch.setenv("MAINT_CF_HOST", "maintenance.cloudfront.net")
        
        event = create_cloudfront_event("203.0.113.10")
        result = handler.lambda_handler(event, None)
        
        # Should redirect to maintenance
        assert 'custom' in result['origin']


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
