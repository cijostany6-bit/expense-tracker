# Expense Tracker ☁️

A **serverless, multi-user expense tracker on AWS** — sign up, log expenses,
upload receipts, and see a spend summary. Built *and understood* service by
service: every step has a diagram, the decisions behind it, and drills to go
deeper.

> **Status:** ✅ **Portfolio-complete** (2026-10-16) · **V3 — receipt OCR + custom domain** (2026-10-17) · **Region:** `eu-central-1` (Frankfurt)
> **Stack:** Cognito · API Gateway · Lambda · DynamoDB · S3 · CloudFront · **Bedrock** · **Route 53** · **ACM** · IAM · CloudWatch
>
> **New here?** Start with [`docs/capabilities.md`](docs/capabilities.md) (what it
> does), then [`docs/how-it-works.md`](docs/how-it-works.md) (how a request flows),
> then [`docs/services-in-depth.md`](docs/services-in-depth.md) (the services).

## 🔗 Live

| Piece | URL |
|---|---|
| **Web app** (HTTPS) | https://d3ssxu6u8n5flg.cloudfront.net |
| **Web app** — custom domain | https://worldofvpc.online ✅ |
| **Learning site** (how this was built) | https://worldofvpc.online/learn/ |
| **Interactive course** (module by module) | https://worldofvpc.online/learn/course/ |
| **📄 Whole guide as a PDF** (87 pages, ~3 MB) | https://worldofvpc.online/learn/expense-tracker-guide.pdf |
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
     │  DYNAMODB    │◀──│  S3  receipts (private)         │
     │  expenses    │   │  receives the direct PUT        │
     └──────────────┘   └───────────────┬────────────────┘
              ▲                         │ ObjectCreated (prefix receipts/)
              │ UpdateItem              ▼
              │            ┌────────────────────────────────┐
              └────────────│  Lambda  expense-tracker-ocr   │
                           │  read image → Bedrock vision   │
                           └───────────────┬────────────────┘
                                           │ converse (eu.* profile → stays in EU)
                                           ▼
                           ┌────────────────────────────────┐
                           │  BEDROCK  Nova Lite (vision)   │
                           │  image → JSON {vendor, total…} │
                           └────────────────────────────────┘

     ┌──────────────┐
     │ CloudWatch   │  (logs from both Lambdas)
     └──────────────┘
```

## ✅ Build status

| Step | Service | What it does | Status |
|---|---|---|---|
| 1a | **DynamoDB** | stores expenses (PK `userId`, SK `expenseId`) | ✅ |
| 1b | **S3** | stores receipts (private, presigned URLs) | ✅ |
| 2 | **Cognito** | sign-up / sign-in, issues JWTs | ✅ |
| 3 | **IAM + Lambda** | CRUD + presign logic, least-privilege role | ✅ |
| 4 | **API Gateway** | HTTP API + JWT authorizer, 8 routes | ✅ |
| 5 | **S3 static** | hosts the frontend | ✅ |
| 6 | **Testing** | end-to-end + security verification | ✅ |
| 7 | **UI v2** | edit + receipt preview endpoints, colourful interactive frontend | ✅ |
| 8 | **CloudFront** | HTTPS front door for the S3 website | ✅ |
| 9 | **Infrastructure as Code** | full stack as a CloudFormation template | ✅ |
| 10 | **Automated tests + CI** | 36 pytest/moto unit tests, GitHub Actions on every push | ✅ |
| 11 | **Route 53 + ACM** | custom domain `worldofvpc.online` on HTTPS | ✅ |
| 12 | **Bedrock** | receipt OCR — photo of a bill → auto-filled expense | ✅ |

### 🏁 Portfolio-complete checklist

- [x] Working, live, multi-user app (tenant-isolated by JWT `sub`)
- [x] **HTTPS** on the front door (CloudFront) — and a **custom domain** (Route 53 + ACM)
- [x] **Receipt OCR** — upload a photo, [Bedrock](docs/step-9-receipt-ocr.md) fills the expense in
- [x] **Infrastructure as Code** — [`infra/template.yaml`](infra/template.yaml)
- [x] **Automated tests** — [`tests/`](tests/) (pytest + moto, offline, 36 tests)
- [x] **CI** — [`.github/workflows/ci.yml`](.github/workflows/ci.yml)
- [x] Least-privilege IAM, encryption at rest, EU data residency
- [x] Real load test + security test with written findings

## 🔌 API (all routes require a valid JWT)

| Method | Path | Purpose | Auth |
|---|---|---|---|
| `GET` | `/expenses` | list the caller's expenses | JWT |
| `POST` | `/expenses` | create an expense | JWT |
| `POST` | `/expenses/scan` | start a receipt scan → pending expense + presigned upload URL | JWT |
| `PUT` | `/expenses/{id}` | update fields of an expense | JWT |
| `DELETE` | `/expenses/{id}` | delete an expense | JWT |
| `POST` | `/expenses/{id}/receipt-url` | presigned S3 **upload** URL | JWT |
| `GET` | `/expenses/{id}/receipt-url` | presigned S3 **preview** URL | JWT |
| `GET` | `/summary` | totals grouped by category | JWT |

## ✨ What it can do

| Feature | Under the hood |
|---|---|
| Create account / sign in | Cognito (auto-confirm via PreSignUp Lambda) |
| **📷 Scan a receipt** | upload a photo → **Bedrock** reads it → expense auto-filled (vendor · date · total · category) |
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
| **Bedrock** (Nova Lite) | reads receipt images → structured JSON | *Textract* → purpose-built but **gated on this account**; *Rekognition* → raw text only, we'd own the parsing (see [step 9](docs/step-9-receipt-ocr.md)) |
| **Route 53 + ACM** | custom domain `worldofvpc.online` on HTTPS | *`*.cloudfront.net* → works, but not a real product name |
| **IAM** | Least-privilege access | *admin keys* → one leak = whole account |
| **CloudWatch** | Logs & debugging | *self-hosted* → need a server |
| **CloudFormation** | Reproducible infrastructure | *hand-built console* → nobody can review or rebuild it |

