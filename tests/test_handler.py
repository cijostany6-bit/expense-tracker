"""Unit tests for the Expense Tracker API handler.

These run fully offline: moto mocks DynamoDB and S3, and identity is injected
the same way API Gateway's JWT authorizer injects it (the `sub` claim).
"""
import json

BUCKET = "expense-tracker-receipts"


def call(api, method, path, sub="user-a", body=None, path_params=None):
    """Invoke the Lambda handler with a payload-format-2.0 event."""
    event = {
        "requestContext": {
            "http": {"method": method},
            "authorizer": {"jwt": {"claims": {"sub": sub}}},
        },
        "rawPath": path,
        "body": json.dumps(body) if body is not None else None,
        "pathParameters": path_params or {},
    }
    resp = api.handler(event, None)
    return resp["statusCode"], json.loads(resp["body"])


# --------------------------------------------------------------------------- #
# create
# --------------------------------------------------------------------------- #
def test_create_expense_success(api):
    code, body = call(api, "POST", "/expenses", body={"amount": 12.5, "category": "Food"})
    assert code == 201
    assert body["amount"] == 12.5
    assert body["category"] == "food"  # normalised to lower-case
    assert body["currency"] == "EUR"   # default
    assert body["userId"] == "user-a"
    assert "expenseId" in body


def test_create_expense_requires_positive_amount(api):
    assert call(api, "POST", "/expenses", body={})[0] == 400
    assert call(api, "POST", "/expenses", body={"amount": -1})[0] == 400
    assert call(api, "POST", "/expenses", body={"amount": 0})[0] == 400
    assert call(api, "POST", "/expenses", body={"amount": "abc"})[0] == 400


def test_create_expense_invalid_json(api):
    event = {
        "requestContext": {
            "http": {"method": "POST"},
            "authorizer": {"jwt": {"claims": {"sub": "user-a"}}},
        },
        "rawPath": "/expenses",
        "body": "{not json",
        "pathParameters": {},
    }
    resp = api.handler(event, None)
    assert resp["statusCode"] == 400


# --------------------------------------------------------------------------- #
# list + tenant isolation
# --------------------------------------------------------------------------- #
def test_list_sorted_newest_first(api):
    call(api, "POST", "/expenses", body={"amount": 1, "date": "2024-01-01"})
    call(api, "POST", "/expenses", body={"amount": 2, "date": "2024-03-01"})
    call(api, "POST", "/expenses", body={"amount": 3, "date": "2024-02-01"})

    code, body = call(api, "GET", "/expenses")
    assert code == 200
    assert body["count"] == 3
    dates = [i["date"] for i in body["items"]]
    assert dates == ["2024-03-01", "2024-02-01", "2024-01-01"]


def test_tenant_isolation(api):
    call(api, "POST", "/expenses", sub="user-a", body={"amount": 5})
    code, body = call(api, "GET", "/expenses", sub="user-b")
    assert code == 200
    assert body["count"] == 0


# --------------------------------------------------------------------------- #
# delete
# --------------------------------------------------------------------------- #
def test_delete_expense(api):
    _, created = call(api, "POST", "/expenses", body={"amount": 9})
    eid = created["expenseId"]

    code, body = call(api, "DELETE", f"/expenses/{eid}")
    assert code == 200
    assert body["deleted"] == eid
    # gone from the list
    assert call(api, "GET", "/expenses")[1]["count"] == 0


def test_delete_missing_returns_404(api):
    code, body = call(api, "DELETE", "/expenses/does-not-exist")
    assert code == 404
    assert "error" in body


def test_delete_is_scoped_to_caller(api):
    _, created = call(api, "POST", "/expenses", sub="user-a", body={"amount": 9})
    eid = created["expenseId"]
    # user-b cannot delete user-a's expense
    assert call(api, "DELETE", f"/expenses/{eid}", sub="user-b")[0] == 404
    # and it still exists for user-a
    assert call(api, "GET", "/expenses", sub="user-a")[1]["count"] == 1


# --------------------------------------------------------------------------- #
# update
# --------------------------------------------------------------------------- #
def test_update_partial_fields(api):
    _, created = call(api, "POST", "/expenses", body={"amount": 10, "category": "food"})
    eid = created["expenseId"]

    code, body = call(api, "PUT", f"/expenses/{eid}", body={"amount": 20, "note": "  hi  "})
    assert code == 200
    assert body["amount"] == 20
    assert body["note"] == "hi"          # trimmed
    assert body["category"] == "food"    # untouched
    assert "updatedAt" in body


