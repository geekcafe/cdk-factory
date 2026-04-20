# Cognito App Clients

## Overview

The Cognito stack now supports creating multiple app clients per user pool, each with different authentication flows and OAuth configurations. This is essential for supporting web apps, mobile apps, and backend services with different security requirements.

## Features

✅ **Multiple App Clients** - Create unlimited app clients per user pool  
✅ **Client Secrets** - Optional client secret generation for confidential clients  
✅ **Auth Flows** - Support for USER_PASSWORD_AUTH, USER_SRP_AUTH, CUSTOM_AUTH, ADMIN_USER_PASSWORD_AUTH  
✅ **OAuth 2.0** - Full OAuth flow support (Authorization Code, Implicit, Client Credentials)  
✅ **Custom Scopes** - Standard scopes (email, openid, profile) + custom scopes  
✅ **Token Validity** - Configurable access, ID, and refresh token expiry  
✅ **Attributes** - Control read/write permissions for user attributes  
✅ **Identity Providers** - Support for COGNITO, Google, Facebook, Amazon, Apple  
✅ **SSM Export** - Automatic export of client IDs to SSM Parameter Store  

## Configuration

### Basic App Client

```json
{
  "cognito": {
    "user_pool_name": "my-app-users",
    "app_clients": [
      {
        "name": "web-app",
        "generate_secret": false,
        "auth_flows": {
          "user_srp": true
        }
      }
    ]
  }
}
```

### Complete App Client Configuration

```json
{
  "name": "web-app",
  "generate_secret": false,
  "auth_flows": {
    "user_password": true,
    "user_srp": true,
    "custom": false,
    "admin_user_password": false
  },
  "oauth": {
    "flows": {
      "authorization_code_grant": true,
      "implicit_code_grant": false,
      "client_credentials": false
    },
    "scopes": ["email", "openid", "profile"],
    "callback_urls": ["https://example.com/callback"],
    "logout_urls": ["https://example.com/logout"]
  },
  "supported_identity_providers": ["COGNITO"],
  "prevent_user_existence_errors": true,
  "enable_token_revocation": true,
  "access_token_validity": {"minutes": 60},
  "id_token_validity": {"minutes": 60},
  "refresh_token_validity": {"days": 30},
  "read_attributes": ["email", "name"],
  "write_attributes": ["name"]
}
```

## App Client Types

### 1. Web Application (Public Client)

```json
{
  "name": "web-app",
  "generate_secret": false,
  "auth_flows": {
    "user_srp": true
  },
  "oauth": {
    "flows": {
      "authorization_code_grant": true
    },
    "scopes": ["email", "openid", "profile"],
    "callback_urls": ["https://myapp.com/callback"]
  }
}
```

**Use Case**: Browser-based single-page applications (React, Vue, Angular)  
**Security**: No client secret (public client)  
**Auth Flow**: Authorization Code Grant with PKCE

### 2. Mobile Application

```json
{
  "name": "mobile-app",
  "generate_secret": false,
  "auth_flows": {
    "user_srp": true
  },
  "oauth": {
    "flows": {
      "authorization_code_grant": true
    },
    "scopes": ["email", "openid", "profile"],
    "callback_urls": ["myapp://callback"]
  },
  "refresh_token_validity": {"days": 90}
}
```

**Use Case**: iOS/Android native mobile apps  
**Security**: No client secret (public client)  
**Auth Flow**: Authorization Code Grant with PKCE  
**Note**: Longer refresh token validity for mobile UX

### 3. Backend Service (Confidential Client)

```json
{
  "name": "backend-service",
  "generate_secret": true,
  "auth_flows": {
    "admin_user_password": true
  },
  "oauth": {
    "flows": {
      "client_credentials": true
    },
    "scopes": ["api/read", "api/write"]
  },
  "access_token_validity": {"minutes": 30}
}
```

**Use Case**: Server-to-server communication, microservices  
**Security**: Client secret required (confidential client)  
**Auth Flow**: Client Credentials Grant  
**Note**: Shorter token validity for server-side security

### 4. Admin/Management Client

```json
{
  "name": "admin-client",
  "generate_secret": true,
  "auth_flows": {
    "admin_user_password": true
  },
  "oauth": {
    "flows": {
      "authorization_code_grant": true
    },
    "scopes": ["email", "openid", "profile", "cognito_admin"]
  }
}
```

**Use Case**: Administrative interfaces, user management  
**Security**: Client secret + admin permissions  
**Auth Flow**: Authorization Code Grant with elevated permissions

