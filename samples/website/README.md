# WebSite Sample README

Deploy a static website using the pre-built website stack.

## What this sample does
- **S3 bucket** for static assets
- **CloudFront distribution** fronting the bucket (with automatic invalidation on deploy)
- **Optional Route53 + ACM** for custom domains and HTTPS

Source files live in `samples/website/src/www/`.

## Files in this sample
- **`config_min.json`**: minimal configuration demonstrating both a direct stack deploy and a pipeline mode
- **`commands/cdk_synth.sh`**: synth command used by the pipeline stage
- **`src/www/`**: example website files (`index.html`, `403.html`, `404.html`)

## Prerequisites
- **Node.js** (for `npx cdk`), **Python 3.10+**
- **AWS credentials** configured for the target account
- Install project dependencies (from repo root):
  - `pip install -r requirements.txt`

## Quick start: synth a simple stack
Use the provided minimal config:

```sh
cdk synth -c config=../../samples/website/config_min.json
```

`config_min.json` uses environment variables for required placeholders. Set these before running if not already present:

**Quick export for local testing:**
```sh
export CDK_WORKLOAD_NAME="my-website"
export AWS_ACCOUNT_NUMBER="123456789012"
export DEVOPS_AWS_ACCOUNT="123456789012"
export DEVOPS_REGION="us-east-1"
export CODE_REPOSITORY_NAME="myorg/my-repo"
export CODE_REPOSITORY_CONNECTOR_ARN="arn:aws:codestar-connections:us-east-1:123456789012:connection/abc123"
export SITE_BUCKET_NAME="my-site"
export ENVIRONMENT="dev"
```

**Required variables:**

- **CDK_WORKLOAD_NAME** (e.g., `website`)
- **AWS_ACCOUNT_NUMBER**
- **DEVOPS_AWS_ACCOUNT** (for pipeline account; can equal AWS_ACCOUNT_NUMBER for single-account)
- **DEVOPS_REGION** (e.g., `us-east-1`)
- **CODE_REPOSITORY_NAME** (e.g., `company/my-repo-name`)
- **CODE_REPOSITORY_CONNECTOR_ARN** (for CodeStar Connections)
- **SITE_BUCKET_NAME** (short name; full bucket name is derived)
- **ENVIRONMENT** (e.g., `dev`)

The minimal config sets up:
- A stack-mode deployment for the website bucket
- A pipeline-mode deployment that uses `commands/cdk_synth.sh`

## Pipeline deployment
When `mode` is `pipeline` in `config_min.json`, CodePipeline will invoke `commands/cdk_synth.sh` to run `cdk synth`. Ensure your connection ARN and repository name are correct in your environment variables so the pipeline can source and build successfully.

## Deploy
After synth, you can deploy with the same config path:

```sh
cdk deploy -c config=../../samples/website/config_min.json
```

## Custom domain (optional)
To use a custom domain with Route53 and ACM, add `dns` and `cert` to the website stack section in your config, for example:

```json
{
  "name": "web-site",
  "module": "static_website_stack",
  "enabled": true,
  "bucket": { "name": "{{SITE_BUCKET_NAME}}", "exists": true },
  "src": { "location": "file_system", "path": "{{WWW_FILES}}" },
  "dns": {
    "hosted_zone_id": "Z1234567890ABC",
    "hosted_zone_name": "example.com",
    "aliases": ["www.example.com"]
  },
  "cert": {
    "domain_name": "www.example.com",
    "alternate_names": ["example.com"]
  }
}
```

Notes:
- When `dns.hosted_zone_id` is set, `aliases` must be a non-empty list; Route53 A/AAAA records will be created for each alias.
- Certificate validation uses DNS in the specified hosted zone.

## Using this outside the repo
For real projects:
- **pip install cdk-factory**
- Create your own config modeled after `samples/website/config_min.json`
- Keep your website assets in a folder and point `src.path` to it
- Run `cdk synth`/`cdk deploy` with `-c config=<your-config-path>`

Example reference project: [geekcafe/cdk-factory-sample-static-website](https://github.com/geekcafe/cdk-factory-sample-static-website/)