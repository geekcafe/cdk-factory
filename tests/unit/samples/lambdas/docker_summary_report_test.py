import os
import unittest
from pathlib import Path
import json

from samples.lambdas.docker_file.src.lambda_handlers.summary_report.app import (
    lambda_handler,
)


class DockerSummaryReportTest(unittest.TestCase):

    def test_lambda_handler(self):
        event: dict = {}

        response: dict = lambda_handler(event, None)
        self.assertIn("statusCode", response)
        self.assertIn("body", response)
        self.assertEqual(response.get("statusCode"), 200)
        data = response.get("body")
        self.assertIsInstance(response.get("body"), str)

        body: dict = json.loads(response.get("body"))
        # no filter so 100 records
        self.assertEqual(len(body), 100)

    def test_lambda_handler_filter_user_email(self):
        event: dict = {"filter": {"user_email": "user_001@example.com"}}

        response: dict = lambda_handler(event, None)

        body: dict = json.loads(response.get("body"))
        self.assertEqual(len(body), 30)

    def test_lambda_handler_querystring_user_email(self):
        event: dict = {"queryStringParameters": {"user_email": "user_001@example.com"}}

        response: dict = lambda_handler(event, None)

        body: dict = json.loads(response.get("body"))
        self.assertEqual(len(body), 30)

    def test_lambda_handler_filter_service(self):
        event: dict = {"filter": {"service": "Lambda"}}

        response: dict = lambda_handler(event, None)

        body: dict = json.loads(response.get("body"))
        self.assertEqual(len(body), 18)