## 🗄️ Data model

| Entity | Keys / fields | Store |
|---|---|---|
| **Expense** | `userId` (PK) · `expenseId` (SK) · `amount` · `currency` · `category` · `date` · `note` · `receiptKey` · `createdAt` · **`vendor` · `status` · `ocrConfidence` · `ocrModel`** (V3) | DynamoDB |
| **Receipt** | `receipts/{userId}/{expenseId}` | S3 |

`status` drives the scan lifecycle: `pending → processed` (confident) or
`needs_review` (no amount / low confidence / any OCR error).

## 📁 Repo layout

```
expense-tracker/
├── README.md                     ← you are here
├── infra/
│   └── template.yaml             ← FULL STACK as CloudFormation (IaC)
├── backend/
│   ├── handler.py                ← all API routes (Python 3.12)
│   ├── ocr.py                    ← receipt OCR Lambda (S3 → Bedrock → DynamoDB)
│   └── autoconfirm.py            ← Cognito PreSignUp trigger
├── tests/
│   ├── conftest.py               ← moto fixtures (offline AWS)
│   ├── test_handler.py           ← 23 unit tests for every route (incl. /scan)
│   ├── test_ocr.py               ← 13 tests for the OCR pipeline (Bedrock stubbed)
│   └── requirements-dev.txt
├── .github/workflows/ci.yml      ← CI: install deps → run pytest on every push
├── pytest.ini
├── app/
│   ├── index.html                ← page structure
│   ├── styles.css                ← aurora theme (colourful, animated, responsive)
│   ├── app.js                    ← auth + CRUD + filters + chart + receipt scan
│   └── error.html
├── scripts/
│   ├── loadtest.py               ← real load test: throughput, p50/p90/p99, errors
│   ├── deploy-web.sh             ← safe S3 deploy (app + learn + PDF) + CF invalidation
│   ├── build-pdf.sh              ← render the whole site to ONE PDF (Chrome headless + pypdf)
│   └── pdf-merge.py              ← lossless PDF merge used by build-pdf.sh
├── learn/
│   ├── index.html                ← the learning site (renders docs/*.md in the browser)
│   ├── print.html                ← print/PDF build page (reuses the real renderers)
│   ├── site.css
│   └── course/
│       ├── index.html            ← the interactive course map + progress
│       ├── course.js             ← the course engine (modules, diagrams, quizzes)
│       ├── course.css
│       └── module-01-architecture.html
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
    ├── step-7-hardening.md       ← HTTPS · IaC · tests · CI
    ├── step-8-custom-domain.md   ← GoDaddy → Route 53 → ACM → CloudFront
    └── step-9-receipt-ocr.md     ← Bedrock vision: the receipt scanner
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
| D11 | **Bedrock vision, not Textract, for OCR** | Textract `AnalyzeExpense` is purpose-built but **gated on this account**; Bedrock (Nova Lite) returns structured JSON in one call and has an **EU inference profile** (keeps D1) |
| D12 | **Custom domain via Route 53 + ACM** | `worldofvpc.online` on HTTPS; ACM cert in **us-east-1** (CloudFront's rule), apex as an **alias** record |
| D13 | **Event-driven OCR (S3 → Lambda → Bedrock)** | Decouples a slow, failure-prone AI call from the user's request; the row renders instantly and the pipeline retries independently |

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
# 5. API Gateway HTTP API + JWT authorizer + 8 routes  [docs/step-4-api-gateway.md]
# 6. web bucket (public policy + website hosting) and upload app/  [docs/step-5-frontend.md]
# 7. CloudFront in front of the web bucket for HTTPS
# 8. OCR Lambda + IAM role + S3 ObjectCreated trigger  [docs/step-9-receipt-ocr.md]
# 9. Route 53 hosted zone + ACM cert (us-east-1) + CloudFront aliases  [docs/step-8-custom-domain.md]
```

