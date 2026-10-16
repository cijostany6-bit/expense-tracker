# The services, in depth

One section per service: the mental model, how it actually works inside, what
you must remember, the gotchas we hit, and interview questions. Read it service
by service — don't skim all seven at once.

---

## 1. 💾 DynamoDB — the record keeper

**Mental model:** a giant, infinitely-scalable hash map of *items*, grouped by
*partition*, addressed by a primary key. Not a SQL database; no joins, no
schemas to migrate, no server.

**How it works inside**
1. You write an item with a composite primary key `(partitionKey, sortKey)`.
2. DynamoDB hashes the partition key → picks a **physical partition**.
3. Items with the same partition key are stored **together, sorted by the sort key**.
4. Load grows → DynamoDB splits partitions automatically (**adaptive capacity**).
5. Reads: `PutItem`/`GetItem` (by key) end-to-end HTTP(S). `Query` = one
   partition, sorted and range-scannable. `Scan` = *whole table*, avoid.

**Billing modes**
- **On-demand** (`PAY_PER_REQUEST`): pay per read/write unit; no planning. ← we use this.
- **Provisioned**: you set RCU/WCU; cheaper at steady scale; risky if you guess wrong.

**What to remember**
- The **partition key should distribute traffic**. `userId` is good for tenant
  isolation but one whale user = one hot partition.
- A **sort key** enables `begins_with`, `between`, and range queries within a partition.
- **Reserved words**: `DATE`, `SIZE`, `NAME`, `STATUS`… must be aliased with
  `ExpressionAttributeNames`.
- `ConditionExpression` = optimistic concurrency / guard rails, evaluated atomically.
- Default reads are **eventually consistent**; `ConsistentRead=True` costs 2×.

**Gotchas we hit**
- `ValidationException: ExpressionAttributeNames unused` → don't pass aliases you don't use.
- `#date` needed because `DATE` is reserved.

**Interview Q&A**
- *Query vs Scan?* Query needs the key and touches one partition; Scan reads
  everything, is slow and expensive, and is a red flag in production.
- *When RDS instead?* relational integrity, joins, ad-hoc SQL, multi-entity transactions.
- *How to avoid hot partitions?* better key design, write sharding, on-demand + adaptive capacity.
- *Why no GSI yet?* our access pattern is "one user's items, newest first" —
  which the primary key already serves. A GSI (e.g. by category across users)
  would only be needed for cross-user analytics.

---

## 2. 📦 S3 — the storeroom + the shop window

**Mental model:** infinite object storage. A **bucket** holds **objects**
addressed by **key**. Not a filesystem (no real directories), not a database.
Also: it can serve **static websites**.

**How it works inside**
1. `PUT /bucket/key` → S3 stores the bytes + metadata in an **Availability Zone-redundant** way.
2. Buckets are globally named but **live in one region** (data residency!).
3. Access is controlled by **bucket policy** (resource-based) + **IAM**
   (identity-based) + **ACLs** (legacy) + **Block Public Access** (the safety net).
4. **Presigned URLs** move the signature into the query string so a browser can
   perform one specific action without credentials.
5. Website hosting (`IndexDocument`, `ErrorDocument`) is a *separate* endpoint
   (`s3-website.<region>…`) from the REST API endpoint.

**What to remember**
- **Block Public Access ON** for private buckets; a website needs a *bucket
  policy* allowing `s3:GetObject`, which requires public *policy* access but
  can keep public *ACL* access blocked.
- **Encryption**: SSE-S3 (free, AES256) vs SSE-KMS (key control + audit, costs).
- **Storage classes**: Standard → Infrequent Access → Glacier; lifecycle rules move objects.
- Presigned URLs **expire**; scope them to one key and short TTL.
- S3 returns **403 instead of 404** for missing keys if the caller lacks
  `s3:ListBucket` — existence hiding.

**Gotchas we hit**
- Global endpoint + non-us-east-1 bucket = **307 redirect** → sign regionally.
- Needed `s3:ListBucket` for correct 404s on `HeadObject`.

