# V3 blueprint — "Smart Receipts" + the expense history view

V3 turns the app from *record what I type* into **point a camera at a receipt and
let AWS do the work**. It also adds the navigation and grouping you asked for.

---

## The 5 things V3 adds

| # | You asked for | How V3 does it |
|---|---|---|
| 1 | **An interactive way to add an expense** | a "＋ Add" sheet with two tabs: **Manual** and **📷 Scan receipt** (drag-drop / camera) |
| 2 | **Segregate expenses** | collapsible **category groups** with per-group subtotal, count and share % |
| 3 | **An "Expenses" button that navigates to past expenses**, showing all segregations | a top-level nav: **Dashboard · Add · Expenses**. "Expenses" = the full history page, grouped by category, filterable |
| 4 | **Upload image receipts** | presigned **S3 PUT** (already built) + automatic processing |
| 5 | **An AWS service that extracts the image, transforms it, and loads it into the right category** | **Amazon Textract `AnalyzeExpense`** in an **event-driven ETL pipeline** (S3 → Lambda → Textract → DynamoDB) |

---

## The ETL pipeline (extract → transform → load)

This is the heart of V3. It is **event-driven**: nothing polls, nothing waits.
The user uploads a file and walks away; the system reacts.

```
 ①  Browser
     │  POST /expenses/scan        → Lambda issues a presigned PUT
     │  (or reuse the receipt endpoint)
     ▼
 ②  S3  receipts/{userId}/{expenseId}
     │        └── "ObjectCreated:*" event  ──────────┐
     │                                                │  (no polling, no queues to run)
 ③  ▼                                                │
    Lambda  expense-tracker-ocr   ← invoked BY S3 ───┘
     │
     │  EXTRACT
     ├──► Textract AnalyzeExpense(image)
     │       returns: VendorName, Total, InvoiceReceiptDate, LineItems…
     │
     │  TRANSFORM
     ├── amount   = Total
     ├── date     = InvoiceReceiptDate (normalised to YYYY-MM-DD)
     ├── vendor   = VendorName
     ├── category = classify(vendor + line-item text)   ← rules + keywords
     └── status   = "processed"   (or "needs_review" if confidence is low)
     │
     │  LOAD
     └──► DynamoDB  UpdateItem  on (userId, expenseId)
            sets amount / date / vendor / category / status / ocrConfidence
     │
     ▼
 ④  Browser polls GET /expenses  →  the expense appears, already categorised
```

### Why this shape?

- **S3 events are the trigger**, so the browser never waits for OCR (which takes
  2–5 s). Upload returns instantly; the record fills itself in a moment later.
- **Textract `AnalyzeExpense`** is purpose-built for receipts — it returns
  *structured* fields (`VendorName`, `Total`, `InvoiceReceiptDate`, line items),
  not a wall of raw text. That's the difference between OCR and *understanding*.
- **Separate Lambda** (`expense-tracker-ocr`) with its **own least-privilege
  role** — the API Lambda never gets Textract permission, and vice versa. If the
  OCR path is compromised it cannot read the API's data path.

### The "status" field is the UX secret

An expense can be `pending` → `processed` → (optionally) `needs_review`. The UI
shows a small spinner chip while `pending`, then the extracted values animate in.
Nothing is a lie: the user sees the machine thinking.

---

## Categorisation — be honest about how hard it is

| Approach | How | Trade-off |
|---|---|---|
| **Keyword rules** *(recommended)* | vendor/line-item text → keyword map (`"pharmacy"→health`, `"shell|esso"→travel`, `"lidl|rewe"→food`) | deterministic, free, explainable, 70–85% on common vendors |
| **Textract + rules + confidence** | same, but store the confidence and flag low-confidence rows for review | honest and robust |
| **Amazon Comprehend** | entity/keyword extraction to enrich the text before rules | costs extra; rarely beats good rules for receipts |
| **Amazon Bedrock (LLM)** | prompt: "classify this receipt into one of 8 categories, return JSON" | highest accuracy, most impressive, but **costs per token** and adds latency |

