# Load Balancer IP Whitelisting

The LoadBalancer stack supports IP whitelisting functionality to restrict access to your Application Load Balancer (ALB) based on source IP addresses.

## Overview

IP whitelisting allows you to:
- Block access from unauthorized IP addresses
- Allow access only from specific CIDR blocks
- Customize the response for blocked requests
- Apply restrictions across all listeners automatically

**Note**: IP whitelisting is only supported for Application Load Balancers (ALB), not Network Load Balancers (NLB).

## Configuration

Add the `ip_whitelist` section to your load balancer configuration:

```json
{
  "load_balancer": {
    "name": "secure-alb",
    "type": "APPLICATION",
    "ip_whitelist": {
      "enabled": true,
      "allowed_cidrs": [
        "203.0.113.0/24",
        "198.51.100.0/24",
        "192.0.2.0/24"
      ],
      "block_action": "fixed_response",
      "block_response": {
        "status_code": 403,
        "content_type": "text/html",
        "message_body": "<html><body><h1>Access Denied</h1></body></html>"
      }
    }
  }
}
```

## Configuration Properties

### `ip_whitelist.enabled`
- **Type**: Boolean
- **Default**: `false`
- **Description**: Enable or disable IP whitelisting functionality

### `ip_whitelist.allowed_cidrs`
- **Type**: Array of strings
- **Default**: `[]`
- **Description**: List of CIDR blocks that are allowed to access the load balancer
- **Examples**: 
  - `"192.168.1.0/24"` - Allow entire subnet
  - `"203.0.113.5/32"` - Allow single IP address
  - `"10.0.0.0/8"` - Allow private network range

### `ip_whitelist.block_action`
- **Type**: String
- **Default**: `"fixed_response"`
- **Description**: Action to take for blocked requests
- **Supported Values**: `"fixed_response"` (currently only option)

### `ip_whitelist.block_response`
- **Type**: Object
- **Description**: Configuration for the response sent to blocked requests

#### `block_response.status_code`
- **Type**: Integer
- **Default**: `403`
- **Description**: HTTP status code for blocked requests

#### `block_response.content_type`
- **Type**: String
- **Default**: `"text/plain"`
- **Description**: Content type of the response
- **Examples**: `"text/plain"`, `"text/html"`, `"application/json"`

#### `block_response.message_body`
- **Type**: String
- **Default**: `"Access Denied"`
- **Description**: Response body content for blocked requests

## How It Works

When IP whitelisting is enabled, the system creates two ALB listener rules:

1. **Allow Rule (Priority 1)**: Matches whitelisted IP addresses and forwards them to the configured target groups
2. **Block Rule (Priority 32000)**: Catches all other IP addresses and returns the configured block response

The rules are automatically applied to all HTTP and HTTPS listeners on the Application Load Balancer.

## Example Configurations

### Basic IP Whitelisting
```json
{
  "ip_whitelist": {
    "enabled": true,
    "allowed_cidrs": ["203.0.113.0/24"]
  }
}
```

### Custom Block Response
```json
{
  "ip_whitelist": {
    "enabled": true,
    "allowed_cidrs": ["203.0.113.0/24", "198.51.100.0/24"],
    "block_response": {
      "status_code": 404,
      "content_type": "application/json",
      "message_body": "{\"error\": \"Resource not found\"}"
    }
  }
}
```

### Multiple CIDR Blocks
```json
{
  "ip_whitelist": {
    "enabled": true,
    "allowed_cidrs": [
      "10.0.0.0/8",        // Private network
      "172.16.0.0/12",     // Private network
      "192.168.0.0/16",    // Private network
      "203.0.113.0/24"     // Public office network
    ]
  }
}
```

## Important Notes

1. **Application Load Balancer Only**: IP whitelisting is only supported for ALB, not NLB
2. **Rule Priorities**: The system uses priorities 1 and 32000 for whitelist rules. Ensure your custom listener rules use different priorities
3. **IPv6 Support**: The system supports both IPv4 and IPv6 CIDR blocks
4. **Performance**: IP whitelisting adds minimal latency as it's processed at the load balancer level
5. **Logging**: Blocked requests will appear in ALB access logs with the configured status code

## Troubleshooting

### Common Issues

1. **Rules Not Working**: Ensure `enabled` is set to `true` and `allowed_cidrs` is not empty
2. **Priority Conflicts**: Check that your custom listener rules don't use priorities 1 or 32000
3. **IPv6 Issues**: Make sure your CIDR blocks are properly formatted for IPv6 if needed

### Testing

To test IP whitelisting:

1. Deploy the load balancer with IP whitelisting enabled
2. Access from an allowed IP - should work normally
3. Access from a non-allowed IP - should receive the configured block response
4. Check ALB access logs to verify the behavior

## Security Considerations

- Use the most restrictive CIDR blocks possible
- Regularly review and update allowed IP ranges
- Consider using WAF for more advanced filtering capabilities
- Monitor access logs for blocked attempts
- Ensure your block response doesn't reveal sensitive information
