# Expense Tracker ☁️

A **serverless, multi-user expense tracker on AWS** — sign up, log expenses,
upload receipts, and see a spend summary. Built *and understood* service by
service: every step has a diagram, the decisions behind it, and drills to go
deeper.

> **Status:** ✅ **Complete + UI v2** (2026-10-16) · **Region:** `eu-central-1` (Frankfurt)
> **Stack:** Cognito · API Gateway · Lambda · DynamoDB · S3 · IAM · CloudWatch
>
> **New here?** Start with [`docs/capabilities.md`](docs/capabilities.md) (what it
> does), then [`docs/how-it-works.md`](docs/how-it-works.md) (how a request flows),
> then [`docs/services-in-depth.md`](docs/services-in-depth.md) (the services).

## 🔗 Live

| Piece | URL |
|---|---|
| Web app | http://expense-tracker-web-896618135736.s3-website.eu-central-1.amazonaws.com |
| API | https://4haajttqgh.execute-api.eu-central-1.amazonaws.com |
| Demo user | `demo.cijo@example.com` / `Testpass1` |

---

## 🗺️ Architecture

```
                        ┌─────────────────────────────┐
                        │   Browser (S3 static site)   │
                        └───────┬──────────────┬───────┘
                   sign-in      │              │  PUT file
                                ▼              │
                    ┌───────────────────┐      │
                    │  COGNITO pool     │      │
                    │  + PreSignUp λ    │      │
                    │  → IdToken (JWT)  │      │
                    └─────────┬─────────┘      │
                              │ JWT            │
                              ▼                │
                    ┌───────────────────┐      │
                    │ API Gateway HTTP  │      │
                    │ JWT authorizer    │      │
                    └─────────┬─────────┘      │
                              │ AWS_PROXY      │
                              ▼                │
     ┌──────────────────────────────────┐      │
     │  Lambda  expense-tracker-api     │      │
     │  (runs as IAM role, least priv.) │      │
     └────────┬────────────────┬────────┘      │
              │                │ presign        │
              ▼                ▼                ▼
     ┌──────────────┐   ┌────────────────────────────────┐
     │  DYNAMODB    │   │  S3  receipts (private)         │
     │  expenses    │   │  receives the direct PUT        │
     └──────────────┘   └────────────────────────────────┘
              │
              ▼
     ┌──────────────┐
     │ CloudWatch   │
     │ Logs         │
     └──────────────┘
```

## ✅ Build status

| Step | Service | What it does | Status |
|---|---|---|---|
| 1a | **DynamoDB** | stores expenses (PK `userId`, SK `expenseId`) | ✅ |
| 1b | **S3** | stores receipts (private, presigned URLs) | ✅ |
| 2 | **Cognito** | sign-up / sign-in, issues JWTs | ✅ |
| 3 | **IAM + Lambda** | CRUD + presign logic, least-privilege role | ✅ |
| 4 | **API Gateway** | HTTP API + JWT authorizer, 7 routes | ✅ |
| 5 | **S3 static** | hosts the frontend | ✅ |
| 6 | **Testing** | end-to-end + security verification | ✅ |
| 7 | **UI v2** | edit + receipt preview endpoints, colourful interactive frontend | ✅ |

## 🔌 API (all routes require a valid JWT)

| Method | Path | Purpose | Auth |
|---|---|---|---|
| `GET` | `/expenses` | list the caller's expenses | JWT |
| `POST` | `/expenses` | create an expense | JWT |
| `PUT` | `/expenses/{id}` | update fields of an expense | JWT |
| `DELETE` | `/expenses/{id}` | delete an expense | JWT |
| `POST` | `/expenses/{id}/receipt-url` | presigned S3 **upload** URL | JWT |
| `GET` | `/expenses/{id}/receipt-url` | presigned S3 **preview** URL | JWT |
| `GET` | `/summary` | totals grouped by category | JWT |

## ✨ What it can do

| Feature | Under the hood |
|---|---|
| Create account / sign in | Cognito (auto-confirm via PreSignUp Lambda) |
| Add / edit / delete expenses | `POST` / `PUT` / `DELETE` → DynamoDB |
| Coloured list, newest first | `GET /expenses` → DynamoDB **Query** by partition key |
| Search · category filter · sort | client-side over the fetched list |
| KPI dashboard (total · count · avg · top category) | derived from filtered data, animated |
| Spend-by-category bar chart | `/summary` aggregation + live recompute |
| Upload a receipt (≤5 MB) | presigned **PUT** straight to private S3 |
| Preview a receipt image | presigned **GET** in a modal |
| Export filtered list to CSV | client-side blob |
| Keyboard shortcuts | `/` search · `Esc` close |

Full capability list and honest "not built yet" table → **`docs/capabilities.md`**.

## 🧰 Services used — and *why this, not that*

