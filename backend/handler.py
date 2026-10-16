"""
Expense Tracker API — single Lambda handling all routes.

Routes (API Gateway HTTP API, payload format 2.0):
  GET    /expenses                  -> list the caller's expenses
  POST   /expenses                  -> create an expense
  DELETE /expenses/{id}             -> delete one of the caller's expenses
  POST   /expenses/{id}/receipt-url -> presigned S3 PUT url for a receipt
  GET    /summary                   -> spend totals grouped by category

The caller's identity always comes from the verified JWT `sub` claim
(injected by API Gateway's Cognito JWT authorizer) — never from the request
body. That is what enforces tenant isolation.
"""
import json
import os
import re
import uuid
from datetime import datetime, timezone
from decimal import Decimal

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

TABLE_NAME = os.environ["TABLE_NAME"]
BUCKET_NAME = os.environ["BUCKET_NAME"]
REGION = os.environ.get("AWS_REGION", "eu-central-1")

dynamodb = boto3.resource("dynamodb", region_name=REGION)
table = dynamodb.Table(TABLE_NAME)
# Pin the REGIONAL S3 endpoint. Using the global endpoint (s3.amazonaws.com)
# causes a 307 redirect for buckets outside us-east-1, which breaks direct
# browser PUTs to presigned URLs.
s3 = boto3.client(
    "s3",
    region_name=REGION,
    endpoint_url=f"https://s3.{REGION}.amazonaws.com",
    config=Config(signature_version="s3v4", s3={"addressing_style": "virtual"}),
)


class DecimalEncoder(json.JSONEncoder):
    """DynamoDB returns numbers as Decimal; JSON can't serialise that."""

    def default(self, o):
        if isinstance(o, Decimal):
            return float(o)
        return super().default(o)


def _response(code, body):
    return {
        "statusCode": code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body, cls=DecimalEncoder),
    }


def _claims(event):
    return event["requestContext"]["authorizer"]["jwt"]["claims"]


def _user_id(event):
    # `sub` is the immutable unique id of the Cognito user.
    return _claims(event)["sub"]


def _now():
    return datetime.now(timezone.utc).isoformat()


# --------------------------------------------------------------------------- #
# route handlers
# --------------------------------------------------------------------------- #
def list_expenses(event):
    user_id = _user_id(event)
    result = table.query(
        KeyConditionExpression=boto3.dynamodb.conditions.Key("userId").eq(user_id)
    )
    items = sorted(result.get("Items", []), key=lambda i: i.get("date", ""), reverse=True)
    return _response(200, {"items": items, "count": len(items)})


def create_expense(event):
    user_id = _user_id(event)
    try:
        payload = json.loads(event.get("body") or "{}")
    except json.JSONDecodeError:
        return _response(400, {"error": "invalid JSON body"})

    # minimal validation
    try:
        amount = Decimal(str(payload["amount"]))
    except (KeyError, ValueError, TypeError):
        return _response(400, {"error": "'amount' is required and must be a number"})
    if amount <= 0:
        return _response(400, {"error": "'amount' must be greater than 0"})

    item = {
        "userId": user_id,
        "expenseId": str(uuid.uuid4()),
        "amount": amount,
        "currency": (payload.get("currency") or "EUR").upper(),
        "category": (payload.get("category") or "other").lower(),
        "date": payload.get("date") or datetime.now(timezone.utc).date().isoformat(),
        "note": (payload.get("note") or "").strip(),
        "createdAt": _now(),
    }
    table.put_item(Item=item)
    return _response(201, item)


def delete_expense(event):
    user_id = _user_id(event)
    expense_id = (event.get("pathParameters") or {}).get("id")
    if not expense_id:
        return _response(400, {"error": "missing expense id"})

    result = table.delete_item(
        Key={"userId": user_id, "expenseId": expense_id},
        ReturnValues="ALL_OLD",
    )
    if "Attributes" not in result:
        return _response(404, {"error": "expense not found"})
    return _response(200, {"deleted": expense_id})


def create_receipt_url(event):
    user_id = _user_id(event)
    expense_id = (event.get("pathParameters") or {}).get("id")
    if not expense_id:
        return _response(400, {"error": "missing expense id"})

    key = f"receipts/{user_id}/{expense_id}"
    url = s3.generate_presigned_url(
        "put_object",
        Params={"Bucket": BUCKET_NAME, "Key": key},
        ExpiresIn=300,  # 5 minutes to complete the upload
    )
    # remember which object belongs to which expense
    table.update_item(
        Key={"userId": user_id, "expenseId": expense_id},
        UpdateExpression="SET receiptKey = :k",
        ConditionExpression="attribute_exists(expenseId)",
        ExpressionAttributeValues={":k": key},
    )
    return _response(200, {"uploadUrl": url, "receiptKey": key})


