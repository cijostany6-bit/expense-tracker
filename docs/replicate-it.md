# Build it yourself — a checklist, not a lecture

The point of publishing these docs is that you can recreate this project. Here's
the path in order, with what each step teaches you and where people normally get
stuck. Anyone who has done this once can do it again on a blank account.

---

## Before you start

| Need | Note |
|---|---|
| An AWS account | free tier covers everything here at demo scale |
| AWS CLI installed + logged in | `aws configure` or `aws login` |
| Region | pick your own (`eu-central-1` for EU, `ap-south-2` for India) |
| Terminal + a text editor | that's it — no Terraform, no Docker needed |

**Rule that keeps costs near zero:** *pay-per-request / on-demand pricing for
everything*, and tear down at the end of the day.

---

## The build order (≈ a day, if you go straight through)

### 1 · DynamoDB — decide the data model *first*
Create the table, but spend your time on the key design: partition key = the
user's id, sort key = the record id. Everything else (cheap reads, free reads
inside Free Tier, automatic tenant isolation) falls out of that one decision.

> Stuck point: reaching for a `Scan`. Use `Query` with the partition key.

### 2 · S3 — private by default
Two buckets: one private for files, one public *policy only* for the website.
Turn **Block Public Access** on first, then allow exactly what you need.

> Stuck point: presigned URLs signed against `s3.amazonaws.com` in another region
> → HTTP 307. Sign against your regional endpoint.

### 3 · Cognito — never write auth code
Create the pool + a **public app client** (no secret, because browsers can't keep
secrets). Add a PreSignUp trigger so sign-up is instant during development.

> Stuck point: mixing up the **ID token** (identity → your API) and the **access
> token** (for AWS APIs). Use the ID token as your `Authorization` header.

### 4 · Lambda + IAM — the two questions
Write the handler, then create a role with **only** the actions on **only** the
resources it touches. Five DynamoDB actions on one table, three on one bucket.

> Stuck point: `AccessDenied` at runtime. Read CloudWatch — the *denied action*
> in the error tells you the one line of policy to add.

### 5 · API Gateway — the cheap front door
An **HTTP API** with a JWT authorizer. The crucial mental shift: **the gateway
verifies the token before your code runs**, so a 401 costs you nothing.

> Stuck point: forgetting CORS, so every browser call fails while `curl` works
> perfectly. Always test with a browser *and* a terminal.

### 6 · Frontend — three files, no framework
Structure, style, logic. Keep the token **in memory**, render on fetch, and use
presigned URLs so files never pass through your compute.

### 7 · Test like an attacker and a stranger
- no token → 401, and **no Lambda log line** (the real proof)
- user A's token → only user A's data
- a load test → find your concurrency ceiling and know where it lives in metrics

---

## How to make it *yours* (do at least two)

The architecture above is standard — **your project becomes original in the
deltas**. Pick two:

- **Different domain**: not expenses → tool lending, lab bookings, meal planning,
  clinic appointments, gig-payment ledger.
- **A second language**: rebuild the API in Go or Node; two languages side by
  side is a strong signal.
- **An event-driven addition**: an S3 upload that triggers a Lambda (this
  project's V3 uses this for OCR — see [`v3-blueprint.md`](v3-blueprint.md)).
- **Infrastructure as code**: rebuild the whole stack in CloudFormation/SAM.
- **CI/CD**: GitHub Actions running tests and deploying on push.
- **A queue**: SQS between two services, to learn retries and idempotency.

> **Interview advice:** a project you *reproduced* proves you can follow a guide.
> A project you *changed and can defend* proves you can engineer. Always be able
> to answer: *"what would you do differently now?"*

---

## Common pitfalls (all of which hit this build)

| Pitfall | Symptom | Fix |
|---|---|---|
| CORS forgotten | works in `curl`, fails in the browser | set `AllowMethods` / `AllowHeaders`, test with OPTIONS |
| Wrong region signing | `307` redirect on upload | sign against the regional S3 endpoint |
| IAM too narrow | `500` + `AccessDenied` in logs | add only the missing action |
| Reserved words | `DATE` in `UpdateExpression` | alias it with `ExpressionAttributeNames` |
| Token expired | `401` after ~1 hour | implement refresh, or re-login |
| Assuming serverless is unlimited | `503` under load | check your account's concurrency limit |
| Forgetting teardown | surprise bill | a teardown command list in your README |

---

## What to write about it

Whatever you build, document three things while they're still in your head:

1. **The decision** you made and the alternative you rejected.
2. **The bug** you hit and how you found it (the CloudWatch line, the metric).
3. **The trade-off** you'd revisit at 100× scale.

That's the entire difference between "I followed a tutorial" and "I built this."
