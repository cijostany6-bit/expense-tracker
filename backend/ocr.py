"""
Receipt OCR Lambda — event-driven extraction with Amazon Bedrock.

Trigger: S3 `ObjectCreated` on `receipts/{userId}/{expenseId}`.

Flow (extract -> transform -> load):
  1. EXTRACT  read the object, send the image to Bedrock (Amazon Nova Lite, vision)
              and ask for structured JSON: vendor / date / total / currency / category.
  2. TRANSFORM normalise the fields, sanity-check the category, and decide a status
              (`processed` vs `needs_review`).
  3. LOAD     UpdateItem on (userId, expenseId) so the browser (which is polling
              GET /expenses) sees the row fill itself in.

Why Bedrock and not Textract? See docs/step-9-receipt-ocr.md — short version:
Textract AnalyzeExpense is the purpose-built service but is not enabled on this
account, and Bedrock carries the EU inference profile so the image never leaves
the EU (data-residency principle D1).

Everything here is defensive: any failure marks the row `needs_review` instead of
failing silently or corrupting the user's data.
"""
import json
import os
import re
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from urllib.parse import unquote_plus

import boto3

TABLE_NAME = os.environ["TABLE_NAME"]
REGION = os.environ.get("AWS_REGION", "eu-central-1")
MODEL_ID = os.environ.get("BEDROCK_MODEL_ID", "eu.amazon.nova-lite-v1:0")
MIN_CONFIDENCE = float(os.environ.get("MIN_CONFIDENCE", "0.5"))

dynamodb = boto3.resource("dynamodb", region_name=REGION)
table = dynamodb.Table(TABLE_NAME)
s3 = boto3.client("s3", region_name=REGION)
bedrock = boto3.client("bedrock-runtime", region_name=REGION)

# --------------------------------------------------------------------------- #
# classification — deterministic, explainable, unit-testable
# --------------------------------------------------------------------------- #
CATEGORY_KEYWORDS = {
    "food": ["lidl", "rewe", "aldi", "edeka", "kaufland", "penny", "netto", "supermarket",
             "grocery", "restaurant", "cafe", "café", "bakery", "bäckerei", "mcdonald",
             "kfc", "starbucks", "coffee", "food", "pizza", "burger"],
    "travel": ["shell", "esso", "aral", "total", "bp", "fuel", "petrol", "tankstelle",
               "deutsche bahn", "train", "flight", "hotel", "uber", "taxi", "airline", "parking"],
    "health": ["pharmacy", "apotheke", "rossmann", "dm ", "doctor", "clinic", "hospital",
               "dentist", "arzt", "health"],
    "shopping": ["amazon", "zalando", "h&m", "zara", "ikea", "mediamarkt", "saturn",
                 "clothing", "electronics", "shopping", "store", "shop"],
    "utilities": ["electric", "water", "gas", "internet", "vodafone", "telekom", "o2",
                  "bill", "utility", "utility bill", "strom", "stadtwerke"],
    "entertainment": ["netflix", "spotify", "cinema", "kino", "concert", "steam", "game",
                      "theatre", "theater"],
}
CATEGORIES = list(CATEGORY_KEYWORDS) + ["other"]


def classify(*texts):
    """Map vendor / line-item text to a category. First keyword match wins."""
    hay = " ".join(t for t in texts if t).lower()
    for category, words in CATEGORY_KEYWORDS.items():
        if any(word in hay for word in words):
            return category
    return "other"


def normalize_category(model_category, *texts):
    """Trust the model's category only if it is one we allow; else use rules."""
    if isinstance(model_category, str) and model_category.strip().lower() in CATEGORIES:
        return model_category.strip().lower()
    return classify(*texts)


# --------------------------------------------------------------------------- #
# parsing helpers (pure, unit-tested)
# --------------------------------------------------------------------------- #
def detect_image_format(data: bytes):
    """Return a Bedrock-supported image format for the given bytes, else None."""
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if data[:3] == b"\xff\xd8\xff":
        return "jpeg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    if data[:3] == b"GIF":
        return "gif"
    return None


def parse_model_json(text: str) -> dict:
    """Extract the JSON object from a model reply, tolerating ```json fences."""
    cleaned = (text or "").strip()
    cleaned = re.sub(r"^```(?:json)?", "", cleaned).strip()
    cleaned = re.sub(r"```$", "", cleaned).strip()
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start != -1 and end != -1 and end > start:
        cleaned = cleaned[start:end + 1]
    return json.loads(cleaned)


