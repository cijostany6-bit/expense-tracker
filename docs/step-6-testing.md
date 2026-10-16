# Step 6 — End-to-end verification (Phase 1 complete)

**Date:** 2026-10-16 · **Region:** `eu-central-1` · **Status:** ✅ all green

---

## 🎯 Goal

Prove the whole chain works — and prove the **security** works too — using only
the public API (no console clicking).

## 🧪 Test 1 — the happy path

| # | Action | Result |
|---|---|---|
| 1 | `cognito-idp sign-up` (email + password) | `UserConfirmed: true` (PreSignUp trigger auto-confirmed) |
| 2 | `cognito-idp initiate-auth` (USER_PASSWORD_AUTH) | `IdToken` returned (1091 chars) |
| 3 | `GET /expenses` with **no** token | **HTTP 401** ✅ blocked at the edge |
| 4 | `POST /expenses` `{amount:250, category:food}` | `201` + item with `expenseId` |
| 5 | `GET /expenses` | returns the item, `count: 1` |
| 6 | `GET /summary` | `{"byCategory":{"food":250.0},"grandTotal":250.0}` |
| 7 | `POST /expenses/{id}/receipt-url` | presigned URL + `receiptKey` saved |
| 8 | `PUT` file to the presigned URL | **HTTP 200** |
| 9 | `aws s3 ls receipts/ --recursive` | object present at `receipts/<userId>/<expenseId>` |
| 10 | `DELETE /expenses/{id}` | `{"deleted": ...}`, item gone from the next list |

### Real captured output (excerpts)

```json
// POST /expenses
{"userId":"53d45842-...","expenseId":"1136e8b2-...","amount":42.5,
 "currency":"EUR","category":"travel","note":"Train ticket","date":"2026-10-16"}

// GET /summary
{"byCategory":{"travel":42.5,"food":250.0},"grandTotal":292.5,"count":2}

// DELETE /expenses/1136e8b2-...
{"deleted":"1136e8b2-24e5-4e06-ab19-d52219696aef"}
```

## 🧪 Test 2 — the security path

```bash
curl -s -o /dev/null -w "%{http_code}\n" $API/expenses        # no token       -> 401
curl -s -o /dev/null -w "%{http_code}\n" $API/expenses -H "Authorization: not.a.jwt"  # -> 401
```

The **401 happens before Lambda runs** — verified by the fact that nothing
appears in the function's CloudWatch logs for those calls.

## 🐛 Two real bugs found by testing (and fixed)

### Bug 1 — router didn't match path templates
`DELETE /expenses/{id}` and `POST /expenses/{id}/receipt-url` returned
`404 no route for ...`. The in-function router compared `rawPath` literally to
the template. **Fix:** regex-match templates and merge captured groups into
`pathParameters`. *(See `backend/handler.py`.)*

### Bug 2 — presigned PUT got HTTP 307
The URL was signed against the **global** endpoint `s3.amazonaws.com`, which
**redirects (307)** to the regional endpoint for non-us-east-1 buckets.
**Fix:** sign against `https://s3.eu-central-1.amazonaws.com` with SigV4 +
virtual addressing. Result: `PUT → 200`.

> These two are exactly the kind of thing an interviewer wants to hear: *what
> broke, why, and how you diagnosed it.*

## 📊 Final architecture (all components live)

```
                        ┌─────────────────────────────┐
                        │   Browser (S3 static site)   │  ✅
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
     │  expenses    │   │  ✅ receives the direct PUT      │
     └──────────────┘   └────────────────────────────────┘
              │
              ▼
     ┌──────────────┐
     │ CloudWatch   │
     │ Logs         │
     └──────────────┘
```

## 🔬 Re-run the tests yourself

```bash
cd expense-tracker
CLIENT=4grucsnelng73rhl3c1kbasi7j
API=https://4haajttqgh.execute-api.eu-central-1.amazonaws.com

TOKEN=$(aws cognito-idp initiate-auth --auth-flow USER_PASSWORD_AUTH --client-id $CLIENT \
  --auth-parameters USERNAME=demo.cijo@example.com,PASSWORD=Testpass1 \
  --query 'AuthenticationResult.IdToken' --output text)

curl -s $API/expenses -H "Authorization: $TOKEN"
curl -s $API/summary  -H "Authorization: $TOKEN"
```

## 🎯 What this proves to an interviewer

- The app is **real and working**, not a diagram.
- **Auth is enforced at the edge** (401 before compute).
- **Tenant isolation** works: the partition key is the JWT `sub`, so queries can
  only ever return the caller's rows.
- **Least privilege** is real (scoped actions/ARNs).
- You can **debug AWS** (307 redirect, path templates, Cognito update resets).

## ⏭️ Phase 2 — deliberately deferred (documented, not forgotten)

| Idea | Why it's out of Phase 1 | Where it goes |
|---|---|---|
| CloudFront + HTTPS + custom domain | extra moving parts | Project C |
| Textract OCR on receipts | cost/complexity | Project C |
| Athena / QuickSight analytics | out of scope for a tracker | Project C |
| Budgets/alerts per entity, RBAC/orgs | scope | Phase 2 |
| CI/CD (GitHub Actions → deploy) | DevOps theme | Project B/C |
| CloudFormation/IaC for all of this | IaC theme | Project C |
