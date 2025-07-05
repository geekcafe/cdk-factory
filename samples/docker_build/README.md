# Docker Build Readme

If you want to build a docker container and publish it to ECR, this is an example on how to do it.

In this use case, I only want to build, tag and deploy the Docker Container.  This can be used for Containers backed ECS, or Lambda.

The actual consuming of the Docker Container by an ECS task or Lambda function will happen else where.

This is ideal for controlling the Docker Container process with separation of how it's used in your environment.

The general flow would be something like this:

1. Code update triggers pipeline
1. Docker Build is done
1. Docker Image and tagging is done
1. Docker image is deployed 
    1. To one or more ECR repos (may need to deploy to more than one region)
1. Optionally Trigger one or more Lambda’s to refresh to the 
    1. latest image (e.g. latest or a specific version number)
    1. Specify the AWS Account
1. Optionally Trigger an ECS Task to update to the latest or a specific version.
