# Requirements Document

## Introduction

This feature eliminates route duplication between lambda configuration files and the API Gateway configuration. Currently, API routes are declared in two places: inline within each lambda resource config (`"api": {"route": "...", "method": "..."}`) and again in the API Gateway config (`api-gateway-primary.json` → `"routes": [...]`). The goal is to follow the same decentralized pattern already used for SQS — lambda configs are the single source of truth for their routes, and the API Gateway stack auto-discovers them. The API Gateway config retains only gateway-level settings (name, stage, CORS, custom domain, Cognito).

## Glossary

- **Lambda_Config**: A JSON configuration file defining a Lambda function's properties, including its `api` section with route metadata. Located under `configs/stacks/lambdas/` in the IaC project.
- **Resource_Config**: A JSON file within a Lambda_Config's `resources` array (or `__inherits__` directory) that defines a single Lambda function and its inline `api` route declaration.
- **API_Gateway_Config**: The JSON configuration file for the API Gateway stack (e.g., `api-gateway-primary.json`), containing gateway-level settings and optionally an explicit `routes` array.
- **Route_Metadata**: The `api` section of a Resource_Config, containing `route`, `method`, `skip_authorizer`, `authorization_type`, and optionally `routes` (for multi-route lambdas).
- **Lambda_Stack**: The `LambdaStack` class in `cdk-factory` (`lambda_stack.py`) that provisions Lambda functions and exports their ARNs to SSM.
- **API_Gateway_Stack**: The `ApiGatewayStack` class in `cdk-factory` (`api_gateway_stack.py`) that provisions the API Gateway and wires Lambda integrations.
- **SSM_Route_Export**: An SSM parameter written by the Lambda_Stack containing serialized Route_Metadata for a Lambda function, enabling cross-stack route discovery.
- **Route_Discovery**: The process by which the API_Gateway_Stack reads Route_Metadata from SSM parameters exported by Lambda_Stacks listed in the `depends_on` array, then merges them with any explicit routes to build the final route set.
- **Pipeline_Config**: The top-level `config.json` that defines pipeline stages and references stack config files via `__inherits__`.
- **Namespace**: The SSM parameter path prefix (e.g., `acme-saas/beta`) used to scope SSM exports per deployment environment.
- **SQS_Pattern**: The existing pattern where Lambda configs declare SQS queues inline and the Lambda_Stack wires triggers/permissions automatically without a separate SQS config.

## Requirements

### Requirement 1: Lambda Stack Exports Route Metadata to SSM

**User Story:** As an infrastructure developer, I want the Lambda_Stack to automatically export Route_Metadata to SSM Parameter Store for each Lambda that has an `api` section, so that the API_Gateway_Stack can discover routes without a separate config.

#### Acceptance Criteria

1. WHEN a Resource_Config contains an `api` section with a non-empty `route` field, THE Lambda_Stack SHALL write an SSM parameter at `/{namespace}/lambda/{lambda-name}/api-route` containing the serialized Route_Metadata as a JSON string.
2. WHEN a Resource_Config contains an `api` section with a `routes` array (multi-route lambda), THE Lambda_Stack SHALL include all routes from the `routes` array in the serialized Route_Metadata SSM parameter.
3. WHEN a Resource_Config does not contain an `api` section, THE Lambda_Stack SHALL not write any route-related SSM parameter for that Lambda function.
4. THE Lambda_Stack SHALL write route SSM parameters using the same Namespace prefix already used for ARN exports (e.g., `/{namespace}/lambda/{lambda-name}/api-route`).
5. THE Lambda_Stack SHALL include the following fields in the serialized Route_Metadata: `route`, `method`, `skip_authorizer`, `authorization_type`, and `routes` (if present).

### Requirement 2: API Gateway Stack Discovers and Merges Routes

**User Story:** As an infrastructure developer, I want the API_Gateway_Stack to always merge routes from both explicit config and SSM discovery, so that migration is seamless and no separate mode switch is needed.

#### Acceptance Criteria

1. THE API_Gateway_Stack SHALL always build its final route set by merging two sources: explicit routes from the API_Gateway_Config `routes` array and discovered routes from SSM_Route_Exports of Lambda_Stacks listed in the `depends_on` array.
2. WHEN the API_Gateway_Config contains a `routes` array with entries but no discovered routes exist, THE API_Gateway_Stack SHALL use the explicit routes unchanged, preserving backward compatibility.
3. WHEN the API_Gateway_Config does not contain a `routes` array (or it is empty) and discovered routes exist, THE API_Gateway_Stack SHALL use the discovered routes with no explicit routes array needed.
4. WHEN both explicit routes and discovered routes are present, THE API_Gateway_Stack SHALL merge them into a single route set.
5. WHEN the same path and HTTP method combination appears in both the explicit `routes` array and a discovered SSM_Route_Export, THE API_Gateway_Stack SHALL use the explicit route definition and log a WARNING during CDK synthesis identifying the conflict.
6. WHEN the API_Gateway_Stack discovers routes from SSM, THE API_Gateway_Stack SHALL construct route definitions equivalent to the current explicit route format, including `path`, `method`, `lambda_name`, and authorization settings.
7. WHEN a discovered route has `skip_authorizer` set to `true`, THE API_Gateway_Stack SHALL configure that route with `authorization_type` set to `NONE`.
8. WHEN a discovered route does not specify `skip_authorizer` or sets it to `false`, THE API_Gateway_Stack SHALL apply the default authorization behavior (Cognito authorizer if configured).
9. WHEN a Lambda has multiple routes (via the `routes` array in Route_Metadata), THE API_Gateway_Stack SHALL create an API Gateway route for each entry, all pointing to the same Lambda function.
10. THE API_Gateway_Stack SHALL log each discovered route at INFO level during CDK synthesis for auditability.

