# Step 9 — Receipt OCR: read a photo of a bill, fill the expense in

Step 9 is the feature that turns a toy into something people would actually use:
**upload a photo of a receipt and the expense fills itself in.** Vendor, date,
total, currency and category — extracted from the image, no typing.

This page covers the architecture, the *service choice* (and why it's not the
obvious one), and how every piece connects.

---

## 9.1 — The user story

> *"I have a drawer of paper receipts. I want to photograph one and have it show
> up in the app, categorised, without typing anything."*

The app already let you attach a receipt to an expense you'd typed by hand. Step 9
inverts that: **the receipt creates the expense.**

---

## 9.2 — Architecture: event-driven, not request-driven

The naïve design is "upload → wait → return the parsed result". That couples the
user's request to a slow AI call and breaks the moment the model is slow. We use
an **asynchronous, event-driven** pipeline instead — the same
*extract → transform → load* shape you'd use in a real data pipeline:

```
  Browser                     API Lambda            S3               OCR Lambda        Bedrock
    │                              │                 │                   │               │
    │ 1 POST /expenses/scan        │                 │                   │               │
    │─────────────────────────────▶│ put pending row │                   │               │
    │                              │────────────────▶│                   │               │
    │ ◀── {expenseId, uploadUrl} ──│                 │                   │               │
    │                                                │                   │               │
    │ 2 PUT image (presigned)                        │                   │               │
    │───────────────────────────────────────────────▶│                   │               │
    │                                                │ ObjectCreated     │               │
    │                                                │──────────────────▶│ 3 read image  │
    │                                                │                   │──────────────▶│
    │                                                │                   │ ◀── JSON ─────│
    │                                                │                   │ 4 UpdateItem  │
    │ 5 poll GET /expenses (every 2s)                │                   │  status=done  │
    │─────────────────────────────▶│                 │                   │               │
    │ ◀── row now filled in ✔ ─────│                 │                   │               │
```

**Why this shape is better:**

| Concern | Request/response | Event-driven (ours) |
|---|---|---|
| Slow model | user waits, request may time out | user gets an instant "reading…" row |
| Retries | hard (the request is gone) | S3 event can redeliver |
| Cost | Lambda billed for the whole AI call | each Lambda does one job |
| Coupling | API must know about OCR | API just writes a row and a presigned URL |

The browser **polls** `GET /expenses` and watches `status` flip from `pending` to
`processed`. That's a deliberate simplicity choice over WebSockets — trivial to
reason about, and a two-second poll on a personal app is nothing.

---

## 9.3 — The service decision (the interesting part)

The purpose-built AWS service for receipts is **Amazon Textract `AnalyzeExpense`**
— it returns vendor, total, line items, all structured. That's what we *wanted*.

**Textract is not available on this account.** Every call returns:

```
SubscriptionRequiredException: The AWS Access Key Id needs a subscription for the service
```

This is an account-level gate on newer AWS accounts (it also hit Comprehend and
Transcribe). It can't be lifted from the CLI, and unblocking it needs a paid
support plan we don't have. So we evaluated the alternatives that *do* work:

| Service | What it returns | Verdict |
|---|---|---|
| **Textract `AnalyzeExpense`** | purpose-built vendor/total/line-items | ❌ `SubscriptionRequiredException` |
| **Rekognition `DetectText`** | raw OCR text lines (99–100% conf on our test) | ✅ works — but it's *just text*; we'd parse the fields ourselves |
| **Bedrock vision (Nova Lite)** | already-structured JSON: vendor, date, total, currency | ✅ **chosen** |

We ran a real comparison on a generated receipt. Rekognition read it perfectly —
`LIDL`, `Datum: 12.03.2024`, `SUMME 13.16 EUR` — but then *we* would own a brittle
pile of regex. Bedrock returned exactly what we needed in one call:

```json
{ "vendor": "LIDL Filiale Berlin Mitte", "date": "2024-03-12",
  "total": 13.16, "currency": "EUR", "category": "food", "confidence": 0.95 }
```

> **Interview gold:** "Textract is the right *service*, but it was blocked on my
> account. I benchmarked Rekognition and Bedrock on a real receipt, and chose
> Bedrock because it does OCR *and* understanding in one call — fewer moving
> parts, and less code for me to maintain. I documented why."

### Bedrock details

- **Model:** `eu.amazon.nova-lite-v1:0` — Amazon Nova **Lite**, cheap, fast, and
  vision-capable.
- **Inference profile:** Bedrock on-demand needs a profile (direct model IDs are
  region-pinned); the `eu.` prefix routes inference **within the EU**.
