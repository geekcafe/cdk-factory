# ALB Listener Default Action Configuration

## Problem

The ALB listener `default_action` was **hardcoded to return 404**, ignoring any custom `default_action` specified in the configuration.

### Example Issue

**Your Config:**
```json
{
  "name": "https",
  "port": 443,
  "protocol": "HTTPS",
  "default_action": {
    "type": "fixed-response",
    "fixed_response": {
      "status_code": "403",
      "content_type": "text/html",
      "message_body": "<html><body><h1>Access Denied</h1></body></html>"
    }
  }
}
```

**What Happened:**
- Config specified `403 Access Denied`
- Code returned `404 Not Found` (hardcoded)
- Your security configuration was ignored!

## Solution

**Added `_parse_listener_action()` method** that reads the `default_action` from your config and applies it correctly.

### How It Works

The listener creation now follows this logic:

1. **If you have a `default_target_group`:** Routes to that target group (existing behavior)
2. **If you specify `default_action` in config:** Uses your configured action
3. **If neither:** Falls back to `404 Not Found` (backward compatible)

## Configuration

### Fixed Response (Most Common)

Return a static HTTP response when no rules match:

```json
{
  "listeners": [
    {
      "name": "https",
      "port": 443,
      "protocol": "HTTPS",
      "default_action": {
        "type": "fixed-response",
        "fixed_response": {
          "status_code": "403",
          "content_type": "text/html",
          "message_body": "<html><body><h1>Access Denied</h1><p>Missing required authentication header.</p></body></html>"
        }
      }
    }
  ]
}
```

**Use Cases:**
- **403:** Security - require specific headers/conditions
- **404:** Standard not found
- **503:** Maintenance mode
- **Custom HTML:** Branded error pages

### Forward to Target Group

Route all unmatched traffic to a specific target group:

```json
{
  "listeners": [
    {
      "name": "https",
      "port": 443,
      "protocol": "HTTPS",
      "default_action": {
        "type": "forward",
        "target_group": "default-tg"
      }
    }
  ]
}
```

**Note:** This is equivalent to using `default_target_group` but allows more explicit configuration.

## Common Patterns

### Secure ALB Behind CloudFront

Only allow requests with `X-Origin-Secret` header:

```json
{
  "default_action": {
    "type": "fixed-response",
    "fixed_response": {
      "status_code": "403",
      "content_type": "text/html",
      "message_body": "<html><body><h1>Access Denied</h1><p>Direct access not allowed.</p></body></html>"
    }
  },
  "rules": [
    {
      "priority": 1,
      "conditions": [
        {
          "field": "http-header",
          "http_header_config": {
            "header_name": "X-Origin-Secret",
            "values": ["{{X_ORIGIN_SECRET}}"]
          }
        }
      ],
      "actions": [
        {
          "type": "forward",
          "target_group": "primary-tg"
        }
      ]
    }
  ]
}
```

**Result:**
- ✅ Request with correct header → Priority 1 matches → Forwarded to `primary-tg`
- ❌ Request without header → No rules match → Default 403 action fires

### Custom 404 Page

Return a branded 404 page:

```json
{
  "default_action": {
    "type": "fixed-response",
    "fixed_response": {
      "status_code": "404",
      "content_type": "text/html",
      "message_body": "<html><body><h1>Page Not Found</h1><p>The page you're looking for doesn't exist.</p></body></html>"
    }
  }
}
```

### Maintenance Mode

Return 503 with custom message:

```json
{
  "default_action": {
    "type": "fixed-response",
    "fixed_response": {
      "status_code": "503",
      "content_type": "text/html",
      "message_body": "<html><body><h1>Maintenance</h1><p>We'll be back soon!</p></body></html>"
    }
  }
}
```

## Migration

### Before (0.35.0 and earlier)
```json
{
  "listeners": [
    {
      "name": "https",
      "port": 443,
      "protocol": "HTTPS"
      // No default_action - always returned 404
    }
  ]
}
```

**Result:** Always returned `404 Not Found`

### After (0.36.0+)
```json
{
  "listeners": [
    {
      "name": "https",
      "port": 443,
      "protocol": "HTTPS"
      // No default_action - still returns 404 (backward compatible)
    }
  ]
}
```

**Result:** Returns `404 Not Found` (same behavior)

**To change:**
```json
{
  "listeners": [
    {
      "name": "https",
      "port": 443,
      "protocol": "HTTPS",
      "default_action": {
        "type": "fixed-response",
        "fixed_response": {
          "status_code": "403",
          "content_type": "text/html",
          "message_body": "<html><body><h1>Access Denied</h1></body></html>"
        }
      }
    }
  ]
}
```

**Result:** Returns your configured `403 Access Denied`

## Implementation Details

### Method: `_parse_listener_action()`

Parses action config and returns CDK `ListenerAction`:

```python
def _parse_listener_action(self, action_config: Dict[str, Any]) -> elbv2.ListenerAction:
    """Parse a listener action from configuration."""
    action_type = action_config.get("type", "fixed-response")
    
    if action_type == "fixed-response":
        fixed_response = action_config.get("fixed_response", {})
        return elbv2.ListenerAction.fixed_response(
            status_code=int(fixed_response.get("status_code", 404)),
            content_type=fixed_response.get("content_type", "text/plain"),
            message_body=fixed_response.get("message_body", "Not Found"),
        )
    elif action_type == "forward":
        target_group_name = action_config.get("target_group")
        if target_group_name and target_group_name in self.target_groups:
            return elbv2.ListenerAction.forward([self.target_groups[target_group_name]])
        else:
            raise ValueError(f"Target group '{target_group_name}' not found")
    else:
        raise ValueError(f"Unsupported action type: {action_type}")
```

### Listener Creation Logic

```python
# Determine default action from config or use default target group
default_action = None
if default_target_group:
    # If there's a default target group, CDK will use it automatically
    default_action = None
else:
    # Check if config specifies a custom default_action
    default_action_config = listener_config.get("default_action")
    if default_action_config:
        default_action = self._parse_listener_action(default_action_config)
    else:
        # Fallback to 404 if no config provided
        default_action = elbv2.ListenerAction.fixed_response(
            status_code=404,
            content_type="text/plain",
            message_body="Not Found",
        )
```

## Benefits

- ✅ Configure custom default responses (403, 503, etc.)
- ✅ Implement security patterns (header validation)
- ✅ Custom error pages with HTML
- ✅ Backward compatible (still defaults to 404)
- ✅ Explicit configuration instead of hardcoded values

## Version

- **Added:** 2025-11-18
- **Version:** 0.36.0
- **Related:** Also added `enabled` field support for ALB listener rules