**Interview Q&A**
- *How do you let users upload to a private bucket?* presigned URLs (or CloudFront + OAC).
- *Block Public Access vs bucket policy?* BPA is a guardrail that overrides policy/ACL.
- *Versioning?* protects against overwrite/delete; costs storage.
- *How would you serve this over HTTPS on a domain?* CloudFront + ACM + OAC.

---

## 3. 🔑 Cognito — the passport office

**Mental model:** a managed directory of users that issues signed **JWTs**. You
get sign-up, sign-in, password policy, MFA, federation, and token refresh —
without storing a password.

**How it works inside**
1. A **user pool** holds users + password policy + triggers.
2. An **app client** is how an app talks to the pool. *Public* (browser/mobile,
   **no secret** — anyone can read JavaScript) vs *confidential* (server, has a secret).
3. Auth flows: `USER_PASSWORD_AUTH` (sends the password, TLS-protected),
   `USER_SRP_AUTH` (password never leaves the client — better),
   `REFRESH_TOKEN_AUTH`.
4. Success → **ID token** (identity: `sub`, `email`, `aud`), **access token**
   (for Cognito's own APIs/scopes), **refresh token** (get new ones silently).
5. **Lambda triggers** run your code at lifecycle points (PreSignUp,
   PostConfirmation, PreTokenGeneration…).
6. Public keys (JWKS) are published so *anyone* can verify tokens offline.

**What to remember**
- **ID token** = "who you are" → use for your API authorizer. **Access token** =
  "what you may call". They are not the same; mixing them up is a classic bug.
- `sub` is **immutable**; email is not. Use `sub` as a key.
- `update-user-pool` **resets unspecified settings** to defaults — always pass
  the full config and verify with `describe-user-pool`.
- `--username-attributes` is create-only.

**Gotcha we hit**
- Our `update-user-pool` call silently cleared `AutoVerifiedAttributes`.
- And the pool got its own `PreSignUp` Lambda trigger that made sign-up instant.

**Interview Q&A**
- *How does API Gateway trust a JWT without calling Cognito?* JWKS signature verification.
- *Where do you store tokens in a browser?* memory (safest-ish), localStorage
  (XSS risk), httpOnly cookie (CSRF risk) — trade-offs, no perfect answer.
- *How do you add roles?* Cognito **groups** → `cognito:groups` claim → check in
  Lambda (or a groups-based authorizer).
- *SRP vs USER_PASSWORD?* SRP proves knowledge of the password without sending it.

---

## 4. ⚡ Lambda — the clerk

**Mental model:** a function that runs on demand, in milliseconds, billed per
call + per GB-second. No servers. **Stateless** between invocations.

**How it works inside**
1. A request arrives → AWS finds (or starts) a **micro-VM** (Firecracker) with your runtime.
2. Cold start: create VM → download code → init runtime → run your handler.
   Subsequent calls may reuse the same **warm** sandbox (`/tmp` persists briefly).
3. Your function **assumes an IAM role** and gets **temporary credentials** via STS.
4. `print()` → CloudWatch Logs. Exceptions → logged + a failed invocation metric.
5. Concurrency: one execution per sandbox; more requests → more sandboxes (up to
   the account limit), then **throttling**.

**What to remember**
- **Stateless**: never assume `/tmp` or globals survive. (We create boto3 clients
  at module scope — a legitimate warm-start optimisation.)
- Increase **memory** → more *CPU* too; sometimes cheaper overall because it's faster.
- **Timeout** and **payload** limits are real design constraints.
- One Lambda handling many routes = fewer cold starts, simpler deploys (our choice).

**Interview Q&A**
- *What is a cold start and how do you reduce it?* provisioned concurrency,
  SnapStart, smaller packages, keep-warm, avoid heavy imports.
- *When NOT Lambda?* long-running jobs (>15 min), heavy GPU, steady high
  throughput where EC2 is cheaper, or stateful streaming.
- *How do you avoid a "fat Lambda"?* split by domain, use layers for shared code.

---

## 5. 🛡 IAM — the ID badge system

**Mental model:** the authorisation system for *everything* in AWS. Answers two
questions: **who may assume this role?** (trust policy) and **what may it do?**
(permission policy).

**How it works inside**
1. A **principal** (user, role, service) makes an API call.
2. AWS gathers every applicable policy: identity-based, resource-based,
   permissions boundary, SCP, session policy.
3. **Explicit deny wins** → else if any policy allows → allowed.
4. Temporary credentials come from **STS `AssumeRole`** (that's what Lambda does
   for you — no static keys anywhere).

**What to remember**
- **Least privilege** = specific actions on specific ARNs. We grant exactly:
  `PutItem/GetItem/Query/UpdateItem/DeleteItem` on one table,
  `PutObject/GetObject` on one prefix, `ListBucket` on one bucket, logs.
- **Resource policy** is the *other* half: it's how API Gateway and Cognito are
  allowed to invoke your Lambda (`SourceArn` = confused-deputy protection).
- Roles > users > long-lived access keys.

**Interview Q&A**
- *Trust policy vs permission policy?* who may assume vs what it may do.
- *Why no access keys in Lambda?* the role provides rotating temporary credentials.
- *How do you scope a role to one bucket?* resource ARN + optional conditions
  (`s3:prefix`, `aws:SourceArn`).

---

## 6. 🚪 API Gateway — the front door and bouncer

**Mental model:** a managed HTTP front door: routing, TLS, auth, CORS,
throttling, and scaling. It never holds your data.

**How it works inside**
1. A request hits the regional endpoint.
2. Routes match on **method + path**, optionally with `{pathParameters}`.
3. A **JWT authorizer** fetches (and caches) the issuer's JWKS, verifies the
   signature/`iss`/`aud`/`exp`, and injects **verified claims** into the event.
4. `AWS_PROXY` integration forwards the whole request as a JSON event and returns
   your `{statusCode, headers, body}` verbatim.
5. CORS preflight (`OPTIONS`) is answered by the gateway, not your code.

**HTTP API vs REST API**
| | HTTP API | REST API |
|---|---|---|
| Cost | ~70% cheaper | more |
| JWT authorizer | ✅ native | needs a Lambda authorizer |
| Usage plans / API keys | ❌ | ✅ |
| Request validation / WAF | limited | ✅ |
| Private endpoints | ❌ | ✅ |

We need routing + JWT → **HTTP API** is the right call.

**Interview Q&A**
- *Where does 401 come from?* the authorizer, before Lambda is invoked.
- *How do you rate-limit?* REST API usage plans, or WAF, or Lambda concurrency limits.
- *How do you version an API?* stage (`/v1`) or path prefix.

---

## 7. 📊 CloudWatch — the log book

**Mental model:** metrics, logs, alarms, dashboards. Lambda writes logs to
`/aws/lambda/<function>` automatically.

**How it works inside**
- Each invocation emits a log stream; `print()` lines and the platform's
  START/END/REPORT lines land there.
- Metrics (Invocations, Errors, Duration, Throttles) are aggregated automatically.
- **Logs Insights** lets you query with a SQL-like syntax.
- Alarms can trigger SNS/autoscaling/actions.

**How we used it:** `aws logs tail /aws/lambda/expense-tracker-api --follow`
found both the `ValidationException` and the `HeadObject 403` immediately. **Logs
are the debugger in serverless.**

**Interview Q&A**
- *How do you debug a Lambda without SSH?* logs + X-Ray/tracing + structured logging.
- *Cost control?* retention policy, log level discipline, metric filters.

---

## 🔗 How they fit together (the one paragraph)

A **browser** loads static files from **S3**. It authenticates against
**Cognito**, receiving a signed **JWT**. It calls **API Gateway**, which verifies
that JWT with **Cognito's public keys** and forwards verified claims to
**Lambda**. Lambda runs under an **IAM role** that can touch exactly one
**DynamoDB** table and one **S3** prefix. For uploads, Lambda hands the browser a
**presigned S3 URL** so bytes never pass through compute. Everything Lambda does
is written to **CloudWatch Logs**. No servers to patch, no idle cost, and
tenant isolation comes from making the JWT `sub` the DynamoDB partition key.