### Requirement 3: API Gateway Config Retains Gateway-Level Settings Only

**User Story:** As an infrastructure developer, I want the API_Gateway_Config to contain only gateway-level settings after migration, so that route definitions are not duplicated.

#### Acceptance Criteria

1. THE API_Gateway_Config SHALL support operation without a `routes` array, relying entirely on Route_Discovery.
2. WHEN the API_Gateway_Config contains gateway-level settings (name, api_type, description, deploy_options, custom_domain, cognito, cors), THE API_Gateway_Stack SHALL apply those settings regardless of whether routes come from the config or from Route_Discovery.
3. THE API_Gateway_Config SHALL retain `depends_on` references to Lambda stack config names to ensure correct deployment ordering and to identify which Lambda_Stacks to discover routes from.

### Requirement 4: Lambda Config Remains the Single Source of Truth for Routes

**User Story:** As an infrastructure developer, I want each Lambda's route to be defined only in its Resource_Config, so that there is a single source of truth and no risk of route drift.

#### Acceptance Criteria

1. THE Resource_Config `api` section SHALL be the sole location where route path, HTTP method, and authorization overrides are defined for a Lambda function.
2. WHEN a route is added to a Resource_Config `api` section, THE Route_Discovery mechanism SHALL automatically include that route in the API Gateway without any change to the API_Gateway_Config.
3. WHEN a route is removed from a Resource_Config `api` section, THE Route_Discovery mechanism SHALL automatically exclude that route from the API Gateway without any change to the API_Gateway_Config.

### Requirement 5: Route Metadata Schema Validation

**User Story:** As an infrastructure developer, I want route metadata to be validated at synth time, so that misconfigured routes are caught before deployment.

#### Acceptance Criteria

1. WHEN the Lambda_Stack processes a Resource_Config with an `api` section, THE Lambda_Stack SHALL validate that the `route` field is a non-empty string starting with `/`.
2. WHEN the Lambda_Stack processes a Resource_Config with an `api` section, THE Lambda_Stack SHALL validate that the `method` field is a recognized HTTP method (GET, POST, PUT, DELETE, PATCH, OPTIONS, HEAD).
3. IF a Resource_Config contains an `api` section with an invalid `route` or `method`, THEN THE Lambda_Stack SHALL raise a descriptive error during CDK synthesis.
4. WHEN the API_Gateway_Stack reads a route SSM parameter, THE API_Gateway_Stack SHALL validate the deserialized Route_Metadata before creating the API Gateway integration.

### Requirement 6: SSM Route Parameter Follows Existing Naming Convention

**User Story:** As an infrastructure developer, I want route SSM parameters to follow the same naming convention as existing Lambda ARN exports, so that the parameter store remains organized and predictable.

#### Acceptance Criteria

1. THE Lambda_Stack SHALL write route SSM parameters under the path `/{namespace}/lambda/{lambda-name}/api-route`, consistent with the existing `/{namespace}/lambda/{lambda-name}/arn` pattern.
2. WHEN the `ssm.auto_export` flag is `false` in the Lambda stack config, THE Lambda_Stack SHALL not export route SSM parameters.
3. THE Lambda_Stack SHALL use `ssm.ParameterTier.STANDARD` for route SSM parameters.

### Requirement 7: API Gateway Discovers Routes from depends_on Lambda Stacks

**User Story:** As an infrastructure developer, I want the API_Gateway_Stack to use the existing `depends_on` array to determine which Lambda stacks to discover routes from, so that no new configuration field is needed.

#### Acceptance Criteria

1. THE API_Gateway_Stack SHALL discover routes from Lambda_Stacks whose config names appear in the API_Gateway_Config `depends_on` array.
2. WHEN a `depends_on` entry references a Lambda_Stack that has exported route SSM parameters, THE API_Gateway_Stack SHALL read and include those routes in the merged route set.
3. WHEN a `depends_on` entry references a non-Lambda stack (e.g., a Cognito stack), THE API_Gateway_Stack SHALL skip route discovery for that entry without raising an error.
4. WHEN a `depends_on` entry references a Lambda_Stack that has no route SSM parameters, THE API_Gateway_Stack SHALL skip that stack without raising an error.
