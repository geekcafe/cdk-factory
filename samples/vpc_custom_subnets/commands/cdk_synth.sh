#!/bin/bash
set -e

# This is a simple script to synthesize the CDK app
# It's referenced in the config_min.json file

echo "Synthesizing CDK app for VPC with custom subnet names"
cd "$(dirname "$0")/../../../"
npx cdk synth
