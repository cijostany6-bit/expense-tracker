"""Tests for the receipt-OCR Lambda (pure parsing + a mocked end-to-end pass)."""
import importlib
from decimal import Decimal

import boto3
import pytest
from moto import mock_aws

import ocr

BUCKET = "expense-tracker-receipts"
TABLE = "expense-tracker-expenses"


# --------------------------------------------------------------------------- #
# pure functions
# --------------------------------------------------------------------------- #
def test_classify_known_vendors():
    assert ocr.classify("LIDL Filiale Berlin") == "food"
    assert ocr.classify("Shell Tankstelle") == "travel"
    assert ocr.classify("Apotheke am Markt") == "health"
    assert ocr.classify("Amazon EU") == "shopping"
    assert ocr.classify("Vodafone GmbH") == "utilities"
    assert ocr.classify("Netflix") == "entertainment"


def test_classify_unknown_is_other():
    assert ocr.classify("ZZZ Unknown Vendor") == "other"
    assert ocr.classify(None, "") == "other"


def test_normalize_category_accepts_valid_model_answer():
    assert ocr.normalize_category("Travel", "LIDL") == "travel"  # model wins if valid


def test_normalize_category_rejects_invalid_and_falls_back():
    assert ocr.normalize_category("banana", "LIDL") == "food"
    assert ocr.normalize_category(None, "Apotheke") == "health"


def test_detect_image_format():
    assert ocr.detect_image_format(b"\x89PNG\r\n\x1a\nrest") == "png"
    assert ocr.detect_image_format(b"\xff\xd8\xff\xe0rest") == "jpeg"
    assert ocr.detect_image_format(b"RIFF\x00\x00\x00\x00WEBP") == "webp"
    assert ocr.detect_image_format(b"%PDF-1.4") is None


def test_parse_model_json_strips_fences():
    assert ocr.parse_model_json('```json\n{"vendor": "LIDL", "total": 13.16}\n```') == {
        "vendor": "LIDL",
        "total": 13.16,
    }


def test_parse_model_json_tolerates_prose():
    assert ocr.parse_model_json('Here: {"total": 1} done')["total"] == 1


def test_to_decimal():
    assert ocr.to_decimal("13,16") == Decimal("13.16")
    assert ocr.to_decimal("7.50") == Decimal("7.50")
    assert ocr.to_decimal(-5) is None
    assert ocr.to_decimal("abc") is None
    assert ocr.to_decimal(None) is None


# --------------------------------------------------------------------------- #
# mocked end-to-end (moto for S3 + DynamoDB, Bedrock stubbed)
# --------------------------------------------------------------------------- #
@pytest.fixture
def env():
    with mock_aws():
        ddb = boto3.resource("dynamodb", region_name="eu-central-1")
        ddb.create_table(
            TableName=TABLE,
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
            Bucket=BUCKET,
            CreateBucketConfiguration={"LocationConstraint": "eu-central-1"},
        )
        importlib.reload(ocr)  # bind clients to the mocked endpoints
        yield ocr, ddb.Table(TABLE), s3


def _s3_event(key):
    return {"Records": [{"s3": {"bucket": {"name": BUCKET}, "object": {"key": key}}}]}


def test_process_record_fills_the_row(env, monkeypatch):
    mod, table, s3 = env
    table.put_item(Item={"userId": "u1", "expenseId": "e1", "status": "pending"})
    s3.put_object(Bucket=BUCKET, Key="receipts/u1/e1", Body=b"\x89PNG\r\n\x1a\nfake")

    monkeypatch.setattr(
        mod,
        "extract_from_image",
        lambda body, fmt: (
            {
                "vendor": "LIDL Filiale Berlin",
                "date": "2024-03-12",
                "total": 13.16,
                "currency": "eur",
                "category": "food",
                "confidence": 0.92,
            },
            {"totalTokens": 100},
        ),
    )

    mod.handler(_s3_event("receipts/u1/e1"), None)

    item = table.get_item(Key={"userId": "u1", "expenseId": "e1"})["Item"]
    assert item["status"] == "processed"
    assert item["vendor"] == "LIDL Filiale Berlin"
    assert item["category"] == "food"
    assert item["amount"] == Decimal("13.16")
    assert item["currency"] == "EUR"       # upper-cased
    assert item["date"] == "2024-03-12"
    assert item["ocrModel"].startswith("eu.")


def test_unusable_image_marks_needs_review(env):
    mod, table, s3 = env
    table.put_item(Item={"userId": "u1", "expenseId": "e2", "status": "pending"})
    s3.put_object(Bucket=BUCKET, Key="receipts/u1/e2", Body=b"%PDF-1.4 not an image")

    mod.handler(_s3_event("receipts/u1/e2"), None)

    item = table.get_item(Key={"userId": "u1", "expenseId": "e2"})["Item"]
    assert item["status"] == "needs_review"


def test_low_confidence_marks_needs_review(env, monkeypatch):
    mod, table, s3 = env
    table.put_item(Item={"userId": "u1", "expenseId": "e3", "status": "pending"})
    s3.put_object(Bucket=BUCKET, Key="receipts/u1/e3", Body=b"\x89PNG\r\n\x1a\nfake")

    monkeypatch.setattr(
        mod,
        "extract_from_image",
        lambda body, fmt: (
            {"vendor": None, "total": 4.0, "category": "other", "confidence": 0.2},
            {},
        ),
    )
    mod.handler(_s3_event("receipts/u1/e3"), None)

    item = table.get_item(Key={"userId": "u1", "expenseId": "e3"})["Item"]
    assert item["status"] == "needs_review"   # amount found but confidence too low


def test_bedrock_error_marks_needs_review(env, monkeypatch):
    mod, table, s3 = env
    table.put_item(Item={"userId": "u1", "expenseId": "e4", "status": "pending"})
    s3.put_object(Bucket=BUCKET, Key="receipts/u1/e4", Body=b"\x89PNG\r\n\x1a\nfake")

    def boom(body, fmt):
        raise RuntimeError("bedrock down")

    monkeypatch.setattr(mod, "extract_from_image", boom)
    mod.handler(_s3_event("receipts/u1/e4"), None)

    item = table.get_item(Key={"userId": "u1", "expenseId": "e4"})["Item"]
    assert item["status"] == "needs_review"


def test_unexpected_key_is_ignored(env):
    mod, table, s3 = env
    # should not raise
    mod.handler(_s3_event("somewhere/else"), None)
