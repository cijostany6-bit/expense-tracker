# Step 7 — Portfolio hardening: HTTPS, IaC, tests & CI

Steps 1–6 built a working app. Step 7 makes it *look like engineering*: a
secure front door, reproducible infrastructure, an automated test suite, and
continuous integration. Four small additions, four big interview wins.

---

## 7.1 — HTTPS with CloudFront (the visible red flag)

**The problem.** The app was served from an **S3 website endpoint**, which only
speaks **HTTP**. Any browser shows "Not secure", and a demo over plain HTTP
sends a sign-in password in cleartext. That is the first thing a reviewer or
recruiter sees.

**The fix.** Put **CloudFront** in front of the bucket:

```
Browser ──HTTPS──▶ CloudFront ──HTTP──▶ S3 website endpoint
         (viewer side: TLS)   (origin side, AWS-internal)
```

Key settings:

| Setting | Value | Why |
|---|---|---|
| Origin | the S3 **website** endpoint | it already handles `index.html`, `error.html` and the `/learn/` directory |
| Viewer protocol policy | `redirect-to-https` | plain-HTTP requests get a 301 to HTTPS |
| Certificate | **CloudFront default** (`*.cloudfront.net`) | HTTPS **with no domain purchase** — the trick that makes this free |
| Price class | `PriceClass_100` | serve from US/EU edge locations only (cheapest) |
| Allowed methods | `GET, HEAD` | it's a static site; the JS talks to the API directly |

**Why not the alternatives.**
- *ACM cert + custom domain* → needs a domain; nice-to-have, not required for HTTPS.
- *Make the bucket private + Origin Access Control (OAC)* → more secure, but it
  breaks direct `s3-website` behaviour; the website endpoint is intentional here.
- *API Gateway as the front door* → wrong tool for serving HTML/CSS/JS.

**What we learned / gotcha.** The *viewer* leg is HTTPS, but the *origin* leg is
HTTP — that's fine because it stays inside AWS's network. And because both the
API CORS config and the receipts bucket CORS use `*`, moving the origin from the
S3 URL to the CloudFront URL needed **no backend changes**.

---

## 7.2 — Infrastructure as Code with CloudFormation

**The problem.** The whole stack was built by hand with `aws` CLI commands. It
works, but *nobody can review it, version it, or rebuild it* — which is exactly
what "DevOps" means.

**The fix.** [`infra/template.yaml`](../infra/template.yaml) describes the entire
stack declaratively: DynamoDB, both S3 buckets (+ policy + CORS), Cognito pool &
client, IAM role & policy, both Lambdas, API Gateway HTTP API + JWT authorizer +
7 routes, and the CloudFront distribution.

Deploy with the two-command package→deploy flow:

```bash
aws cloudformation package --template-file infra/template.yaml \
  --s3-bucket <artifact-bucket> --output-template-file infra/packaged.yaml
aws cloudformation deploy --template-file infra/packaged.yaml \
  --stack-name expense-tracker --capabilities CAPABILITY_IAM
```

`package` uploads the Lambda code to S3 and rewrites `Code: ../backend` into an
`S3Bucket`/`S3Key`; `deploy` creates the stack.

**What we learned.** `Ref`/`GetAtt` express **dependency order**: CloudFormation
figures out that the IAM role must exist before the Lambdas, that the pool must
exist before the authorizer, and so on. That ordering *is* the architecture
diagram, in code.

**Why CloudFormation, not Terraform.** The repo's principle: AWS-native IaC
first, so it's one less tool between the builder and the service. Terraform is a
deliberate later step.

---

## 7.3 — Automated tests with pytest + moto

**The problem.** No tests meant a refactor could silently break a route.

**The fix.** [`tests/`](../tests/) runs **21 unit tests** over every route using
**moto**, which mocks DynamoDB and S3 **entirely offline** — no AWS account, no
credentials, no cost. Identity is injected exactly the way API Gateway's JWT
authorizer injects it (the `sub` claim), so **tenant isolation is tested for
real**.

**The tests paid for themselves immediately — they found three real bugs:**

| Bug | Symptom before | Root cause | Fix |
|---|---|---|---|
| Bad `amount` | `500` | `Decimal("abc")` raises `decimal.InvalidOperation` (**an `ArithmeticError`**), which wasn't in the `except` list | also catch `InvalidOperation` → `400` |
| Delete missing expense | `200` (lied) | checked `"Attributes" in result`, but DynamoDB returns `Attributes: {}` | check truthiness → `404` |
| Presign for missing expense | `500` | the conditional `UpdateItem` raised `ConditionalCheckFailedException`, uncaught | catch it → `404` |

> **Interview gold:** "I wrote the test suite and it immediately surfaced three
> bugs — two of which returned a 500 where the API contract said 400/404. That's
> the argument for tests: they encode the contract."

**What we learned.** Moto's behaviour differs from real DynamoDB in useful ways —
it's *more lenient* on some edge cases, which forces you to write the check that
is correct for the real service (truthiness, not key-presence).

---

## 7.4 — CI with GitHub Actions

**The problem.** Nothing ran the tests automatically.

**The fix.** [`.github/workflows/ci.yml`](../.github/workflows/ci.yml): on every
push and pull request, install `tests/requirements-dev.txt` and run `pytest`.

```yaml
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }
      - run: pip install -r tests/requirements-dev.txt
      - run: pytest
```

Because the tests are offline (moto), CI needs **no AWS secrets** — a green
check on every push for zero cost and zero credential risk. A `deploy` job is
the natural next step.

---

## 💬 Interview questions this step unlocks

- **"Why CloudFront instead of just an ACM cert?"** — the default
  `*.cloudfront.net` cert gives HTTPS with no domain; ACM is only needed for a
  custom domain.
- **"How do you get a certificate for a custom domain?"** — ACM cert **in
  `us-east-1`** (CloudFront is global), validated, then attached to the
  distribution.
- **"How do you test serverless without a cloud account?"** — moto mocks the
  AWS APIs in-process; inject the same event shape API Gateway sends.
- **"What does `cloudformation package` do?"** — uploads local code to S3 and
  rewrites the template to point at it, so `deploy` only needs the template.
- **"Why `GetAtt` instead of `Ref`?"** — `Ref` returns the resource *name*;
  `GetAtt` returns an *attribute* like an ARN, which is what an IAM policy or a
  `LambdaConfig` needs.

## 💸 Cost

- CloudFront: free-tier covers 1 TB/month egress + 10M requests; this demo is
  far below it → **~$0**.
- CloudFormation, moto, GitHub Actions (public repo) → **free**.
