# Requirements Document

## Introduction

The Cognito CDK stack currently exports SSM parameters for all app clients under a single top-level `ssm.namespace` (e.g., `/acme-saas/beta/cognito/app_client_nca_web_app_id`). When multiple consuming applications share a Cognito User Pool but each needs to discover its own client ID under its own SSM path, there is no way to configure per-client SSM namespaces. This feature adds an optional `ssm_namespace` field to each app client configuration, allowing individual clients to export their SSM parameters to application-specific paths while preserving the existing pool-level namespace as the default.

## Glossary

- **Cognito_Stack**: The CDK stack class (`CognitoStack`) that provisions a Cognito User Pool, app clients, and exports SSM parameters.
- **CognitoConfig**: The Pydantic-style configuration model (`CognitoConfig`) that parses the `cognito` block from stack JSON configuration.
- **App_Client**: A Cognito User Pool Client entry defined in the `app_clients` array of the cognito configuration.
- **SSM_Namespace**: A slash-delimited path prefix used to organize SSM Parameter Store exports (e.g., `nca-web/beta/auth`).
- **Pool_Level_Namespace**: The existing `ssm.namespace` value defined at the top level of the stack configuration, used as the default export path for all Cognito resources.
- **Client_Level_Namespace**: An optional `ssm_namespace` value defined on an individual app client entry, overriding the Pool_Level_Namespace for that client's SSM exports.
- **Safe_Client_Name**: A sanitized version of the app client name where hyphens and spaces are replaced with underscores (e.g., `nca-web-app` becomes `nca_web_app`).
- **Stack_Config**: The top-level stack configuration object (`StackConfig`) that holds the `ssm` block including `namespace` and `auto_export`.

## Requirements

### Requirement 1: Per-Client SSM Namespace Configuration

**User Story:** As a platform engineer, I want to specify an optional SSM namespace on each app client, so that different consuming applications can discover their Cognito client ID under their own SSM path.

#### Acceptance Criteria

1. WHERE an App_Client entry includes an `ssm_namespace` field, THE CognitoConfig SHALL expose that value via a property on the parsed client configuration.
2. WHERE an App_Client entry does not include an `ssm_namespace` field, THE CognitoConfig SHALL return `None` for that client's SSM namespace property.
3. THE CognitoConfig SHALL accept `ssm_namespace` as an optional string field in each element of the `app_clients` array.

### Requirement 2: Client-Level SSM Parameter Export

**User Story:** As a platform engineer, I want app client SSM parameters exported under the client-level namespace when one is specified, so that each consuming application has a predictable SSM path for its credentials.

#### Acceptance Criteria

1. WHEN `ssm.auto_export` is true AND an App_Client specifies a Client_Level_Namespace, THE Cognito_Stack SHALL export that client's ID to `/{Client_Level_Namespace}/app_client_{Safe_Client_Name}_id`.
2. WHEN `ssm.auto_export` is true AND an App_Client specifies a Client_Level_Namespace AND the client has `generate_secret` set to true, THE Cognito_Stack SHALL export that client's secret ARN to `/{Client_Level_Namespace}/app_client_{Safe_Client_Name}_secret_arn`.
3. WHEN `ssm.auto_export` is true AND an App_Client does not specify a Client_Level_Namespace, THE Cognito_Stack SHALL export that client's parameters under the Pool_Level_Namespace as `/{Pool_Level_Namespace}/app_client_{Safe_Client_Name}_id`.

### Requirement 3: Pool-Level Parameters Remain Unaffected

**User Story:** As a platform engineer, I want pool-level SSM parameters (user pool ID, ARN, name) to always export under the pool-level namespace, so that existing consumers are not disrupted.

#### Acceptance Criteria

1. WHEN `ssm.auto_export` is true, THE Cognito_Stack SHALL export `user_pool_id`, `user_pool_arn`, and `user_pool_name` under the Pool_Level_Namespace regardless of any Client_Level_Namespace values.
2. WHEN an App_Client specifies a Client_Level_Namespace, THE Cognito_Stack SHALL continue to export pool-level parameters under the Pool_Level_Namespace without duplication or omission.

### Requirement 4: Multiple Clients with Different Namespaces

**User Story:** As a platform engineer, I want to configure multiple app clients where each can have a different SSM namespace, so that a single Cognito User Pool can serve several applications with isolated SSM paths.

#### Acceptance Criteria

1. WHEN two or more App_Clients each specify distinct Client_Level_Namespace values, THE Cognito_Stack SHALL export each client's parameters under its respective namespace without conflict.
2. WHEN one App_Client specifies a Client_Level_Namespace and another does not, THE Cognito_Stack SHALL export the first client's parameters under its Client_Level_Namespace and the second client's parameters under the Pool_Level_Namespace.

### Requirement 5: Backward Compatibility

**User Story:** As a platform engineer, I want existing configurations without `ssm_namespace` on app clients to continue working identically, so that no migration or changes are required for current deployments.

#### Acceptance Criteria

1. WHEN no App_Client entries in the configuration include an `ssm_namespace` field, THE Cognito_Stack SHALL export all parameters identically to the current behavior using only the Pool_Level_Namespace.
2. THE CognitoConfig SHALL not require `ssm_namespace` in the app client schema, treating it as fully optional with no default value.

### Requirement 6: Configuration Validation

**User Story:** As a platform engineer, I want clear error feedback when the SSM namespace configuration is invalid, so that I can fix misconfigurations before deployment.

#### Acceptance Criteria

1. IF an App_Client specifies a Client_Level_Namespace AND `ssm.auto_export` is false AND no explicit `ssm.exports` are configured, THEN THE Cognito_Stack SHALL log a warning that the Client_Level_Namespace is ignored because auto-export is disabled.
2. IF an App_Client specifies a Client_Level_Namespace that is an empty string, THEN THE Cognito_Stack SHALL raise a ValueError with a descriptive message indicating that `ssm_namespace` must be a non-empty string or omitted entirely.

### Requirement 7: Sample Configuration and Documentation

**User Story:** As a platform engineer, I want an updated sample configuration demonstrating per-client SSM namespaces, so that I can understand the feature through a working example.

#### Acceptance Criteria

1. THE app clients sample JSON SHALL include at least one App_Client entry with an `ssm_namespace` field demonstrating the per-client namespace feature.
2. THE app clients sample JSON SHALL include at least one App_Client entry without an `ssm_namespace` field demonstrating the fallback to Pool_Level_Namespace behavior.
