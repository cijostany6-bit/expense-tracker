# How it works — every request traced, hop by hop

This is the file to read before an interview. Pick any user action and follow
the bytes.

---

## 🧭 The 7 pieces and their one-line jobs

| Piece | Job | Analogy |
|---|---|---|
| **S3 (web bucket)** | serves the 3 static files | the shop window |
| **Cognito** | proves *who* you are | passport office |
| **API Gateway** | the front door + bouncer | reception desk |
| **Lambda** | the worker doing the logic | the clerk |
| **IAM role** | the clerk's ID badge | building access card |
| **DynamoDB** | keeps the records | filing cabinet |
| **S3 (receipts)** | keeps the attachments | locked storeroom |
| **CloudWatch** | keeps the diary of what happened | CCTV + log book |

---

## ① FLOW: sign in  (browser → Cognito → JWT)

```
 Browser                     Cognito user pool
   │                                │
   │  POST https://cognito-idp.eu-central-1.amazonaws.com/
   │  X-Amz-Target: ...InitiateAuth │
   │  { AuthFlow: USER_PASSWORD_AUTH,
   │    ClientId, USERNAME, PASSWORD}
   │ ───────────────────────────────►
   │                                │  1. look up the user
   │                                │  2. verify password hash (SRP/hash in pool)
   │                                │  3. sign a JWT with the pool's private key
   │  ◄───── { IdToken, AccessToken, RefreshToken }
   │
   │  (the app keeps IdToken in memory only)
```

**Why no server?** Cognito *is* the server. We never store a password and never
write auth code.

**Key claims inside the IdToken:**
`sub` (unique user id ← becomes our partition key), `email`, `aud` (= the app
client id, checked by API Gateway), `iss` (= the user pool), `exp`, `iat`.

**Depth:** the token is signed with a **private key** Cognito holds. The matching
**public keys** are published at
`https://cognito-idp.<region>.amazonaws.com/<poolId>/.well-known/jwks.json`.
That's why API Gateway can verify a token with **no network call to Cognito**
and **no shared secret**. That is real, asymmetric JWT verification.

---

## ② FLOW: add an expense  (the main path)

```
Browser                API Gateway            Lambda              DynamoDB
  │                        │                    │                    │
  │ POST /expenses         │                    │                    │
  │ Authorization: <IdToken>                    │                    │
  │ {amount, category…}    │                    │                    │
  │ ──────────────────────►│                    │                    │
  │                        │ 1. fetch Cognito JWKS (cached)          │
  │                        │ 2. verify signature + iss + aud + exp   │
  │                        │    ❌ invalid → 401, Lambda never runs   │
  │                        │ 3. build event{requestContext.          │
  │                        │    http.method, rawPath, body,          │
  │                        │    authorizer.jwt.claims}               │
  │                        │ ──────────────────►│                    │
  │                        │                    │ 4. router matches   │
  │                        │                    │    POST /expenses   │
  │                        │                    │ 5. userId = claims.sub
  │                        │                    │ 6. validate amount  │
  │                        │                    │ 7. PutItem          │
  │                        │                    │ ──────────────────►│
  │                        │                    │ 8. 200 OK           │
  │                        │                    │ ◄──────────────────│
  │                        │ 9. return {statusCode, headers, body}   │
  │ ◄──────────────────────│                    │                    │
  │ 10. re-render the list │                    │                    │
```

**Steps 1–3 are the whole point of API Gateway.** Lambda receives a *verified
identity*, not a token to trust. The `sub` claim is trustworthy because the
signature was checked at the edge.

**Tenant isolation in one line:**
```python
user_id = event["requestContext"]["authorizer"]["jwt"]["claims"]["sub"]
table.put_item(Item={"userId": user_id, ...})     # never from the request body
```
Because `userId` is the **partition key**, `Query(userId == sub)` can only ever
return that user's rows. There is no `WHERE user_id = ?` to forget.

---

## ③ FLOW: list expenses

```
GET /expenses  →  Lambda  →  DynamoDB Query(Key("userId").eq(sub))
```
*Not* a `Scan`. A `Scan` reads the whole table and would (a) be slow, (b) cost
much more, (c) return other users' data. Using the partition key is both the
correct and the cheap option.

**Depth — why DynamoDB is fast:** it hashes the partition key to pick a
*physical partition*. All of one user's items live together, so a Query touches
one partition. Scale means more partitions, not slower queries.

---

## ④ FLOW: upload a receipt  (the clever one)