- **Data residency (principle D1):** an `eu.*` profile keeps the receipt image in
  the EU. There are also `us.*` and `global.*` profiles — we deliberately didn't
  use them.

---

## 9.4 — How the pieces connect

| Piece | Role | Connects to |
|---|---|---|
| `POST /expenses/scan` | creates a `pending` row + presigned PUT | API Lambda → DynamoDB |
| Presigned PUT | browser uploads **straight to S3** (no bytes through Lambda) | S3 receipts bucket |
| `receipts/{userId}/{expenseId}` | the key encodes **who** and **which expense** | S3 → Lambda |
| S3 `ObjectCreated` (prefix `receipts/`) | fires exactly once per upload | S3 → OCR Lambda |
| `expense-tracker-ocr` | orchestration: read → Bedrock → write | S3, Bedrock, DynamoDB |
| Bedrock `converse` | image → structured JSON | the model |
| `classify()` | deterministic vendor→category fallback | pure function (tested) |
| DynamoDB `UpdateItem` | sets amount/vendor/date/category/status | the same row the browser polls |

Two design choices worth calling out:

**The S3 key is the contract.** The key is
`receipts/{userId}/{expenseId}` — so the OCR Lambda needs **no extra state** to
know which row to update. It parses the key. Tenant isolation comes for free
because `userId` is *in* the key.

**The API role and the OCR role are separate.** The API Lambda never touches
Bedrock; the OCR Lambda never touches Cognito or presigns. Least privilege, and
each function's IAM policy reads as documentation of what it does.

---

## 9.5 — Defensive by design

An AI call can fail in a dozen ways: a blurry photo, a PDF, a network blip, a
model hiccup. The rule is: **never lose the user's data and never leave a row
stuck in limbo.**

```
status: pending ──▶ processed      (amount found, confidence ≥ 0.5)
              └──▶ needs_review    (no amount, low confidence, or any error)
```

- Every failure path — bad image format, Bedrock exception, unparseable JSON —
  is caught and marks the row **`needs_review`** instead of throwing. The user
  still has their row and can fill it in by hand.
- The category the model returns is **validated against our allow-list**; if it's
  nonsense we fall back to `classify()` — a plain keyword table. That keeps a
  deterministic, unit-testable path even when the model improvises.
- `parse_model_json()` tolerates the model wrapping JSON in ```` ```json ```` fences
  or adding prose — a real-world LLM failure mode.

This is the difference between a demo and software: **the demo assumes the model
works; the software assumes it might not.**

---

## 9.6 — Testing

[`tests/test_ocr.py`](../tests/test_ocr.py) adds **13 tests**, all offline:

- the pure functions — `classify`, `normalize_category`, `detect_image_format`,
  `parse_model_json`, `to_decimal` — which hold the parsing logic;
- the **end-to-end path with moto** (mock S3 + DynamoDB) and Bedrock stubbed:
  a good receipt fills the row, a PDF marks `needs_review`, low confidence marks
  `needs_review`, and a Bedrock crash still marks `needs_review`.

No AWS account, no credentials, no model spend — the whole pipeline is verified
in CI.

---

## 💰 Cost

| Item | Cost |
|---|---|
| Bedrock · Nova Lite | ~**$0.0001** per receipt (a fraction of a cent) |
| S3 PUT + GET of a receipt | pennies per thousand |
| OCR Lambda | free tier (1M requests + 400k GB-s/month) |

The OCR feature costs effectively **nothing** at this scale — worth noting, since
"AI features are expensive" is a common assumption.

---

## 💬 Interview questions this step unlocks

- **"Why event-driven instead of parsing during the upload request?"** — decouples
  a slow, failure-prone AI call from the user's request; the row renders instantly
  and the pipeline retries independently.
- **"Why Bedrock and not Textract?"** — Textract is purpose-built but was gated on
  the account; Bedrock returns structured JSON in one call. (See §9.3.)
- **"How do you keep AI features from corrupting data?"** — the model only ever
  *suggests*; a `pending → processed | needs_review` state machine and a
  validated allow-list mean a bad extraction degrades gracefully.
- **"How do you stop one user's receipt touching another's data?"** — the S3 key
  is `receipts/{userId}/{expenseId}` and the row key is `(userId, expenseId)`; the
  Lambda can only write where the key says.
- **"Where does the image go?"** — an `eu.*` Bedrock inference profile keeps it in
  the EU; that was a deliberate data-residency decision, not a default.
- **"Why not stream results over WebSockets?"** — polling is enough at this scale
  and far simpler; WebSockets would be the move at a larger one.
