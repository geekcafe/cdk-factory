# SSM Parameter Sharing Example

This sample demonstrates how to use the SSM Parameter Store for sharing information between CDK stacks, enabling looser coupling and independent deployment.

## Overview

The sample includes:

1. A configuration file (`config.json`) that defines:
   - VPC stack with SSM parameter exports
   - Cognito stack with SSM parameter exports
   - API Gateway stack that consumes SSM parameters from both VPC and Cognito stacks

2. A deployment script (`deploy_stacks.py`) that shows how to:
   - Deploy stacks in the correct order
   - Use SSM parameters for cross-stack references

## Key Benefits

- **Loose Coupling**: Stacks can be deployed independently without creating explicit CloudFormation dependencies
- **Flexibility**: Stacks can be updated or replaced without affecting consumers
- **Standardization**: Consistent pattern for resource sharing across all stacks

## Usage

1. Review the configuration in `config.json`:
   ```json
   {
     "stacks": {
       "vpc": {
         "vpc": {
           "ssm_parameters": {
             "vpc_id_path": "/my-app/dev/vpc/id",
             "vpc_cidr_path": "/my-app/dev/vpc/cidr"
           }
         }
       }
     }
   }
   ```

2. Run the deployment script:
   ```bash
   python deploy_stacks.py
   ```

3. Deploy stacks individually as needed:
   - VPC stack can be deployed first
   - Cognito stack can be deployed independently
   - API Gateway stack can be deployed last, consuming parameters from both

## Implementation Details

The SSM parameter sharing pattern uses:

1. `BaseConfig` - Base configuration class with SSM parameter support
2. `SsmParameterMixin` - Mixin class with methods for exporting/importing SSM parameters
3. Stack implementations that use the mixin to export and import parameters

For more details, see the [SSM Parameter Pattern documentation](../../docs/ssm_parameter_pattern.md).

## Testing

To test the SSM parameter sharing:

1. Deploy the VPC stack first
2. Verify SSM parameters are created in the AWS console
3. Deploy the Cognito stack
4. Deploy the API Gateway stack and verify it can access the VPC and Cognito resources