## Authentication Flows

### Available Auth Flows

| Flow | Parameter | Use Case |
|------|-----------|----------|
| **USER_SRP_AUTH** | `user_srp: true` | Secure Remote Password protocol (recommended) |
| **USER_PASSWORD_AUTH** | `user_password: true` | Direct username/password (less secure) |
| **CUSTOM_AUTH** | `custom: true` | Custom Lambda-based authentication |
| **ADMIN_USER_PASSWORD_AUTH** | `admin_user_password: true` | Server-side admin authentication |

### Recommended Combinations

**Web/Mobile Apps:**
```json
{
  "auth_flows": {
    "user_srp": true
  }
}
```

**Backend Services:**
```json
{
  "auth_flows": {
    "admin_user_password": true
  }
}
```

**Testing/Development:**
```json
{
  "auth_flows": {
    "user_password": true,
    "user_srp": true
  }
}
```

## OAuth Configuration

### OAuth Flows

```json
{
  "oauth": {
    "flows": {
      "authorization_code_grant": true,    // Standard for web/mobile
      "implicit_code_grant": false,        // Legacy (not recommended)
      "client_credentials": false          // For machine-to-machine
    }
  }
}
```

### OAuth Scopes

**Standard Scopes:**
- `"openid"` - Required for OIDC
- `"email"` - Access to email address
- `"phone"` - Access to phone number
- `"profile"` - Access to profile information
- `"cognito_admin"` - Admin API access

**Custom Scopes:**
```json
{
  "oauth": {
    "scopes": ["email", "openid", "api/read", "api/write"]
  }
}
```

Custom scopes must be defined at the Resource Server level.

### Callback URLs

**When Callback URLs are Required:**
- ✅ OAuth authorization code flow
- ✅ OAuth implicit flow
- ✅ Hosted UI (Cognito built-in login pages)
- ✅ Social identity providers (Google, Facebook, etc.)

**When Callback URLs are NOT Required:**
- ❌ Using AWS Amplify UI components (handles auth internally)
- ❌ Direct auth flows (USER_SRP_AUTH, USER_PASSWORD_AUTH)
- ❌ Custom auth flows without OAuth
- ❌ Backend services using admin or client credentials flows
- ❌ Mobile apps using SDK-based authentication (without OAuth)

**Example: Web App with AWS Amplify**
```json
{
  "name": "amplify-web-app",
  "generate_secret": false,
  "auth_flows": {
    "user_srp": true
  }
  // No oauth configuration needed - Amplify handles auth directly
}
```

**Example: OAuth-Based Web App**
```json
{
  "name": "oauth-web-app",
  "generate_secret": false,
  "auth_flows": {
    "user_srp": true
  },
  "oauth": {
    "flows": {
      "authorization_code_grant": true
    },
    "scopes": ["email", "openid", "profile"],
    "callback_urls": [
      "https://myapp.com/callback",
      "http://localhost:3000/callback"  // For development
    ],
    "logout_urls": [
      "https://myapp.com/logout",
      "http://localhost:3000/logout"
    ]
  }
}
```

**Example: Mobile App with Deep Links**
```json
{
  "oauth": {
    "callback_urls": ["myapp://callback"],  // Custom URL scheme
    "logout_urls": ["myapp://logout"]
  }
}
```

### Amplify and SDK-Based Authentication

**AWS Amplify** and similar frameworks (Auth0 UI, Firebase Auth, etc.) handle authentication **without requiring OAuth callback URLs** because they:
- Use direct authentication API calls (InitiateAuth, RespondToAuthChallenge)
- Manage token storage and refresh internally
- Don't redirect through OAuth authorization endpoints
- Handle MFA and custom challenges programmatically

**Amplify Example (No OAuth needed):**
```typescript
// Frontend code using Amplify
import { Amplify } from 'aws-amplify';
import { signIn, signOut } from '@aws-amplify/auth';

Amplify.configure({
  Auth: {
    userPoolId: 'us-east-1_XXXXXXXXX',
    userPoolClientId: 'your-client-id',
    // No callback URLs needed!
  }
});

// Sign in directly
await signIn({ username, password });
```

**Configuration for Amplify:**
```json
{
  "name": "amplify-client",
  "generate_secret": false,
  "auth_flows": {
    "user_srp": true,
    "user_password": true  // Optional fallback
  }
  // OAuth section completely optional
}
```

