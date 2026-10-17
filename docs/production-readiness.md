# Production readiness & real-world testing

Two questions answered here: **"is this production-grade?"** (not yet — here's
exactly what's missing) and **"how do I test it for real?"** (here's the tool we
built and the numbers it produced).

---

## 0. How to access the app right now

| Thing | Value |
|---|---|
| **Web app (HTTPS)** | https://d3ssxu6u8n5flg.cloudfront.net |
| **API base** | https://4haajttqgh.execute-api.eu-central-1.amazonaws.com |
| **Demo user** | `demo.cijo@example.com` / `Testpass1` |
| **Region** | `eu-central-1` (Frankfurt) |
| **Status** | HTTPS via CloudFront ✅ · custom domain ✅ · receipt OCR ✅ · IaC ✅ · tests + CI ✅ — see §2 |
| **Custom domain** | https://worldofvpc.online ✅ (Route 53 + ACM — see [step 8](step-8-custom-domain.md)) |

> Anyone with the URL can use the app; they can only ever see **their own**
> expenses, because the partition key is their Cognito `sub`. Try it: sign up a
> second account and watch it start empty.

---

## 1. Real-world testing — what we actually ran

Tool: [`scripts/loadtest.py`](../scripts/loadtest.py) — stdlib only, signs in,
fires N concurrent requests, reports throughput + **p50/p90/p99** latency +
error rate. Read-only by default, so it's safe against the live stack.

```bash
python3 scripts/loadtest.py --requests 400 --concurrency 40 --mix read
python3 scripts/loadtest.py --requests 400 --concurrency 8  --mix read
python3 scripts/loadtest.py --requests 100 --concurrency 5  --mix write
```

### Result A — concurrency 40 ❌ (found a real limit)

```
requests 400 · concurrency 40 · wall 8.58 s · throughput 46.6 req/s
succeeded 357 (89.2%)   errors 43 (10.8%)
latency  p50 773 ms  p90 876 ms  p99 1653 ms  max 1711 ms
error codes: {503: 43}
```

**Diagnosis (this is the valuable part).** We did not guess — we went to the
metrics:

```bash
aws lambda get-account-settings --query 'AccountLimit.ConcurrentExecutions'   # -> 10
aws cloudwatch get-metric-statistics --namespace AWS/Lambda --metric-name Throttles ...
  # -> 23 throttles in the busy minute
```

**Root cause:** this AWS account has a **Lambda concurrency limit of 10** (the
default for new accounts). At 40 concurrent requests, Lambda refused the extra
invocations, so API Gateway returned **503 Service Unavailable**.

**Lesson:** serverless "scales automatically" *up to your account limits*. A load
test is how you discover where the ceiling is — and the answer is always in
CloudWatch, never in a guess.

### Result B — concurrency 8 ✅ (under the ceiling)

```
requests 400 · concurrency 8 · wall 37.44 s · throughput 10.7 req/s
succeeded 400 (100.0%)   errors 0 (0.0%)
latency  p50 722 ms  p90 811 ms  p99 983 ms  max 1460 ms
```

**100% success, zero errors.** Throughput is capped at ~10.7 req/s *because we
deliberately stayed under the 10-concurrent limit* — that's the point of the test.

### Why is p50 ~720 ms?

Not the backend. The test client runs in **India**, the stack in **Frankfurt**,
and Python's `urllib` opens a **fresh TLS connection on every request**. So each
call pays several round trips (TCP + TLS handshake + request + response) at
~120 ms RTT. A keep-alive client (`requests.Session`, `httpx`, or a browser)
reuses the connection and cuts this a lot.

**Interview gold:** "my first load test showed 503s; I traced it to the account's
Lambda concurrency limit of 10 via the Throttles metric, not a code bug. Below
that ceiling we got 100% success. The client-side latency was dominated by
cross-continent RTT plus per-request TLS handshakes, which a connection-pooling
client removes."

### The other kinds of "real-world" testing (checklist)

| Type | How | Status |
|---|---|---|
| **Load / performance** | `scripts/loadtest.py` (above) | ✅ done |
| **Security — auth bypass** | call the API with no / a tampered / an expired token → expect `401`, and verify **Lambda never runs** in CloudWatch | ✅ done |
| **Security — tenant isolation** | sign in user B, call with user A's token → only A's data | ✅ done |
| **Unit / regression** | `pytest` + `moto` over every route (offline) | ✅ done (36 tests) |
| **AI extraction — failure paths** | blurry/PDF image, low confidence, Bedrock error → row marked `needs_review` (never lost) | ✅ covered by `tests/test_ocr.py` |
| **Input fuzzing** | send bad JSON, negative amounts, 10 MB notes, unicode, SQL/NoSQL-ish strings | 🟡 partial (bad amounts/JSON covered by unit tests) |
| **Browser / device** | Chrome, Safari, Firefox, iOS Safari, small screens | ⬜ partial |
| **Accessibility** | keyboard-only run, contrast, screen-reader labels, Lighthouse a11y score | ⬜ todo |
| **Error/chaos** | throttle DynamoDB, expire URLs, pull the network mid-upload | ⬜ todo |
| **Cost/abuse** | concurrency bomb, huge uploads, spam sign-ups | ⬜ todo |
| **Recovery** | delete a resource, confirm the failure is graceful | ⬜ todo |

---

## 2. Production-ready? Honest gap analysis

Ordered by *what a reviewer would notice first*, not by effort.

### 🔴 P0 — must fix before anyone else uses it

