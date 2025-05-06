# WebSite Sample README

This sample shows how you can use a preconfigured stack library to deploy a static website.

You have two options when running this:
1. Simply Deploy the stack
1. Deploy it as an AWS CodePipeline Deployment

## The flow is controlled in the configuration(s)
1. config.stack.json
1. config.pipeline.json

## Simple Stack Deployment 
For a simple stack deployment, use the `config.stack.json`


## Pipeline Deployment
For a full AWS CodePipeline Deployment you will use the `config.pipeline.json`

### Prerequists
1. You can either point to this public repo or clone this repo and point to it.  
2. You will need to create a Code

> Fair warning, if you point to this repo, anytime we make code changes, `commit` and `push` to GitHub, it will invoke your pipeline.  

This sample will:
1. Define a deployment CodePipeline for automatic updates.
1. Create an S3 Bucket for hosting the static site
1. Create a CloudFront distribution for the site.
1. [Optionally]: Register the CloudFront with a Route53 Hosted Zone for your custom Domain
4. [Optionally]: Create an SSL/TLS certificate for HTTPS connections


This is a simple example, whicha allows you to simply point the cdk_factory to the configs found here.  It's a quick and direct way to run a simple deployment.

## With a custom domain
If you have a domain hosted in AWS and access to the HostedZone in the account you are deploying to, you can use this command.
```sh

cdk synth \
    -c config=../../samples/website/website_config.json \
    -c AccountNumber="<AWS ACCCOUNT>" \   
    -c AccountRegion="<REGION>" \
    -c CodeRepoName="company/my-repo-name" \
    -c CodeRepoConnectorArn="aws::repo_arn" \
    -c SiteBucketName="my-bucket-2" \
    -c HostedZoneId="zone1234" \
    -c HostedZoneName="dev.example.com"
```

However in real-life scenarios, you want to did a pip install of this libary in your own project.  An example of this can be found in GitHub [geekcare/cdk-factory-sample-static-website](https://github.com/geekcafe/cdk-factory-sample-static-website/)