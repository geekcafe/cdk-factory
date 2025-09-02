#!/usr/bin/env python3
"""
Test Lambda function for groups listing
"""


def lambda_handler(event, context):
    """Lambda handler for listing groups"""
    return {
        "statusCode": 200,
        "body": "Groups listed successfully",
        "headers": {
            "Content-Type": "application/json"
        }
    }