| Service | Role here | Why not the alternative |
|---|---|---|
| **DynamoDB** | Expense records | *RDS/Aurora* → pay for an always-on DB; *S3* → no item queries |
| **S3** | Receipt files + web hosting | *EBS/EFS* → not object storage / no presigned URLs |
| **Cognito** | Accounts + JWT | *Auth0* → cost; *custom auth* → we'd own password/MFA security |
| **Lambda** | API business logic | *EC2* → patch & scale servers |
| **API Gateway** | Public API + authorizer | *ALB* → no built-in JWT authorizer |
| **IAM** | Least-privilege access | *admin keys* → one leak = whole account |
| **CloudWatch** | Logs & debugging | *self-hosted* → need a server |

## 🗄️ Data model

| Entity | Keys / fields | Store |
|---|---|---|
| **Expense** | `userId` (PK) · `expenseId` (SK) · `amount` · `currency` · `category` · `date` · `note` · `receiptKey` · `createdAt` | DynamoDB |
| **Receipt** | `receipts/{userId}/{expenseId}` | S3 |

## 📁 Repo layout

```
expense-tracker/
├── README.md                     ← you are here
├── backend/
│   ├── handler.py                ← all API routes (Python 3.12)
│   └── autoconfirm.py            ← Cognito PreSignUp trigger
├── app/
│   ├── index.html                ← page structure
│   ├── styles.css                ← theme (colourful, animated, responsive)
│   ├── app.js                    ← auth + CRUD + filters + chart (vanilla JS)
│   └── error.html
└── docs/
    ├── capabilities.md           ← what the app can do, mapped to services
    ├── how-it-works.md           ← every request traced hop by hop
    ├── services-in-depth.md      ← one deep-dive section per AWS service
    ├── step-1a-dynamodb.md       ← the learning log (one doc per build step)
    ├── step-1b-s3.md
    ├── step-2-cognito.md
    ├── step-3-iam-lambda.md
    ├── step-4-api-gateway.md
    ├── step-5-frontend.md
    └── step-6-testing.md
```

Each **step** doc contains: what was created, a diagram, key concepts, the bug we
hit, drills, **interview questions it unlocks**, and cost notes.

The three **concept** docs (capabilities / how-it-works / services-in-depth) are
the "explain it in an interview" layer on top of the build log.

## 🧭 Key decisions

| # | Decision | Rationale |
|---|---|---|
| D1 | **Region `eu-central-1` (Frankfurt)** | GDPR / EU data residency for an EU-facing product |
| D2 | **DynamoDB `PAY_PER_REQUEST`** | No capacity planning; inside Free Tier |
| D3 | **`userId` = partition key from JWT `sub`** | Tenant isolation — users can only ever read their own data |
| D4 | **Presigned URLs for uploads** | Files go browser→S3 directly; no public bucket, no big Lambda payloads |
| D5 | **One router Lambda** | Fewer cold starts, one deploy unit |
| D6 | **HTTP API (not REST API)** | ~70% cheaper, native JWT authorizer — all we need |
| D7 | **Resource tagging** `Project`/`Owner` | Cost attribution (FinOps) |

## 🚀 Deploy from scratch (the short version)

```bash
# 1. data
aws dynamodb create-table --table-name expense-tracker-expenses \
  --attribute-definitions AttributeName=userId,AttributeType=S AttributeName=expenseId,AttributeType=S \
  --key-schema AttributeName=userId,KeyType=HASH AttributeName=expenseId,KeyType=RANGE \
  --billing-mode PAY_PER_REQUEST

# 2. receipts bucket (private + CORS + AES256)   [see docs/step-1b-s3.md]
# 3. cognito user pool + public app client + PreSignUp trigger  [docs/step-2-cognito.md]
# 4. IAM role + policy, then deploy both Lambdas from backend/  [docs/step-3-iam-lambda.md]
# 5. API Gateway HTTP API + JWT authorizer + 7 routes  [docs/step-4-api-gateway.md]
# 6. web bucket (public policy + website hosting) and upload app/  [docs/step-5-frontend.md]
```

## 💸 Cost

Everything runs inside the AWS Free Tier for this workload (≈ **$0/month**).
Free-tier highlights: DynamoDB 25 GB, Lambda 1M requests, Cognito 10k MAU,
API Gateway 1M requests, S3 5 GB.

### 🧹 Teardown (if you ever want to stop everything)

```bash
aws apigatewayv2 delete-api --api-id 4haajttqgh
aws lambda delete-function --function-name expense-tracker-api
aws lambda delete-function --function-name expense-tracker-autoconfirm
aws dynamodb delete-table --table-name expense-tracker-expenses
aws s3 rm s3://expense-tracker-receipts-896618135736 --recursive
aws s3api delete-bucket --bucket expense-tracker-receipts-896618135736
aws s3 rm s3://expense-tracker-web-896618135736 --recursive
aws s3api delete-bucket --bucket expense-tracker-web-896618135736
aws cognito-idp delete-user-pool --user-pool-id eu-central-1_jswIynPzT
aws iam delete-role-policy --role-name expense-tracker-lambda-role --policy-name expense-tracker-lambda-policy
aws iam delete-role --role-name expense-tracker-lambda-role
```

## 🔭 Phase 2 (deferred on purpose)

CloudFront + HTTPS custom domain · Textract OCR on receipts · budgets/targets ·
Cognito groups for RBAC · CI/CD pipeline · full CloudFormation IaC.
