import os
import unittest
from pathlib import Path
import json

from samples.lambdas.docker_image.src.lambda_handlers.summary_report.app import (
    lambda_handler,
)


class DockerSummaryReportTest(unittest.TestCase):

    def test_lambda_handler(self):
        event: dict = {}

        reposonse: dict = lambda_handler(event, None)
        self.assertIn("statusCode", reposonse)
        self.assertIn("body", reposonse)
        self.assertEqual(reposonse.get("statusCode"), 200)
        data = reposonse.get("body")
        self.assertIsInstance(reposonse.get("body"), str)

        body: dict = json.loads(reposonse.get("body"))
        # no filter so 100 records
        self.assertEqual(len(body), 100)

    def test_lambda_handler_filter_user_email(self):
        event: dict = {"filter": {"user_email": "user_001@example.com"}}

        reposonse: dict = lambda_handler(event, None)

        body: dict = json.loads(reposonse.get("body"))
        self.assertEqual(len(body), 30)

    def test_lambda_handler_querystring_user_email(self):
        event: dict = {"queryStringParameters": {"user_email": "user_001@example.com"}}

        reposonse: dict = lambda_handler(event, None)

        body: dict = json.loads(reposonse.get("body"))
        self.assertEqual(len(body), 30)

    def test_lambda_handler_filter_service(self):
        event: dict = {"filter": {"service": "Lambda"}}

        reposonse: dict = lambda_handler(event, None)

        body: dict = json.loads(reposonse.get("body"))
        self.assertEqual(len(body), 18)
