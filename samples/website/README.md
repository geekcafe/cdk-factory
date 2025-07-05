# WebSite Sample README

This sample shows how you can use a pre-configured stack library to deploy a static website.

You have two options when running this:
1. Simply Deploy the stack without a CI/CD deployment.  Do this if you want to simply test it out.
1. Deploy it as an AWS CodePipeline Deployment.

## The flow is controlled in the configuration(s)
1. config.stack.json
1. config.pipeline.json

## Simple Stack Deployment 
For a simple stack deployment, use the `config.stack.json`


## Pipeline Deployment
For a full AWS CodePipeline Deployment you will use the `config.pipeline.json`

### Prerequisites
- You can either point to this public repo 
- Or (preferably) clone this repo and point to your cloned/forked copy.  


> Fair warning, if you point to this repo, anytime we make code changes, `commit` and `push` to GitHub, it will invoke your pipeline (assuming your creating the CI/CD pipeline).  

This sample will:
1. Define a deployment CodePipeline for automatic updates (if using the `config.pipeline.json`).
1. Create an S3 Bucket for hosting the static site
1. Create a CloudFront distribution for the site.
1. [Optionally]: Register the CloudFront with a Route53 Hosted Zone for your custom Domain
4. [Optionally]: Create an SSL/TLS certificate for HTTPS connections


This is a simple example, which allows you to simply point the cdk_factory to the configs found here.  It's a quick and direct way to run a simple deployment.

## Deploy with a custom domain e.g.  mydomain.com
If you have a domain hosted in AWS and access to the HostedZone in the account you are deploying to, you can use this command.
```sh

cdk synth \
    -c config=../../samples/website/website_config.json \
    -c AccountNumber="<AWS ACCOUNT>" \   
    -c AccountRegion="<REGION>" \
    -c CodeRepoName="company/my-repo-name" \
    -c CodeRepoConnectorArn="aws::repo_arn" \
    -c SiteBucketName="my-bucket-2" \
    -c HostedZoneId="zone1234" \
    -c HostedZoneName="dev.example.com"
```

These samples are located in this library.

However in real-life scenarios, you will want to consume this package in your own project e.g.
1. Create a new python project
1. pip install cdk-factory
1. Define your resources 
1. Deploy it

You can find a working example in GitHub [geekcafe/cdk-factory-sample-static-website](https://github.com/geekcafe/cdk-factory-sample-static-website/)