def to_decimal(value):
    """Best-effort conversion of a model number/string into a positive Decimal."""
    if value is None or value == "":
        return None
    try:
        amount = Decimal(str(value).replace(",", ".").strip())
    except (InvalidOperation, ValueError):
        return None
    return amount if amount > 0 else None


PROMPT = (
    "You are a receipt parsing engine. Read the receipt image and extract the fields. "
    "Reply with ONLY a compact JSON object, no markdown, no prose, with exactly these keys:\n"
    '{"vendor": string|null, "date": "YYYY-MM-DD"|null, "total": number|null, '
    '"currency": 3-letter string|null, "category": one of '
    '["food","travel","health","shopping","utilities","entertainment","other"], '
    '"confidence": number between 0 and 1}\n'
    "Rules: total = the final gross amount paid. Use null when you are not sure."
)


# --------------------------------------------------------------------------- #
# Bedrock call
# --------------------------------------------------------------------------- #
def extract_from_image(image_bytes: bytes, media_format: str):
    """Send the image to Bedrock and return (fields, usage)."""
    response = bedrock.converse(
        modelId=MODEL_ID,
        messages=[
            {
                "role": "user",
                "content": [
                    {"text": PROMPT},
                    {"image": {"format": media_format, "source": {"bytes": image_bytes}}},
                ],
            }
        ],
        inferenceConfig={"maxTokens": 300, "temperature": 0},
    )
    text = response["output"]["message"]["content"][0]["text"]
    return parse_model_json(text), response.get("usage", {})


# --------------------------------------------------------------------------- #
# load
# --------------------------------------------------------------------------- #
def _update(user_id, expense_id, sets, names, values):
    """Apply a SET update; only touch the row if it still exists."""
    values[":now"] = datetime.now(timezone.utc).isoformat()
    sets = sets + ["updatedAt = :now"]
    table.update_item(
        Key={"userId": user_id, "expenseId": expense_id},
        UpdateExpression="SET " + ", ".join(sets),
        ExpressionAttributeNames=names or None,
        ExpressionAttributeValues=values,
        ConditionExpression="attribute_exists(expenseId)",
    )


def process_record(record):
    bucket = record["s3"]["bucket"]["name"]
    key = unquote_plus(record["s3"]["object"]["key"])

    parts = key.split("/")
    if len(parts) != 3 or parts[0] != "receipts":
        print(f"skip: unexpected key '{key}'")
        return
    _, user_id, expense_id = parts

    try:
        body = s3.get_object(Bucket=bucket, Key=key)["Body"].read()
        media_format = detect_image_format(body)
        if media_format is None:
            raise ValueError("unsupported image format (png/jpeg/webp/gif only)")

        fields, usage = extract_from_image(body, media_format)

        vendor = (fields.get("vendor") or "").strip()[:120] or None
        category = normalize_category(fields.get("category"), vendor)
        amount = to_decimal(fields.get("total"))
        currency = (fields.get("currency") or "").strip()[:3].upper() or None
        date = (fields.get("date") or "").strip() or None
        try:
            confidence = Decimal(str(fields.get("confidence")))
        except (InvalidOperation, TypeError):
            confidence = None

        # Decide the state: did we get the one field that matters (the amount)?
        ok = amount is not None and (confidence is None or confidence >= Decimal(str(MIN_CONFIDENCE)))
        status = "processed" if ok else "needs_review"

        sets = ["#status = :status", "ocrModel = :model", "category = :cat"]
        names = {"#status": "status"}
        values = {
            ":status": status,
            ":model": MODEL_ID,
            ":cat": category,
            ":conf": confidence if confidence is not None else Decimal("0"),
        }
        sets.append("ocrConfidence = :conf")
        if vendor:
            sets.append("vendor = :vendor")
            values[":vendor"] = vendor
        if amount is not None:
            sets.append("amount = :amount")
            values[":amount"] = amount
        if currency:
            sets.append("currency = :currency")
            values[":currency"] = currency
        if date:
            sets.append("#date = :date")
            names["#date"] = "date"
            values[":date"] = date

        _update(user_id, expense_id, sets, names, values)
        print(f"ok: {key} -> status={status} amount={amount} vendor={vendor} category={category} "
              f"tokens={usage.get('totalTokens')}")

    except Exception as exc:  # noqa: BLE001 — never leave the row stuck on 'pending'
        print(f"ERROR processing {key}: {exc}")
        try:
            _update(
                user_id,
                expense_id,
                ["#status = :status"],
                {"#status": "status"},
                {":status": "needs_review"},
            )
        except Exception as inner:  # noqa: BLE001
            print(f"could not mark needs_review: {inner}")


def handler(event, context):
    for record in event.get("Records", []):
        process_record(record)
    return {"ok": True}