**When to Use OAuth with Callback URLs:**
- Using Cognito Hosted UI
- Implementing social login (Google, Facebook)
- Need OAuth authorization code flow for security compliance
- Using third-party OAuth providers
- Redirecting users to a login page

## Token Validity

Control how long tokens are valid:

```json
{
  "access_token_validity": {"minutes": 60},
  "id_token_validity": {"minutes": 60},
  "refresh_token_validity": {"days": 30}
}
```

### Validity Units

Supports `minutes`, `hours`, or `days`:

```json
{"minutes": 30}
{"hours": 2}
{"days": 90}
```

### Recommended Settings

| Client Type | Access Token | ID Token | Refresh Token |
|-------------|--------------|----------|---------------|
| Web App | 60 min | 60 min | 30 days |
| Mobile App | 60 min | 60 min | 90 days |
| Backend Service | 30 min | N/A | 1 day |

## Attribute Permissions

Control which user attributes the client can read/write:

```json
{
  "read_attributes": [
    "email",
    "email_verified",
    "name",
    "given_name",
    "family_name",
    "phone_number"
  ],
  "write_attributes": [
    "name",
    "given_name",
    "family_name"
  ]
}
```

### Standard Attributes

- `address`, `birthdate`, `email`, `email_verified`
- `family_name`, `gender`, `given_name`
- `locale`, `middle_name`, `name`, `nickname`
- `phone_number`, `phone_number_verified`
- `picture`, `preferred_username`, `profile`
- `timezone`, `updated_at`, `website`

### Custom Attributes

Custom attributes are automatically detected and included:

```json
{
  "read_attributes": [
    "email",
    "custom:department",
    "custom:employee_id"
  ]
}
```

## Identity Providers

Support for social and enterprise identity providers:

```json
{
  "supported_identity_providers": [
    "COGNITO",     // Cognito user pool
    "Google",      // Google Sign-In
    "Facebook",    // Facebook Login
    "Amazon",      // Login with Amazon
    "Apple",       // Sign in with Apple
    "CustomSAML"   // Custom SAML provider
  ]
}
```

## Client Secret Management

### Automatic Secrets Manager Storage

**Good news!** Client secrets are **automatically stored in AWS Secrets Manager** when you set `generate_secret: true`.

```json
{
  "name": "backend-service",
  "generate_secret": true  // ✅ Automatically stored in Secrets Manager
}
```

### What Gets Created

For each app client with `generate_secret: true`, the stack creates:

**1. Credentials Secret** (Recommended)
- **Name**: `/{deployment}/cognito/{client-name}/credentials`
- **Format**: JSON object with all credentials
- **Contents**:
  ```json
  {
    "client_id": "1234567890abcdef",
    "client_secret": "secret-value-here",
    "user_pool_id": "us-east-1_XXXXXXXXX"
  }
  ```

**2. Secret-Only Secret** (Legacy)
- **Name**: `/{deployment}/cognito/{client-name}/client-secret`
- **Format**: Plain text client secret
- **Contents**: Just the secret value

**3. SSM Parameter** (For cross-stack reference)
- **Name**: `/{org}/{env}/cognito/user-pool/app_client_{name}_secret_arn`
- **Value**: ARN of the credentials secret in Secrets Manager

### Retrieving Client Secrets

**From Your Application (Recommended)**

```python
import boto3
import json

secrets_client = boto3.client('secretsmanager')

# Get credentials from Secrets Manager
response = secrets_client.get_secret_value(
    SecretId='my-deployment/cognito/backend-service/credentials'
)

credentials = json.loads(response['SecretString'])
client_id = credentials['client_id']
client_secret = credentials['client_secret']
user_pool_id = credentials['user_pool_id']
```

**From AWS CLI**

```bash
# Get full credentials JSON
aws secretsmanager get-secret-value \
  --secret-id "my-deployment/cognito/backend-service/credentials" \
  --query SecretString \
  --output text | jq

# Get just the client secret
aws secretsmanager get-secret-value \
  --secret-id "my-deployment/cognito/backend-service/client-secret" \
  --query SecretString \
  --output text
```

**From AWS Console**
1. Go to AWS Secrets Manager
2. Find secret: `{deployment}/cognito/{client-name}/credentials`
3. Click "Retrieve secret value"

### Cross-Stack Access

The secret ARN is exported to SSM for easy cross-stack reference:

```python
# In another stack, import the secret ARN
secret_arn = ssm.StringParameter.value_from_lookup(
    self,
    parameter_name="/my-app/prod/cognito/user-pool/app_client_backend_service_secret_arn"
)

# Import the secret
secret = secretsmanager.Secret.from_secret_complete_arn(
    self, "ImportedSecret", secret_arn
)

# Use in Lambda environment variables
my_lambda.add_environment("COGNITO_SECRET_ARN", secret.secret_arn)

# Grant read permissions
secret.grant_read(my_lambda)
```

## SSM Parameter Export

App client IDs are automatically exported to SSM when SSM is enabled:

```json
{
  "cognito": {
    "ssm": {
      "enabled": true,
      "organization": "my-app",
      "environment": "prod"
    }
  }
}
```

### Exported Parameters

**User Pool:**
- `/{org}/{env}/cognito/user-pool/user_pool_id`
- `/{org}/{env}/cognito/user-pool/user_pool_arn`

**App Clients:**
- `/{org}/{env}/cognito/user-pool/app_client_web_app_id`
- `/{org}/{env}/cognito/user-pool/app_client_mobile_app_id`
- `/{org}/{env}/cognito/user-pool/app_client_backend_service_id`

**Client Secrets (if generate_secret: true):**
- `/{org}/{env}/cognito/user-pool/app_client_backend_service_secret_arn`

The secret ARN points to the Secrets Manager secret containing the full credentials (client_id, client_secret, user_pool_id).

## Security Best Practices

### 1. Use Client Secrets for Server-Side Clients

```json
{
  "name": "backend-service",
  "generate_secret": true  // ✅ Required for confidential clients
}
```

### 2. Never Use Client Secrets in Browser/Mobile Apps

```json
{
  "name": "web-app",
  "generate_secret": false  // ✅ Correct for public clients
}
```

### 3. Use SRP Auth Flow When Possible

```json
{
  "auth_flows": {
    "user_srp": true,        // ✅ More secure
    "user_password": false   // ❌ Avoid if possible
  }
}
```

### 4. Enable Token Revocation

```json
{
  "enable_token_revocation": true  // ✅ Always enable
}
```

### 5. Minimize Token Validity

```json
{
  "access_token_validity": {"minutes": 60},  // ✅ Short-lived
  "refresh_token_validity": {"days": 30}     // ✅ Reasonable duration
}
```

### 6. Prevent User Existence Errors

```json
{
  "prevent_user_existence_errors": true  // ✅ Prevents user enumeration
}
```

## Complete Example

See `samples/cognito/app_clients_sample.json` for a complete configuration with:
- Web application client (public)
- Mobile application client (public)
- Backend service client (confidential)

## Troubleshooting

### Client Secret Not Available

**Problem**: Need to retrieve client secret after deployment

**Solution**: Client secrets are automatically stored in AWS Secrets Manager! Retrieve from:

```bash
# Get full credentials from Secrets Manager
aws secretsmanager get-secret-value \
  --secret-id "{deployment}/cognito/{client-name}/credentials" \
  --query SecretString --output text | jq

# Or get from Cognito directly
aws cognito-idp describe-user-pool-client \
  --user-pool-id <pool-id> \
  --client-id <client-id> \
  --query 'UserPoolClient.ClientSecret' --output text
```

### OAuth Flow Not Working

**Problem**: OAuth redirects failing

**Solution**: Verify callback URLs match exactly:
- Include protocol (https://)
- Match port numbers
- No trailing slashes unless needed

### Token Expired Too Quickly

**Problem**: Users getting logged out frequently

**Solution**: Increase token validity:
```json
{
  "access_token_validity": {"hours": 2},
  "refresh_token_validity": {"days": 90}
}
```

### Client Credentials Flow Failing

**Problem**: Machine-to-machine auth not working

**Solution**: Ensure client secret is generated and OAuth flow is configured:
```json
{
  "generate_secret": true,
  "oauth": {
    "flows": {
      "client_credentials": true
    }
  }
}
```

## Migration from Existing Setup

If you already have a Cognito User Pool without app clients:

1. Add `app_clients` to your configuration
2. Deploy the stack
3. Update your application code with new client IDs
4. Remove old manually-created clients (optional)

## Related Documentation

- [Cognito Stack Documentation](./cognito_stack.md)
- [SSM Parameter Sharing](./ssm_parameter_pattern.md)
- [AWS Cognito App Clients](https://docs.aws.amazon.com/cognito/latest/developerguide/user-pool-settings-client-apps.html)