```
Browser                API Gateway → Lambda            S3
  │                        │                              │
  │ POST /expenses/{id}/receipt-url                       │
  │ ──────────────────────►│  Lambda:                     │
  │                        │  key = receipts/{sub}/{id}   │
  │                        │  presign PUT (SigV4, 300s)   │
  │ ◄── { uploadUrl } ─────│                              │
  │                                                       │
  │ PUT <uploadUrl>  body=file  (goes STRAIGHT to S3, not through Lambda)
  │ ─────────────────────────────────────────────────────►│
  │ ◄───────────────────────────────────── 200 OK ────────│
```

**Why presigned instead of streaming through Lambda?**
- API Gateway caps payloads (~10 MB) and Lambda bills for time the bytes sit in memory.
- The bucket stays **fully private** — no public objects, no bucket policy.
- The URL is **time-limited** (300 s) and scoped to exactly one object key.

**Depth — how a presigned URL works:** Lambda signs a *specific* request
(`PUT` this key) with its temporary credentials and puts the signature in the
query string. S3 re-computes the signature and compares. No session, no
password — just a signed, expiring permission slip.

**Gotcha we hit:** signing against `s3.amazonaws.com` (global) → **307
redirect** for non-us-east-1 buckets. Fix: sign against
`s3.eu-central-1.amazonaws.com`. See `docs/step-1b-s3.md`.

---

## ⑤ FLOW: preview a receipt

```
GET /expenses/{id}/receipt-url → Lambda: HeadObject (does it exist?)
                                        ├─ no  → 404 (nice error)
                                        └─ yes → presign GET (300s) → <img src=…>
```
**Depth:** we needed `s3:ListBucket` for S3 to answer **404** instead of **403**
on a missing key — S3 hides object existence from principals that can't list.
Classic IAM/S3 subtlety.

---

## ⑥ FLOW: edit and delete

```
PUT    /expenses/{id}  → UpdateItem(UpdateExpression="SET …",
                                     ConditionExpression="attribute_exists(expenseId)")
DELETE /expenses/{id}  → DeleteItem(…, ReturnValues="ALL_OLD")  ← 404 if nothing was there
```
**Depth:** the `ConditionExpression` makes the write *atomic and safe* — it
fails cleanly if the item doesn't exist instead of silently creating a partial
row. That's DynamoDB's answer to a race condition.

Two more DynamoDB subtleties we hit:
1. **`DATE` is a reserved word** → must be aliased: `SET #date = :d` +
   `ExpressionAttributeNames={"#date":"date"}`.
2. **Unused aliases are rejected** → only pass `ExpressionAttributeNames` when
   the alias is actually used in the expression.

---

## 🗄️ Data model

```
DynamoDB: expense-tracker-expenses        S3: receipts/{userId}/{expenseId}

userId      (PK, HASH)   ← Cognito sub  (tenant boundary)
expenseId   (SK, RANGE)  ← uuid4        (unique per item)
amount      (N)
currency    (S)  EUR|USD|INR|GBP
category    (S)  food|travel|rent|…
date        (S)  YYYY-MM-DD
note        (S)
receiptKey  (S)  receipts/{userId}/{expenseId}   ← set when a presigned PUT is issued
createdAt   (S)  ISO-8601
updatedAt   (S)  ISO-8601 (only after an edit)
```

**Why composite key `(userId, expenseId)`?** Two users can both have an expense
with the same `expenseId` without collision, and all of a user's data stays in
one partition → one fast Query.

---

## 💸 What one request costs (rough, Free Tier reality)

| Hop | Metered by | Our usage |
|---|---|---|
| API Gateway HTTP API | per million requests | far inside 1M/mo free |
| Lambda | requests + GB-seconds | 128 MB × ~30 ms per call |
| DynamoDB on-demand | read/write request units | 1–2 RU/WU per call |
| S3 | storage + requests | KBs |
| Cognito | monthly active users | 1 user |
| CloudWatch Logs | ingest + retention | bytes |

**Verdict: effectively $0/month.** The architecture is *designed* to have no
idle cost — that's the actual business value of serverless, and a great answer
to "why did you choose this?".

---

## 🔒 Where it can fail (and what you'd do)

| Failure | Symptom | Fix |
|---|---|---|
| Token expired | 401 | refresh token flow (deferred) |
| Wrong audience | 401 | authorizer `aud` must equal the app client id |
| IAM too narrow | 500 + `AccessDenied` in logs | widen the specific action only |
| Hot partition | throttling | write sharding / better key |
| Presigned URL expired | 403 from S3 | regenerate (300 s TTL) |
| Upload > 5 MB | client guard + API limit | presigned POST with conditions, or multipart |
| Bad JSON body | 400 | we return a clean error instead of crashing |