def test_update_date_reserved_word(api):
    """`date` is a DynamoDB reserved word and must be aliased (#date)."""
    _, created = call(api, "POST", "/expenses", body={"amount": 10})
    eid = created["expenseId"]
    code, body = call(api, "PUT", f"/expenses/{eid}", body={"date": "2024-12-31"})
    assert code == 200
    assert body["date"] == "2024-12-31"


def test_update_no_fields_is_400(api):
    _, created = call(api, "POST", "/expenses", body={"amount": 10})
    assert call(api, "PUT", f"/expenses/{created['expenseId']}", body={})[0] == 400


def test_update_missing_is_404(api):
    assert call(api, "PUT", "/expenses/nope", body={"amount": 1})[0] == 404


def test_update_rejects_bad_amount(api):
    _, created = call(api, "POST", "/expenses", body={"amount": 10})
    eid = created["expenseId"]
    assert call(api, "PUT", f"/expenses/{eid}", body={"amount": -5})[0] == 400


# --------------------------------------------------------------------------- #
# summary
# --------------------------------------------------------------------------- #
def test_summary_groups_by_category(api):
    call(api, "POST", "/expenses", body={"amount": 10, "category": "food"})
    call(api, "POST", "/expenses", body={"amount": 5, "category": "food"})
    call(api, "POST", "/expenses", body={"amount": 2, "category": "travel"})

    code, body = call(api, "GET", "/summary")
    assert code == 200
    assert body["byCategory"] == {"food": 15.0, "travel": 2.0}
    assert body["grandTotal"] == 17.0
    assert body["count"] == 3


def test_summary_isolated_per_user(api):
    call(api, "POST", "/expenses", sub="user-a", body={"amount": 10, "category": "food"})
    code, body = call(api, "GET", "/summary", sub="user-b")
    assert code == 200
    assert body["grandTotal"] == 0.0
    assert body["count"] == 0


# --------------------------------------------------------------------------- #
# receipts (presigned URLs)
# --------------------------------------------------------------------------- #
def test_receipt_upload_url_and_recorded_key(api):
    _, created = call(api, "POST", "/expenses", body={"amount": 10})
    eid = created["expenseId"]

    code, body = call(api, "POST", f"/expenses/{eid}/receipt-url")
    assert code == 200
    assert "uploadUrl" in body
    assert body["receiptKey"] == f"receipts/user-a/{eid}"


def test_receipt_upload_url_missing_expense_is_404(api):
    # No expense exists yet -> the conditional update fails -> 404 (not a 500).
    code, _ = call(api, "POST", "/expenses/ghost/receipt-url")
    assert code == 404


def test_receipt_preview_404_when_no_object(api):
    _, created = call(api, "POST", "/expenses", body={"amount": 10})
    eid = created["expenseId"]
    assert call(api, "GET", f"/expenses/{eid}/receipt-url")[0] == 404


# --------------------------------------------------------------------------- #
# scan (receipt -> pending expense)
# --------------------------------------------------------------------------- #
def test_scan_creates_pending_expense_with_upload_url(api):
    code, body = call(api, "POST", "/expenses/scan")
    assert code == 201
    assert "expenseId" in body
    assert "uploadUrl" in body
    assert body["receiptKey"] == f"receipts/user-a/{body['expenseId']}"

    # it shows up in the list as pending, with no amount yet
    _, listing = call(api, "GET", "/expenses")
    assert listing["count"] == 1
    assert listing["items"][0]["status"] == "pending"


def test_scan_is_scoped_to_caller(api):
    call(api, "POST", "/expenses/scan", sub="user-a")
    assert call(api, "GET", "/expenses", sub="user-b")[1]["count"] == 0


# --------------------------------------------------------------------------- #
# router
# --------------------------------------------------------------------------- #
def test_unknown_route_is_404(api):
    assert call(api, "GET", "/nope")[0] == 404


def test_unmatched_method_is_404(api):
    assert call(api, "PATCH", "/expenses")[0] == 404


def test_trailing_slash_tolerated(api):
    assert call(api, "GET", "/expenses/")[0] == 200
