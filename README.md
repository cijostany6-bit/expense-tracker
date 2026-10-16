# Expense Tracker ☁️

A **serverless, multi-user expense tracker on AWS** — sign up, log expenses, upload
receipts, and see your spend summary. Built *and understood* service by service:
every step is documented with a diagram, the decisions behind it, and drills to go deeper.

> **Status:** 🚧 In active build (started 2026-10-16) · **Region:** `eu-central-1` (Frankfurt)
> **Repo:** part of the [Cloud/DevOps portfolio](../) · separate GitHub repo planned

---

## 🗺️ Architecture — live status

```
                      ┌──────────────────────────────┐
                      │         YOUR BROWSER         │
                      │      (HTML/JS frontend)      │   ⏳ step 5
                      └───────────────┬──────────────┘
                                      │ HTTPS + JWT
                                      ▼
                      ┌──────────────────────────────┐
                      │     API GATEWAY (HTTP API)   │   ⏳ step 4
                      │   routes + JWT authorizer    │
                      └───────────────┬──────────────┘
                                      │ invoke
                                      ▼
                      ┌──────────────────────────────┐
                      │        LAMBDA (Python)       │   ⏳ step 3
                      │  CRUD + presigned-URL logic  │
                      └───────┬───────────────┬──────┘
                              │               │
                    read/write│               │put/get receipt
                              ▼               ▼
            ┌──────────────────────────┐  ┌──────────────────┐
            │  ✅ DYNAMODB             │  │  ⏳ S3 BUCKET     │
            │  expense-tracker-expenses│  │  receipts/        │
            │  PK: userId   ← tenant   │  │  presigned URLs   │
            │  SK: expenseId ← unique  │  │  (private)        │
            └──────────────────────────┘  └──────────────────┘
                  ✅ DONE (step 1a)          step 1b

  ⏳ COGNITO (step 2) ── issues the JWT that API Gateway verifies
  ⏳ IAM     (step 3) ── the "permission slip" Lambda uses to touch DynamoDB/S3
```

## ✅ Build status

| Step | Service | What it does | Status |
|---|---|---|---|
| 1a | **DynamoDB** | stores expenses (PK `userId`, SK `expenseId`) | ✅ done |
| 1b | **S3** | stores receipt files (private, presigned URLs) | ⏳ next |
| 2 | **Cognito** | sign-up / sign-in, issues JWTs | ⏳ |
| 3 | **IAM + Lambda** | CRUD API logic; least-privilege permissions | ⏳ |
| 4 | **API Gateway** | public HTTP API + JWT authorizer | ⏳ |
| 5 | **S3 static** | hosts the frontend | ⏳ |
| 6 | Test + docs | end-to-end verification | ⏳ |

## 🧰 Services used — and *why this, not that*

| Service | Role here | Why not the alternative |
|---|---|---|
| **DynamoDB** | Expense records | *RDS/Aurora* → pay for an always-on DB; *S3* → no item queries |
| **S3** | Receipt files | *EBS/EFS* → not object storage, no presigned URLs |
| **Cognito** | User accounts + JWT | *Auth0* → per-user cost; *custom auth* → we'd own password/MFA security |
| **Lambda** | API business logic | *EC2* → we'd patch & scale servers |
| **API Gateway** | Public API + authorizer | *ALB* → no built-in JWT authorizer / usage plans |
| **IAM** | Least-privilege access | *admin keys* → one leak = whole account |

## 🗄️ Data model

| Entity | Keys / fields | Store |
|---|---|---|
| **Expense** | `userId` (PK) · `expenseId` (SK) · `amount` · `currency` · `category` · `date` · `note` · `receiptKey` | DynamoDB |
| **Receipt** | `receipts/{userId}/{expenseId}.{ext}` | S3 |

## 🧭 Key decisions

| # | Decision | Rationale |
|---|---|---|
| D1 | **Region `eu-central-1` (Frankfurt)** | GDPR / EU data residency — an EU-facing product; a deliberate, explainable choice (accepting slightly higher dev latency from India) |
| D2 | **DynamoDB `PAY_PER_REQUEST`** | No capacity planning; stays inside Free Tier |
| D3 | **`userId` as partition key** | Tenant isolation — Lambda forces it from the JWT, so users can only see their own data |
| D4 | **Presigned URLs for uploads** | Files go browser→S3 directly (no large payloads through Lambda; no public bucket) |
| D5 | **Resource tagging** `Project` / `Owner` | Cost attribution + FinOps discipline |

## 📁 Repo layout

```
expense-tracker/
├── README.md              ← you are here (living overview)
├── docs/
│   └── step-1a-dynamodb.md   ← per-step deep dive (diagram, decisions, drills)
└── app/                   ← frontend (step 5)
```

## 📈 Next steps

1. Step 1b — S3 receipts bucket
2. Step 2 — Cognito user pool
3. Step 3 — Lambda + IAM role
4. Step 4 — API Gateway + authorizer
5. Step 5 — Frontend
6. Step 6 — End-to-end test, screenshots, push to GitHub
