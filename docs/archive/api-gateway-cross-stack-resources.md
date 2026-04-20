# API Gateway Cross-Stack Resource Management

## Problem

When multiple CDK stacks deploy Lambda functions to the same API Gateway instance, CloudFormation deployment conflicts occur:

```
Resource handler returned message: "Another resource with the same parent already has this name: app (Service: ApiGateway, Status Code: 409, Request ID: ...) (SDK Attempt Count: 1)"
```

This happens during CloudFormation deployment (not CDK synth) when:
- Stack A creates `/app/configuration` 
- Stack B tries to create `/app/services/property/search/id`
- Both attempt to create an "app" resource under the API Gateway root

### Workaround: Resource Import Configuration

When this occurs we have a workaround to help you deploy the second stack successfully and keep your API Gateway resource hierarchy intact.

**HOWEVER** this is not a recommended solution. It is better to plan your API Gateway resource hierarchy before deploying multiple stacks and use unique top-level paths per stack when possible.



Configure the second stack to import existing resources instead of creating them:

```json
{
  "api_gateway": {
    "existing_resources": {
      "/app": {
        "resource_id": "abc123def",
        "description": "Import existing 'app' resource created by workload-saas-lambda"
      }
    }
  }
}
```

## How to Find Resource IDs

1. **AWS Console**: Navigate to API Gateway → Your API → Resources → Click on resource → Note the Resource ID
2. **AWS CLI**: 
   ```bash
   aws apigateway get-resources --rest-api-id YOUR_API_ID --query 'items[?pathPart==`app`].id' --output text
   ```
3. **CloudFormation Outputs**: Export resource IDs from the first stack

## Configuration Examples

### Basic Resource Import
```json
{
  "api_gateway": {
    "existing_resources": {
      "/app": {
        "resource_id": "abc123def"
      }
    }
  }
}
```

### Multiple Resource Imports
```json
{
  "api_gateway": {
    "existing_resources": {
      "/app": {
        "resource_id": "abc123def"
      },
      "/app/services": {
        "resource_id": "xyz789ghi"
      }
    }
  }
}
```

## Behavior

- **Imported paths**: Use existing resources (no CloudFormation creation)
- **Non-imported paths**: Create new resources normally
- **Fallback**: If import fails, attempts normal creation

## Route Resolution Example

For route `/app/services/property/search` with `/app` imported:

1. `/app` → Import existing resource (ID: abc123def)
2. `/app/services` → Create new resource under imported `/app`
3. `/app/services/property` → Create new resource
4. `/app/services/property/search` → Create new resource  


## Alternative: Documentation Approach

If resource import is too complex, document the limitation:

### Cross-Stack API Gateway Limitation

In general, it is not recommended to deploy multiple stacks with overlapping API Gateway resource paths to the same API Gateway instance.

**Problematic**:
- Stack A: `/app/configuration`
- Stack B: `/app/services/...` ❌

**Recommended**:
- Stack A: `/app/configuration`  
- Stack B: `/property-search/services/...` ✅

Or use separate API Gateway instances per stack.

## Best Practices

1. **Plan resource hierarchy** before deploying multiple stacks
2. **Use unique top-level paths** per stack when possible
3. **Export resource IDs** from primary stacks for import by secondary stacks
4. **Document dependencies** between stacks clearly

## Troubleshooting

### Import Not Working
- Verify resource ID is correct
- Check API Gateway ID matches
- Ensure resource exists before importing stack deploys

### Still Getting Conflicts
- Check if multiple paths need importing
- Verify no typos in resource_id
- Consider using separate API Gateway instances
