"""
Lambda@Edge Origin-Request Handler for IP-based Access Gating
Geek Cafe, LLC
Maintainers: Eric Wilson
"""

import ipaddress
import json
import os


def lambda_handler(event, context):
    """
    Lambda@Edge origin-request handler that implements IP-based gating
    with maintenance site fallback.
    
    Features:
    - Inject X-Viewer-IP header for origin visibility
    - Check viewer IP against allowlist when gate is enabled
    - Rewrite blocked IPs to maintenance CloudFront distribution, and serve up maintenance site
    - Toggle via GATE_ENABLED environment variable
    """
    
    # Extract request from CloudFront event
    request = event['Records'][0]['cf']['request']
    client_ip = request['clientIp']
    
    # Configuration from environment variables
    gate_enabled = os.environ.get('GATE_ENABLED', 'false').lower() == 'true'
    allow_cidrs_str = os.environ.get('ALLOW_CIDRS', '')
    maint_cf_host = os.environ.get('MAINT_CF_HOST', '')
    
    # Parse allowed CIDRs
    allow_cidrs = [cidr.strip() for cidr in allow_cidrs_str.split(',') if cidr.strip()]
    
    # Always inject viewer IP header
    if 'headers' not in request:
        request['headers'] = {}
    
    request['headers']['x-viewer-ip'] = [{
        'key': 'X-Viewer-IP',
        'value': client_ip
    }]
    
    # If gate is disabled, pass through to origin
    if not gate_enabled:
        return request
    
    # Check if IP is in allowlist
    ip_allowed = False
    try:
        client_ip_obj = ipaddress.ip_address(client_ip)
        for cidr in allow_cidrs:
            try:
                network = ipaddress.ip_network(cidr, strict=False)
                if client_ip_obj in network:
                    ip_allowed = True
                    break
            except (ValueError, ipaddress.AddressValueError):
                # Invalid CIDR, skip
                continue
    except (ValueError, ipaddress.AddressValueError):
        # Invalid client IP, block by default
        ip_allowed = False
    
    # If IP is allowed, pass through to origin
    if ip_allowed:
        return request
    
    # IP not allowed - redirect to maintenance site
    if not maint_cf_host:
        # Safety: if maintenance host not configured, pass through with warning
        # In production, you might want to return a fixed error response instead
        return request
    
    # Rewrite origin to maintenance CloudFront distribution
    request['origin'] = {
        'custom': {
            'domainName': maint_cf_host,
            'port': 443,
            'protocol': 'https',
            'path': '',
            'sslProtocols': ['TLSv1.2'],
            'readTimeout': 30,
            'keepaliveTimeout': 5,
            'customHeaders': {}
        }
    }
    
    # Update Host header to match new origin
    request['headers']['host'] = [{
        'key': 'Host',
        'value': maint_cf_host
    }]
    
    # Normalize URI - redirect directory requests to index.html
    uri = request.get('uri', '/')
    if uri.endswith('/'):
        request['uri'] = uri + 'index.html'
    elif '.' not in uri.split('/')[-1]:
        # No file extension, likely a directory
        request['uri'] = uri + '/index.html'
    
    return request
