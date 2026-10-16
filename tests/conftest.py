"""Shared test fixtures.

The API handler reads TABLE_NAME / BUCKET_NAME at import time and builds its
boto3 clients at module level, so we must (a) set the environment before the
module is imported and (b) re-import it *inside* the moto mock context so its
clients point at the mocked services.
"""
import importlib
import os
import sys

import boto3
import pytest
from moto import mock_aws

BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend"))
sys.path.insert(0, BACKEND)

TABLE_NAME = "expense-tracker-expenses"
BUCKET_NAME = "expense-tracker-receipts"

os.environ.update(
    {
        "TABLE_NAME": TABLE_NAME,
        "BUCKET_NAME": BUCKET_NAME,
        "AWS_REGION": "eu-central-1",
        "AWS_DEFAULT_REGION": "eu-central-1",
        # moto needs *some* credentials, they are never used for real calls
        "AWS_ACCESS_KEY_ID": "testing",
        "AWS_SECRET_ACCESS_KEY": "testing",
        "AWS_SECURITY_TOKEN": "testing",
        "AWS_SESSION_TOKEN": "testing",
    }
)


@pytest.fixture
def api():
    """A freshly-imported handler wired to mocked DynamoDB + S3."""
    with mock_aws():
        ddb = boto3.resource("dynamodb", region_name="eu-central-1")
        ddb.create_table(
            TableName=TABLE_NAME,
            KeySchema=[
                {"AttributeName": "userId", "KeyType": "HASH"},
                {"AttributeName": "expenseId", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "userId", "AttributeType": "S"},
                {"AttributeName": "expenseId", "AttributeType": "S"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )

        s3 = boto3.client("s3", region_name="eu-central-1")
        s3.create_bucket(
            Bucket=BUCKET_NAME,
            CreateBucketConfiguration={"LocationConstraint": "eu-central-1"},
        )

        import handler  # noqa: E402  (imported here on purpose)

        importlib.reload(handler)
        yield handler


@pytest.fixture
def s3_client():
    with mock_aws():
        yield boto3.client("s3", region_name="eu-central-1")
