# Step 3 — IAM + Lambda (permissions & compute)

**Date:** 2026-10-16 · **Region:** `eu-central-1` · **Status:** ✅ deployed & Active

---

## 🎯 Goal

Run all the API logic serverlessly, with an execution role that can do
**exactly** what the app needs and nothing more.

## ⚙️ What was created

### The execution role (who Lambda *is*)

```bash
aws iam create-role --role-name expense-tracker-lambda-role \
  --assume-role-policy-document '{"Version":"2012-10-17","Statement":[{"Effect":"Allow",
    "Principal":{"Service":"lambda.amazonaws.com"},"Action":"sts:AssumeRole"}]}'
```

### The least-privilege policy (what it may *do*)

| Sid | Actions | Resource |
|---|---|---|
| `Logs` | `logs:CreateLogGroup/CreateLogStream/PutLogEvents` | this account's log groups |
| `ExpensesTable` | `dynamodb:PutItem/GetItem/Query/UpdateItem/DeleteItem` | **only** the expenses table ARN |
| `ReceiptsBucket` | `s3:PutObject/GetObject` | **only** `.../receipts/*` |

> Note there is **no** `dynamodb:Scan`, no `dynamodb:*`, no `s3:*`, and no
> wildcard resource. That is the whole point — a leaked function can't delete
> other tables or read other buckets.

### The functions

```bash
aws lambda create-function --function-name expense-tracker-api \
  --runtime python3.12 --handler _h.handler \
  --role arn:aws:iam::896618135736:role/expense-tracker-lambda-role \
  --timeout 15 --memory-size 128 \
  --environment "Variables={TABLE_NAME=expense-tracker-expenses,BUCKET_NAME=expense-tracker-receipts-896618135736}"

aws lambda create-function --function-name expense-tracker-autoconfirm \
  --runtime python3.12 --handler _a.handler --role ... --timeout 5
```

| Function | Runtime | Purpose |
|---|---|---|
| `expense-tracker-api` | python3.12 | all HTTP routes (routing done in-function) |
| `expense-tracker-autoconfirm` | python3.12 | Cognito PreSignUp trigger |

Source lives in `backend/handler.py` and `backend/autoconfirm.py`.

## 📊 Where it sits

```
   API Gateway ──invoke──► ┌──────────────────────────────────────┐
                           │  LAMBDA  expense-tracker-api          │
                           │  ── assumes ──► IAM role              │
                           │                 (temp credentials)    │
                           │                                       │
                           │  env: TABLE_NAME, BUCKET_NAME         │
                           └───────┬───────────────────────┬──────┘
                       DynamoDB    │                       │  S3
                    (5 actions on  │                       │  (2 actions on
                     one table)    ▼                       ▼   receipts/*)
                           ┌───────────────┐        ┌───────────────┐
                           │ DynamoDB      │        │ S3 (private)  │
                           └───────────────┘        └───────────────┘
                                   │
                                   ▼  stdout/logs
                           ┌───────────────┐
                           │ CloudWatch    │
                           │ Logs          │
                           └───────────────┘
```

**Two different "permissions" exist:** the **role** (Lambda → AWS services) and
the **resource policy** (API Gateway → invoke Lambda), added in step 4. A
resource policy is the *other* half of the handshake.

## 🧠 Key concepts learned

| Concept | Meaning here |
|---|---|
| **Trust policy vs permission policy** | Trust policy = *who may assume the role* (lambda.amazonaws.com). Permission policy = *what the role may do*. |
| **Least privilege** | Grant the specific actions on the specific ARNs, not `*`. |
| **Temporary credentials** | Lambda calls `sts:AssumeRole` behind the scenes and gets short-lived keys — no static keys stored anywhere. |
| **Resource policy** | The Lambda-side grant that lets API Gateway (or Cognito) invoke it, scoped by `SourceArn`. |
| **Embedded routing** | One Lambda handling many routes = fewer cold starts, simpler deploys. (Alternatives: one function per route, or API Gateway path-specific integrations.) |
| **Cold start** | First invocation after idle pays init cost. 128 MB + small zip keeps it low. |
| **`pathParameters`** | API Gateway extracts `{id}` for us; the in-function regex router also captures it defensively. |

## ⚠️ Bug we hit and fixed

The first router compared `rawPath` **literally** against `"/expenses/{id}"`,
so every `/expenses/<real-id>` call 404'd. Fixed by regex-matching the
templates and merging the captured groups into `event["pathParameters"]`.
Lesson: path templates are resolved by **API Gateway**, but if you ever build
your own router, you must implement the matching yourself.

## 🔬 Drills

```bash
# what exactly can the role do?
aws iam get-role-policy --role-name expense-tracker-lambda-role \
  --policy-name expense-tracker-lambda-policy

# who can invoke the functions?
aws lambda get-policy --function-name expense-tracker-api
aws lambda get-policy --function-name expense-tracker-autoconfirm

# configuration at a glance
aws lambda get-function-configuration --function-name expense-tracker-api \
  --query '{runtime:Runtime,timeout:Timeout,memory:MemorySize,env:Environment.Variables}'

# tail the logs while you call the API
aws logs tail /aws/lambda/expense-tracker-api --follow
```

## 🎯 Interview questions this unlocks

1. Difference between an **IAM role trust policy** and a **permissions policy**?
2. Why are roles better than long-lived access keys here?
3. How would you tighten this further? *(→ DynamoDB `ConditionExpression` on `userId`, S3 key conditions, resource tags, `aws:SourceArn` conditions — we already use one on the invoke permission)*
4. When would you use **one Lambda per route** instead of one router Lambda?
5. What causes cold starts and how do you reduce them? *(→ provisioned concurrency, SnapStart, smaller packages, keeping the handler warm)*
6. Where do Lambda logs go and how do you search them? *(→ CloudWatch Logs / Logs Insights)*
7. How do you safely pass config to a Lambda? *(→ env vars vs Secrets Manager vs SSM Parameter Store)*

## 💰 Cost

- Lambda free tier: **1M requests + 400,000 GB-seconds / month**.
- CloudWatch Logs: 5 GB ingest free (12-month).
- This workload: effectively **$0**.

## ⏭️ Next

**Step 4 — API Gateway**: the public front door, routes and the JWT authorizer.
