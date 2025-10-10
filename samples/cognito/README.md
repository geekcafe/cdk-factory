# Cognito App Clients - Sample Configurations

This directory contains sample configurations for Cognito User Pools with different app client types.

## Sample: app_clients_sample.json

Complete configuration demonstrating **4 different app client types**:

### 1. 🎨 Amplify Web App (No OAuth)

```json
{
  "name": "amplify-web-app",
  "generate_secret": false,
  "auth_flows": {
    "user_srp": true
  }
}
```

**Use for:**
- AWS Amplify applications
- React/Vue/Angular apps with Amplify UI
- Any SDK-based authentication
- Custom login UI

**Why no OAuth?**
- Amplify calls Cognito APIs directly (InitiateAuth, RespondToAuthChallenge)
- No browser redirects needed
- Simpler configuration
- Tokens managed by SDK

**Frontend Example:**
```typescript
import { Amplify } from 'aws-amplify';
import { signIn } from '@aws-amplify/auth';

Amplify.configure({
  Auth: {
    userPoolId: 'us-east-1_XXXXXXXXX',
    userPoolClientId: 'your-amplify-client-id'
  }
});

await signIn({ username, password });
```

---

### 2. 🌐 OAuth Web App (With Hosted UI)

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
    "callback_urls": ["https://example.com/callback"]
  }
}
```

**Use for:**
- Cognito Hosted UI
- Social login (Google, Facebook, Apple)
- OAuth 2.0 compliance requirements
- Want Cognito to handle login pages

**Why OAuth?**
- Uses standard OAuth 2.0 authorization code flow
- Requires callback URLs for redirects
- Built-in login UI from Cognito
- Social identity provider integration

---

### 3. 📱 Mobile App

```json
{
  "name": "mobile-app",
  "generate_secret": false,
  "auth_flows": {
    "user_srp": true,
    "custom": true
  },
  "oauth": {
    "callback_urls": ["myapp://callback"]
  },
  "refresh_token_validity": {
    "days": 90
  }
}
```

**Use for:**
- iOS/Android native apps
- React Native apps
- Flutter apps

**Features:**
- Custom URL schemes for deep links
- Longer refresh token validity (better UX)
- Support for custom auth (passwordless)

---

### 4. 🔧 Backend Service (Confidential Client)

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
    }
  }
}
```

**Use for:**
- Microservices
- Backend APIs
- Server-to-server communication
- Administrative tools

**Features:**
- Client secret automatically stored in Secrets Manager
- Admin auth flow (requires AWS credentials)
- Client credentials for machine-to-machine auth
- Shorter token validity for security

---

## Key Differences: OAuth vs Direct Auth

### When to Skip OAuth (No callback_urls):

✅ **Use Direct Auth for:**
- AWS Amplify applications
- Mobile apps with SDKs
- Custom login UI in your app
- Backend services
- Simple username/password auth

**Configuration:**
```json
{
  "auth_flows": {
    "user_srp": true
  }
  // No oauth section!
}
```

### When to Use OAuth (With callback_urls):

✅ **Use OAuth for:**
- Cognito Hosted UI
- Social login (Google, Facebook, etc.)
- OAuth 2.0 compliance
- Standard authorization code flow

**Configuration:**
```json
{
  "auth_flows": {
    "user_srp": true
  },
  "oauth": {
    "flows": {
      "authorization_code_grant": true
    },
    "callback_urls": ["https://myapp.com/callback"]
  }
}
```

---

## Quick Start

### Deploy the Sample

```bash
# Deploy the complete sample with all 4 app clients
cdk deploy -c config=samples/cognito/app_clients_sample.json
```

### Retrieve Client IDs

```bash
# List all app client IDs from SSM
aws ssm get-parameters-by-path \
  --path "/my-app/prod/cognito/user-pool" \
  --recursive

# Get specific client ID
aws ssm get-parameter \
  --name "/my-app/prod/cognito/user-pool/app_client_amplify_web_app_id" \
  --query Parameter.Value \
  --output text
```

### Retrieve Backend Service Secret

```bash
# Get full credentials from Secrets Manager
aws secretsmanager get-secret-value \
  --secret-id "my-deployment/cognito/backend-service/credentials" \
  --query SecretString \
  --output text | jq
```

---

## Common Use Cases

### React + Amplify (Recommended)

```json
{
  "name": "react-app",
  "auth_flows": {
    "user_srp": true
  }
}
```

No OAuth needed! Use Amplify UI components.

### Next.js + Hosted UI

```json
{
  "name": "nextjs-app",
  "auth_flows": {
    "user_srp": true
  },
  "oauth": {
    "flows": {
      "authorization_code_grant": true
    },
    "callback_urls": [
      "https://myapp.com/api/auth/callback"
    ]
  }
}
```

OAuth required for Hosted UI redirects.

### React Native Mobile App

```json
{
  "name": "mobile-app",
  "auth_flows": {
    "user_srp": true
  },
  "oauth": {
    "callback_urls": ["myapp://auth"]
  },
  "refresh_token_validity": {
    "days": 90
  }
}
```

Deep links for social login, long refresh tokens for UX.

### Python Backend Service

```json
{
  "name": "python-api",
  "generate_secret": true,
  "auth_flows": {
    "admin_user_password": true
  }
}
```

Server-side auth with AWS credentials.

---

## Testing

### Test Amplify Client

```typescript
import { signIn } from '@aws-amplify/auth';

const user = await signIn({
  username: 'user@example.com',
  password: 'password123'
});

console.log('Access Token:', user.signInUserSession.accessToken.jwtToken);
```

### Test OAuth Client

```bash
# Get authorization code
https://my-app-users.auth.us-east-1.amazoncognito.com/oauth2/authorize?
  client_id=YOUR_CLIENT_ID&
  response_type=code&
  scope=email+openid+profile&
  redirect_uri=https://myapp.com/callback

# Exchange code for tokens
curl -X POST https://my-app-users.auth.us-east-1.amazoncognito.com/oauth2/token \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=authorization_code&client_id=YOUR_CLIENT_ID&code=AUTH_CODE&redirect_uri=https://myapp.com/callback"
```

### Test Backend Service

```python
import boto3
import json

# Get credentials from Secrets Manager
secrets = boto3.client('secretsmanager')
response = secrets.get_secret_value(
    SecretId='my-deployment/cognito/backend-service/credentials'
)
creds = json.loads(response['SecretString'])

# Authenticate
cognito = boto3.client('cognito-idp')
response = cognito.admin_initiate_auth(
    UserPoolId=creds['user_pool_id'],
    ClientId=creds['client_id'],
    AuthFlow='ADMIN_USER_PASSWORD_AUTH',
    AuthParameters={
        'USERNAME': 'user@example.com',
        'PASSWORD': 'password123'
    }
)

print('Tokens:', response['AuthenticationResult'])
```

---

## Related Documentation

- [Full App Clients Guide](../../docs/cognito_app_clients.md)
- [Implementation Details](../../docs/COGNITO_APP_CLIENTS_IMPLEMENTATION.md)
- [AWS Amplify Documentation](https://docs.amplify.aws/)
- [Cognito OAuth Documentation](https://docs.aws.amazon.com/cognito/latest/developerguide/cognito-user-pools-app-integration.html)
