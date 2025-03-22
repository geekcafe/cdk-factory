"""
Geek Cafe, LLC
Maintainers: Eric Wilson
MIT License.  See Project Root for the license information.
"""

from enum import Enum


class ResourceTypes(Enum):
    """Common Resource Types"""

    S3_BUCKET = 1
    LAMBDA_FUNCTION = 2
    API_GATEWAY = 3
    DYNAMO_DB = 3
    LAMBDA_LAYER = 4
    ECR_REPOSITORY = 5
    CLOUD_WATCH_LOGS = 6
    SQS = 7
    PARAMETER_STORE = 8
