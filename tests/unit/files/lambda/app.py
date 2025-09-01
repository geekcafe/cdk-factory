#!/usr/bin/env python3
"""
A simple AWS Lambda function for testing purposes.
"""


def lambda_handler(event, context):
    return {
        "statusCode": 200,
        "body": "Hello from Lambda!",
    }