### 🧪 Test it locally (no AWS needed)

```bash
python3 -m venv .venv && .venv/bin/pip install -r tests/requirements-dev.txt
.venv/bin/pytest        # 36 tests, fully offline via moto
```

### 🌐 Deploy the web app + learning site

```bash
scripts/deploy-web.sh   # syncs app/ + learn/ + docs/ + the PDF, and invalidates CloudFront
```

### 📄 Build the whole guide as one PDF

```bash
scripts/build-pdf.sh    # → dist/expense-tracker-guide.pdf  (all docs + the course)
```

It renders `learn/print.html` (which reuses the site's own renderers — `marked` for
the docs, `course.js` for the diagrams) in headless Chrome, **one part at a time**
(a single ~90-page job is unreliable), then stitches the parts losslessly with
`pypdf`. The generated file is git-ignored; `deploy-web.sh` publishes it to
`/learn/expense-tracker-guide.pdf` so it can be shared by link.

## 💸 Cost

Everything runs inside the AWS Free Tier for this workload — the only standing
cost is the **Route 53 hosted zone at $0.50/month**. Free-tier highlights:
DynamoDB 25 GB, Lambda 1M requests, Cognito 10k MAU, API Gateway 1M requests,
S3 5 GB, CloudFront 1 TB egress, ACM **free**.

| V3 add-on | Cost |
|---|---|
| Route 53 hosted zone | **$0.50 / month** |
| ACM certificate | free |
| Bedrock · Nova Lite (per receipt) | ~**$0.0001** (a fraction of a cent) |

### 🧹 Teardown (if you ever want to stop everything)

```bash
aws apigatewayv2 delete-api --api-id 4haajttqgh
aws lambda delete-function --function-name expense-tracker-api
aws lambda delete-function --function-name expense-tracker-autoconfirm
aws lambda delete-function --function-name expense-tracker-ocr
aws dynamodb delete-table --table-name expense-tracker-expenses
aws s3 rm s3://expense-tracker-receipts-896618135736 --recursive
aws s3api delete-bucket --bucket expense-tracker-receipts-896618135736
aws s3 rm s3://expense-tracker-web-896618135736 --recursive
aws s3api delete-bucket --bucket expense-tracker-web-896618135736
aws cognito-idp delete-user-pool --user-pool-id eu-central-1_jswIynPzT
aws iam delete-role-policy --role-name expense-tracker-lambda-role --policy-name expense-tracker-lambda-policy
aws iam delete-role --role-name expense-tracker-lambda-role
aws iam delete-role-policy --role-name expense-tracker-ocr-role --policy-name expense-tracker-ocr-policy
aws iam delete-role --role-name expense-tracker-ocr-role
# custom domain: remove the cert + hosted zone (and repoint GoDaddy away first)
aws acm delete-certificate --region us-east-1 --certificate-arn <arn>
aws route53 delete-hosted-zone --id Z03161453IVMM54X2ZJN6
# CloudFront: disable first, wait, then delete
aws cloudfront get-distribution-config --id E2CBQ3WW5YO2WF > /tmp/cf.json
# (set "Enabled": false, then update-distribution, wait, then delete-distribution)
```

## 🔭 Phase 2 (deferred on purpose)

Budgets/targets · Cognito groups for RBAC · monitoring alarms & X-Ray · rate
limiting / WAF · a `deploy` job in CI · push/WebSocket instead of polling.