**Say this in an interview:** "I started with deterministic keyword
classification because it's free, explainable, and testable — and I stored a
confidence score so anything uncertain is flagged `needs_review` instead of
silently miscategorised. An LLM (Bedrock) is the natural upgrade, and the code is
already structured so `categories.classify()` is the only function I'd swap."

That shows *judgment*, which beats showing off.

---

## New / changed AWS pieces

| Piece | Change | Why |
|---|---|---|
| **S3** | add an `ObjectCreated:*` → Lambda notification (+ permission) | the trigger for the whole pipeline |
| **Textract** | new — `AnalyzeExpense` | the extraction engine |
| **Lambda `expense-tracker-ocr`** | new function (python3.12) | isolates OCR from the API |
| **IAM `expense-tracker-ocr-role`** | new: `textract:AnalyzeExpense` + `s3:GetObject` on receipts + `dynamodb:UpdateItem` + logs | least privilege, separately |
| **DynamoDB** | new attributes: `vendor`, `status`, `ocrConfidence`, `receiptKey` (already there) | store what we learned |
| **API** | `POST /expenses/scan` (presign + pre-create the row as `pending`) | the interactive scan flow |
| **CloudWatch** | an alarm on the OCR Lambda's `Errors` | know when extraction breaks |

### Cost

- Textract `AnalyzeExpense`: **free for 100 pages/month for 3 months**, then
  **$0.01/page** — 1,000 receipts/month ≈ **$10/month**.
- The S3 event → Lambda path costs effectively nothing at demo scale.

---

## UI work

```
┌──────────────────────────────────────────────────────────────┐
│  💸 Expense Tracker        Dashboard · Add · Expenses   [user]│   ← top nav (the button you asked for)
├──────────────────────────────────────────────────────────────┤
│  ADD VIEW                                                     │
│  ┌─ Manual ─┬─ 📷 Scan receipt ─┐                             │
│  │ amount ▸ │  ┌──────────────┐  │                            │
│  │ category │  │ drop image / │  │  ← upload → returns at once │
│  │ date     │  │  take photo  │  │     row shows "⏳ analysing" │
│  └──────────┴──└──────────────┘──┘                            │
│                                                               │
│  EXPENSES VIEW (the history page)                             │
│  ▾ 🍔 Food                        267.50   (2)  93%           │   ← segregation groups
│      Coffee ☕ with the team        7.50   📎                  │
│      Team lunch                   260.00                      │
│  ▾ 💊 Health                       19.99   (1)   7%           │
│      Pharmacy                     19.99   📎                  │
│  ▸ ✈️ Travel                        —                          │
└──────────────────────────────────────────────────────────────┘
```

Implementation note: keep it a **single-page app with views** (Dashboard / Add /
Expenses) rather than separate HTML files, so the JWT stays **in memory** and is
never written to `localStorage`. Navigating between real pages would force us to
persist the token somewhere an XSS bug could steal it. Worth saying out loud.

---

## Build order for V3 (one concept at a time)

| Step | What | Learn |
|---|---|---|
| **V3-0** | Sample receipt images (SVG/PNG) to test with | — |
| **V3-1** | Enable Textract; call `AnalyzeExpense` from the CLI on one image | Textract, its JSON shape, confidences |
| **V3-2** | Write & unit-test `categorize()` locally (pure function) | classification, thresholds, testability |
| **V3-3** | Create the `ocr` Lambda + its least-privilege role | IAM for services, separation of duties |
| **V3-4** | Wire the **S3 → Lambda notification** and test the trigger | event-driven architecture |
| **V3-5** | DynamoDB updates: `status`, `vendor`, `ocrConfidence` | partial updates, state machines |
| **V3-6** | `POST /expenses/scan` presign + pre-create the row | API design for async work |
| **V3-7** | UI: nav views, scan tab, pending → processed animation, category groups | UX for async systems |
| **V3-8** | Alarm on OCR errors; test the failure path with a non-receipt image | observability & graceful failure |

> **Interview framing:** "V3 is an event-driven ETL pipeline inside a serverless
> app: S3 events trigger a Lambda that calls Textract, normalises the fields,
> classifies the merchant, and loads the result into DynamoDB. I kept OCR in a
> separate function with its own role so the blast radius is small, and I store a
> confidence score so uncertain extractions surface for review rather than
> silently corrupting the data."
