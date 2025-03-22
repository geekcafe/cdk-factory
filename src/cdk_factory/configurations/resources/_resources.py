"""
Geek Cafe, LLC
Maintainers: Eric Wilson
MIT License.  See Project Root for the license information.
"""

from typing import List

from aws_lambda_powertools import Logger

from cdk_factory.configurations.resources.ecr import ECRConfig
from cdk_factory.configurations.resources.lambda_function import (
    LambdaFunctionConfig,
)
from cdk_factory.configurations.resources.s3 import S3BucketConfig
from cdk_factory.configurations.resources.sqs import SQS

logger = Logger()


class Resources:
    """Represents AWS Resources"""

    def __init__(self, parent: dict) -> None:
        # resources will either be listed
        self.parent: dict = parent
        self.ecr_repositories: List[ECRConfig] = []
        self.lambda_functions: List[LambdaFunctionConfig] = []
        self.buckets: List[S3BucketConfig] = []
        self.sqs_queues: List[SQS] = []
        self.__load()

    def __load(self) -> None:
        repositories: List[dict] = self.__load_list("ecr_repositories")
        lambda_functions: List[dict] = self.__load_list("lambda_functions")
        buckets: List[dict] = self.__load_list("s3_buckets")
        sqs_queues: List[dict] = self.__load_list("sqs_queues")

        for repo in repositories:
            ecr = ECRConfig(repo)
            self.ecr_repositories.append(ecr)

        if lambda_functions:
            for item in lambda_functions:
                # todo
                # techdebt
                # i have a bug in the json parsing, doing this for now
                if isinstance(item, list):
                    for i in item:
                        lambda_ = LambdaFunctionConfig(i)
                        self.lambda_functions.append(lambda_)
                else:
                    lambda_ = LambdaFunctionConfig(item)
                    self.lambda_functions.append(lambda_)

        if buckets:
            for item in buckets:
                bucket: S3BucketConfig = S3BucketConfig(item)
                self.buckets.append(bucket)

        if sqs_queues:
            for item in sqs_queues:
                queue: SQS = SQS(item)
                self.sqs_queues.append(queue)

    def __load_list(self, name) -> List[dict]:
        item = self.parent.get(name)
        if item and isinstance(item, list):
            return item
        elif item and isinstance(item, dict):
            file = item.get("file")
            if file:
                raise RuntimeError(
                    "the 'file' key is no longer supported.  Use the __inherits__ key"
                )

        return []
