# What this app can actually do

A plain-language capability list — every feature mapped to the AWS service
that makes it happen. Use this as your "what did you build?" script.

---

## 👤 User-facing capabilities

| # | Capability | How the user sees it | Under the hood |
|---|---|---|---|
| 1 | **Create an account** | Email + password → instant access | `Cognito SignUp` + a **PreSignUp Lambda** auto-confirms & auto-verifies email |
| 2 | **Sign in / sign out** | Enter credentials, session in memory | `Cognito InitiateAuth` (`USER_PASSWORD_AUTH`) → **IdToken** |
| 3 | **Add an expense** | Amount, currency, category, date, note | `POST /expenses` → Lambda → **DynamoDB PutItem** |
| 4 | **Edit an expense** | ✏️ opens a modal, save changes | `PUT /expenses/{id}` → Lambda → **DynamoDB UpdateItem** |
| 5 | **Delete an expense** | 🗑️ + confirmation modal | `DELETE /expenses/{id}` → **DynamoDB DeleteItem** |
| 6 | **See all expenses** | Colour-coded list, newest first | `GET /expenses` → **DynamoDB Query** (by partition key) |
| 7 | **Search & filter** | 🔍 text search · category dropdown | Client-side over the fetched list |
| 8 | **Sort** | Newest / oldest / highest / lowest | Client-side |
| 9 | **Spend summary** | Animated bar chart per category | `/summary` server aggregation + client recompute per filter |
| 10 | **KPI dashboard** | Total · count · average · top category | Derived from the filtered data, animated counters |
| 11 | **Upload a receipt** | 📎 pick an image/PDF (≤5 MB) | `POST /expenses/{id}/receipt-url` → **presigned S3 PUT** from the browser |
| 12 | **View a receipt** | 📎 view → image in a modal | `GET /expenses/{id}/receipt-url` → **presigned S3 GET** |
| 13 | **Export to CSV** | ⬇ CSV button | Client-side blob, no server |
| 14 | **Keyboard-friendly** | `/` search · `Esc` close · `Enter` sign in | Plain JS listeners |

## 🔧 Technical capabilities (what you can defend in an interview)

| Capability | Why it matters |
|---|---|
| **Multi-tenant isolation** | The DynamoDB partition key is the JWT `sub` — a user literally *cannot* query another user's rows |
| **Auth at the edge** | API Gateway rejects a bad JWT **before Lambda runs** → 401s are free |
| **Least-privilege IAM** | The role can only touch 5 DynamoDB actions on one table + 3 S3 actions on one bucket prefix |
| **Private object storage** | The receipts bucket has *all* public access blocked; access is only via time-limited signed URLs |
| **Encryption at rest** | SSE-S3 (AES256) on the receipts bucket |
| **RESTful API** | 7 endpoints, proper verbs and status codes (200/201/400/401/404/500) |
| **Serverless / pay-per-use** | Zero idle cost; scales automatically with traffic |
| **Observability** | Every invocation logged to CloudWatch Logs; we debugged 3 real bugs from those logs |
| **Data residency** | Everything in `eu-central-1` (Frankfurt) — GDPR-friendly |
| **No build step** | 3 static files, vanilla JS; deploys with `aws s3 cp` |

## 🔌 The API (all routes require a valid JWT)

| Method | Path | Purpose | Success |
|---|---|---|---|
| `GET` | `/expenses` | List **your** expenses | `200` |
| `POST` | `/expenses` | Create an expense | `201` |
| `PUT` | `/expenses/{id}` | Update fields (partial) | `200` |
| `DELETE` | `/expenses/{id}` | Delete an expense | `200` / `404` |
| `POST` | `/expenses/{id}/receipt-url` | Presigned **upload** URL | `200` |
| `GET` | `/expenses/{id}/receipt-url` | Presigned **preview** URL | `200` / `404` |
| `GET` | `/summary` | Totals grouped by category | `200` |

## 🚫 Deliberately NOT built (and why) — say this in interviews

| Not built | Reason | Would add |
|---|---|---|
| Orgs / teams / RBAC | scope | Cognito **groups** → `cognito:groups` claim → Lambda authorisation |
| OCR of receipts | cost/complexity | **Textract** + async processing |
| Multi-currency conversion | needs a rate source | cached FX rates + Lambda |
| Budgets & alerts | would need scheduled jobs | **EventBridge Scheduler** + SNS |
| Recurring expenses | domain complexity | DynamoDB streams / EventBridge |
| HTTPS + custom domain | next step | **CloudFront** + ACM cert |
| Infrastructure as code | learning path | **CloudFormation** (Project C) |
| CI/CD | learning path | **GitHub Actions** (Project B/C) |
| Automated tests | time | pytest + moto, or SAM local |

> Rule of thumb: a strong answer names what you *chose not to do* and why. That
> shows judgment, not a lack of ideas.
