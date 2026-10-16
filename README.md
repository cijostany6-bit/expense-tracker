# Expense Tracker ☁️

A **serverless, multi-user expense tracker on AWS** — sign up, log expenses,
upload receipts, and see a spend summary. Built *and understood* service by
service: every step has a diagram, the decisions behind it, and drills to go
deeper.

> **Status:** ✅ **Portfolio-complete** (2026-10-16) · **Region:** `eu-central-1` (Frankfurt)
> **Stack:** Cognito · API Gateway · Lambda · DynamoDB · S3 · CloudFront · IAM · CloudWatch
>
> **New here?** Start with [`docs/capabilities.md`](docs/capabilities.md) (what it
> does), then [`docs/how-it-works.md`](docs/how-it-works.md) (how a request flows),
> then [`docs/services-in-depth.md`](docs/services-in-depth.md) (the services).

## 🔗 Live

| Piece | URL |
|---|---|
| **Web app** (HTTPS) | https://d3ssxu6u8n5flg.cloudfront.net |
| **Learning site** (how this was built) | https://d3ssxu6u8n5flg.cloudfront.net/learn/ |
| API | https://4haajttqgh.execute-api.eu-central-1.amazonaws.com |
| Demo user | `demo.cijo@example.com` / `Testpass1` |

---

## 🗺️ Architecture

```
                        ┌─────────────────────────────┐
                        │  Browser                    │
                        └───────┬──────────────┬───────┘
                 HTTPS (TLS)    │              │  PUT file
                                ▼              │
                    ┌───────────────────┐      │
                    │  CLOUDFRONT       │      │
                    │  (HTTPS front)    │      │
                    └─────────┬─────────┘      │
                              │ origin HTTP    │
                              ▼                │
                    ┌───────────────────┐      │
                    │  S3  web (static) │      │
                    └───────────────────┘      │
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
| 8 | **CloudFront** | HTTPS front door for the S3 website | ✅ |
| 9 | **Infrastructure as Code** | full stack as a CloudFormation template | ✅ |
| 10 | **Automated tests + CI** | 21 pytest/moto unit tests, GitHub Actions on every push | ✅ |

### 🏁 Portfolio-complete checklist

- [x] Working, live, multi-user app (tenant-isolated by JWT `sub`)
- [x] **HTTPS** on the front door (CloudFront + `*.cloudfront.net` cert)
- [x] **Infrastructure as Code** — [`infra/template.yaml`](infra/template.yaml)
- [x] **Automated tests** — [`tests/`](tests/) (pytest + moto, offline)
- [x] **CI** — [`.github/workflows/ci.yml`](.github/workflows/ci.yml)
- [x] Least-privilege IAM, encryption at rest, EU data residency
- [x] Real load test + security test with written findings

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
| **CloudFront** | HTTPS front door for the SPA | *raw S3 website* → HTTP only, browser warns |
| **IAM** | Least-privilege access | *admin keys* → one leak = whole account |
| **CloudWatch** | Logs & debugging | *self-hosted* → need a server |
| **CloudFormation** | Reproducible infrastructure | *hand-built console* → nobody can review or rebuild it |

## 🗄️ Data model

| Entity | Keys / fields | Store |
|---|---|---|
| **Expense** | `userId` (PK) · `expenseId` (SK) · `amount` · `currency` · `category` · `date` · `note` · `receiptKey` · `createdAt` | DynamoDB |
| **Receipt** | `receipts/{userId}/{expenseId}` | S3 |

## 📁 Repo layout

```
expense-tracker/
├── README.md                     ← you are here
├── infra/
│   └── template.yaml             ← FULL STACK as CloudFormation (IaC)
├── backend/
│   ├── handler.py                ← all API routes (Python 3.12)
│   └── autoconfirm.py            ← Cognito PreSignUp trigger
├── tests/
│   ├── conftest.py               ← moto fixtures (offline AWS)
│   ├── test_handler.py           ← 21 unit tests for every route
│   └── requirements-dev.txt
├── .github/workflows/ci.yml      ← CI: install deps → run pytest on every push
├── pytest.ini
├── app/
│   ├── index.html                ← page structure
│   ├── styles.css                ← aurora theme (colourful, animated, responsive)
│   ├── app.js                    ← auth + CRUD + filters + chart (vanilla JS)
│   └── error.html
├── scripts/
│   └── loadtest.py               ← real load test: throughput, p50/p90/p99, errors
├── learn/
│   ├── index.html                ← the learning site (renders docs/*.md in the browser)
│   └── site.css
└── docs/
    ├── capabilities.md           ← what the app can do, mapped to services
    ├── how-it-works.md           ← every request traced hop by hop
    ├── services-in-depth.md      ← one deep-dive section per AWS service
    ├── production-readiness.md   ← prod gap analysis + the load-test results
    ├── replicate-it.md           ← "build this yourself" checklist
    ├── step-1a-dynamodb.md       ← the learning log (one doc per build step)
    ├── step-1b-s3.md
    ├── step-2-cognito.md
    ├── step-3-iam-lambda.md
    ├── step-4-api-gateway.md
    ├── step-5-frontend.md
    ├── step-6-testing.md
    └── step-7-hardening.md       ← HTTPS · IaC · tests · CI (this step)
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
| D8 | **CloudFront with the default `*.cloudfront.net` cert** | Instant HTTPS with no domain purchase; S3 website stays the origin |
| D9 | **pytest + moto for tests** | Full route coverage, runs offline and free in CI — no live AWS needed |
| D10 | **CloudFormation (not Terraform)** | AWS-native IaC; one template reproduces the whole stack |

## 🚀 Deploy from scratch

**Option A — Infrastructure as Code (recommended):**

```bash
# packages the Lambda code to S3, then creates the whole stack
aws cloudformation package \
  --template-file infra/template.yaml \
  --s3-bucket <your-artifact-bucket> \
  --output-template-file infra/packaged.yaml
aws cloudformation deploy \
  --template-file infra/packaged.yaml \
  --stack-name expense-tracker \
  --capabilities CAPABILITY_IAM
# then upload app/ to the web bucket and it is live behind CloudFront
```

**Option B — the manual build log (learn every service by hand):**

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
# 7. CloudFront in front of the web bucket for HTTPS
```

### 🧪 Test it locally (no AWS needed)

```bash
python3 -m venv .venv && .venv/bin/pip install -r tests/requirements-dev.txt
.venv/bin/pytest        # 21 tests, fully offline via moto
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
# CloudFront: disable first, wait, then delete
aws cloudfront get-distribution-config --id E2CBQ3WW5YO2WF > /tmp/cf.json
# (set "Enabled": false, then update-distribution, wait, then delete-distribution)
```

## 🔭 Phase 2 (deferred on purpose)

Custom domain + ACM certificate · budgets/targets · Cognito groups for RBAC ·
monitoring alarms & X-Ray · rate limiting / WAF.