| # | Gap | Why it matters | Fix | Status |
|---|---|---|---|---|
| P0-1 | **No HTTPS** (HTTP S3 website endpoint) | browsers warn, tokens/passwords travel in cleartext | **CloudFront** in front of the bucket (default `*.cloudfront.net` cert) | ✅ done |
| P0-2 | **No infrastructure as code** | the whole stack was built by hand — nobody can reproduce or review it | **CloudFormation** template ([`infra/template.yaml`](../infra/template.yaml)) | ✅ done |
| P0-3 | **No automated tests** | a refactor can silently break anything | **pytest + moto** — 36 offline unit tests ([`tests/`](../tests/)) | ✅ done |
| P0-4 | **No CI/CD** | deploys are manual `aws` commands run from one laptop | **GitHub Actions**: install deps → run tests on every push | ✅ CI done (deploy CD deferred) |
| P0-5 | **Lambda concurrency limit = 10** | load testing proved we 503 under modest traffic | request a quota increase (free) + set **reserved concurrency** deliberately | ⬜ open (AWS support ticket) |
| P0-6 | **OCR has no per-user rate limit** | a user could spam scans → Bedrock spend | per-user quota (a DynamoDB counter) + API Gateway throttling | ⬜ open |
| P0-7 | **No DLQ for failed S3 events** | a receipt that fails every retry is dropped silently | S3 → SQS → Lambda with a **dead-letter queue** | ⬜ open |
| P0-8 | **Vision models are prompt-injectable** | text *inside* a receipt image could try to steer the model | force a strict JSON schema + re-validate every field (partly done: the category allow-list) | 🟡 partial |

### 🟠 P1 — needed for a real product

| # | Gap | Why | Fix |
|---|---|---|---|
| P1-1 | **No monitoring/alarms** | you'd find out about outages from users | CloudWatch **alarms** on 5xx, Throttles, p99 → SNS/email; **X-Ray** tracing |
| P1-2 | **No request validation** on the API | junk reaches Lambda and burns money | API Gateway / Lambda schema validation + payload size limits |
| P1-3 | **No rate limiting / WAF** | one script can hammer the API | AWS **WAF** rate-based rules, API Gateway throttling, or usage plans |
| P1-4 | **No account recovery / MFA** | users can't reset a forgotten password | Cognito **forgot-password** flow, optional TOTP MFA |
| P1-5 | **Token refresh not implemented** | sessions die after ~1 h | use the **RefreshToken** (`REFRESH_TOKEN_AUTH`) silently |
| P1-6 | **No backups / PITR** | one bad delete = data gone | DynamoDB **point-in-time recovery**; S3 **versioning** |
| P1-7 | **Single region** | a regional outage = downtime | multi-region (DynamoDB global tables + CloudFront), or at least documented RTO/RPO |
| P1-8 | **No cost guardrails at app level** | abuse grows the bill | per-user quotas, AWS Budgets + anomalies (we already have 2 budgets) |

### 🟡 P2 — polish / scale

| # | Gap | Fix |
|---|---|---|
| P2-1 | Client-side filtering only | server-side filters + a **GSI** for cross-user analytics |
| P2-2 | `receiptKey` set before upload completes | confirm via an **S3 event → Lambda** on `ObjectCreated` |
| P2-3 | No pagination on `/expenses` | DynamoDB `LastEvaluatedKey` + `?cursor=` |
| P2-4 | Single Lambda for all routes | split by domain; add a **Lambda layer** for shared code |
| P2-5 | 5 MB upload cap | direct-to-S3 multipart for large files |
| P2-6 | No i18n | German/English UI (relevant for the DE market) |

### ✅ Already production-shaped (don't undersell these)

- **Least-privilege IAM** — one table, one bucket prefix, nothing else.
- **Separate roles per function** — the API Lambda can't call Bedrock; the OCR Lambda can't touch Cognito or presign URLs.
- **AI, defensively** — OCR failures degrade to `needs_review`; the model's output is validated against an allow-list, never trusted raw.
- **Private object storage** — no public objects; 300-second signed URLs only.
- **Auth at the edge** — bad JWTs are rejected before compute, so attackers are free to reject.
- **Encryption at rest** (SSE-S3) and **data residency** in the EU — including the `eu.*` Bedrock inference profile, so receipt images stay in the EU.
- **Structured data model** with tenant isolation by key design.
- **Zero idle cost** — the architecture is fundamentally cheap.

> **How to say it:** "It's a production-*shaped* architecture, not a production
> *deployment*. The data and auth layers are already least-privilege and
> GDPR-placed in Frankfurt. What's missing is the operational wrapper: HTTPS via
> CloudFront, IaC, CI/CD, alarms, and quotas — that's P0."

---

## 3. Cost at scale (why serverless is the right call here)

| Traffic | Lambda | API GW | DynamoDB | S3 | ≈ total/mo |
|---|---|---|---|---|---|
| **Demo (now)** | $0 (free) | $0 (free) | $0 (free) | ~$0 | **~$0** |
| 10k users, 1k ops each | ~$0.20 | ~$0.10 | ~$0.10 | ~$0.10 | **< $1** |
| 100k users, 1k ops each | ~$2 | ~$1 | ~$1 | ~$1 | **~$5** |

The point: **cost scales with usage, not with existence.** The expensive part of
most systems is the idle server. We have none.

---

## 4. Your next three actions (in order)

1. **Request a Lambda concurrency quota increase** (P0-5 — the last open P0) and
   re-run `scripts/loadtest.py --concurrency 40` to prove the fix.
2. **Add an alarm** on the API Lambda's 5xx/Throttles + the OCR Lambda's errors
   (P1-1), and a **per-user scan quota** so Bedrock spend can't be abused (P0-6).
3. **Push the repo to GitHub** so the Actions workflow (already committed) runs
   green on every push, and extend it with a `deploy` job.