def update_expense(event):
    """Update selected fields of an existing expense: PUT /expenses/{id}."""
    user_id = _user_id(event)
    expense_id = (event.get("pathParameters") or {}).get("id")
    if not expense_id:
        return _response(400, {"error": "missing expense id"})

    try:
        payload = json.loads(event.get("body") or "{}")
    except json.JSONDecodeError:
        return _response(400, {"error": "invalid JSON body"})

    assignments, values = [], {}

    if "amount" in payload:
        try:
            amount = Decimal(str(payload["amount"]))
        except (ValueError, TypeError):
            return _response(400, {"error": "'amount' must be a number"})
        if amount <= 0:
            return _response(400, {"error": "'amount' must be greater than 0"})
        assignments.append("amount = :a")
        values[":a"] = amount
    if "currency" in payload:
        assignments.append("currency = :cur")
        values[":cur"] = (payload["currency"] or "EUR").upper()
    if "category" in payload:
        assignments.append("category = :cat")
        values[":cat"] = (payload["category"] or "other").lower()
    if "date" in payload:
        # "DATE" is a DynamoDB reserved word -> must be aliased
        assignments.append("#date = :d")
        values[":d"] = payload["date"]
    if "note" in payload:
        assignments.append("note = :n")
        values[":n"] = (payload["note"] or "").strip()

    if not assignments:
        return _response(400, {"error": "no updatable fields supplied"})

    assignments.append("updatedAt = :u")
    values[":u"] = _now()

    kwargs = {
        "Key": {"userId": user_id, "expenseId": expense_id},
        "UpdateExpression": "SET " + ", ".join(assignments),
        "ConditionExpression": "attribute_exists(expenseId)",
        "ExpressionAttributeValues": values,
        "ReturnValues": "ALL_NEW",
    }
    # DynamoDB rejects unused name aliases, so only pass it when #date is used.
    # NOTE: `"#date" in assignments` would be list-membership (always False here),
    # so match it as a substring of each statement instead.
    if any("#date" in stmt for stmt in assignments):
        kwargs["ExpressionAttributeNames"] = {"#date": "date"}

    try:
        result = table.update_item(**kwargs)
    except table.meta.client.exceptions.ConditionalCheckFailedException:
        return _response(404, {"error": "expense not found"})
    return _response(200, result["Attributes"])


def get_receipt_url(event):
    """Presigned GET url so the browser can preview a receipt:
    GET /expenses/{id}/receipt-url"""
    user_id = _user_id(event)
    expense_id = (event.get("pathParameters") or {}).get("id")
    if not expense_id:
        return _response(400, {"error": "missing expense id"})

    key = f"receipts/{user_id}/{expense_id}"
    try:
        s3.head_object(Bucket=BUCKET_NAME, Key=key)  # does the object exist?
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") in ("404", "NoSuchKey", "NotFound"):
            return _response(404, {"error": "no receipt for this expense"})
        raise

    url = s3.generate_presigned_url(
        "get_object",
        Params={"Bucket": BUCKET_NAME, "Key": key},
        ExpiresIn=300,
    )
    return _response(200, {"downloadUrl": url, "receiptKey": key})


def summary(event):
    user_id = _user_id(event)
    result = table.query(
        KeyConditionExpression=boto3.dynamodb.conditions.Key("userId").eq(user_id)
    )
    totals = {}
    grand_total = Decimal("0")
    for item in result.get("Items", []):
        amount = item.get("amount", Decimal("0"))
        category = item.get("category", "other")
        totals[category] = totals.get(category, Decimal("0")) + amount
        grand_total += amount
    return _response(
        200,
        {
            "byCategory": totals,
            "grandTotal": grand_total,
            "count": len(result.get("Items", [])),
        },
    )


# --------------------------------------------------------------------------- #
# router
# --------------------------------------------------------------------------- #
# Routes are matched with regex so that templates like /expenses/{id} work.
ROUTES = [
    ("GET", re.compile(r"^/expenses$"), list_expenses),
    ("POST", re.compile(r"^/expenses$"), create_expense),
    ("DELETE", re.compile(r"^/expenses/(?P<id>[^/]+)$"), delete_expense),
    ("PUT", re.compile(r"^/expenses/(?P<id>[^/]+)$"), update_expense),
    ("POST", re.compile(r"^/expenses/(?P<id>[^/]+)/receipt-url$"), create_receipt_url),
    ("GET", re.compile(r"^/expenses/(?P<id>[^/]+)/receipt-url$"), get_receipt_url),
    ("GET", re.compile(r"^/summary$"), summary),
]


def handler(event, context):
    method = event["requestContext"]["http"]["method"]
    path = event["rawPath"].rstrip("/") or "/"

    for route_method, pattern, fn in ROUTES:
        if route_method != method:
            continue
        match = pattern.match(path)
        if not match:
            continue
        # merge any captured path parameters into the event
        params = dict(event.get("pathParameters") or {})
        params.update(match.groupdict())
        event["pathParameters"] = params
        try:
            return fn(event)
        except Exception as exc:  # noqa: BLE001 - surface a clean 500 to the client
            print(f"ERROR {method} {path}: {exc}")
            return _response(500, {"error": "internal error"})

    return _response(404, {"error": f"no route for {method} {path}"})
