# cdk-factory
An AWS CDK wrapper for common deployments and best practices.

## Contributing to the Code Base 
If you are contributing to the code base

1. Clone this repo
1. Run the `./setup.sh` shell script
1. Start exploring

## Understanding the flow
The core configuration for any of the CDK deployments are controlled in your config.json files.  From a high-level we have the following key elements that control the actions within the framework.  The details will follow.


|key|description|
|---|---|
|`cdk`|Any cdk configs/parameters that you need to pass|
|`workload`|General information about your workload|
|`workload`->`stacks`|A CDK implementation of a CloudFormation Stack|
|`workload`->`deployments`|Grouping of Stacks, which can be deployed via `stack` or `pipeline` mode|
|`workload`->`pipelines`|An AWS Code Pipeline deployment|


### cdk
The `cdk` -> `parameters` defines the following

|key|description|
|---|---|
|`placeholder`|A placeholder that will used to perform a fine/replace action in the config once it's processed|
|`env_var_name \| value`|An environment variable to load the value or a static value|
|`cdk_parameter_name`|The CdkParameterName that will be passed in as custom argument to the synth command |



#### Example
```json
{ 
    "cdk": {
        "parameters": [
            {
                "placeholder": "{{WORKLOAD_NAME}}",
                "env_var_name": "CDK_WORKLOAD_NAME",
                "cdk_parameter_name": "WorkloadName"
            },
            {
                "placeholder": "{{CDK_SYNTH_COMMAND_FILE}}",
                "value": "../../samples/website/commands/cdk_synth.sh",
                "cdk_parameter_name": "CdkSynthCommandFile"
            },
        ]
    }
}
```


### workload
>TODO:

### stacks
>TODO:


## deployments
>TODO:


## pipelines
>TODO: