# Step 5 — Frontend (static site on S3)

**Date:** 2026-10-16 · **Region:** `eu-central-1` · **Status:** ✅ live

---

## 🎯 Goal

A zero-dependency web UI, hosted cheaply, that talks straight to Cognito and
API Gateway from the browser — no web server, no build step, no SDK.

## ⚙️ What was created

```bash
WEB=expense-tracker-web-896618135736
aws s3api create-bucket --bucket $WEB --create-bucket-configuration LocationConstraint=eu-central-1

# a website MUST be publicly readable -> allow a public bucket POLICY
aws s3api put-public-access-block --bucket $WEB \
  --public-access-block-configuration '{"BlockPublicAcls":true,"IgnorePublicAcls":true,
    "BlockPublicPolicy":false,"RestrictPublicBuckets":false}'

aws s3api put-bucket-policy --bucket $WEB --policy \
  '{"Version":"2012-10-17","Statement":[{"Sid":"PublicRead","Effect":"Allow",
    "Principal":"*","Action":"s3:GetObject","Resource":"arn:aws:s3:::'$WEB'/*"}]}'

aws s3api put-bucket-website --bucket $WEB \
  --website-configuration '{"IndexDocument":{"Suffix":"index.html"},"ErrorDocument":{"Key":"error.html"}}'

aws s3 cp app/index.html  s3://$WEB/index.html  --content-type text/html
aws s3 cp app/error.html  s3://$WEB/error.html  --content-type text/html
```

**URL:** `http://expense-tracker-web-896618135736.s3-website.eu-central-1.amazonaws.com`

| Property | Value |
|---|---|
| Bucket | `expense-tracker-web-896618135736` |
| Access | public **read** via bucket policy (ACLs still blocked) |
| Hosting | S3 static website (index + error doc) |
| Auth | direct browser calls to `cognito-idp` (no SDK) |

## 📊 Where it sits

```
        ┌──────────────────────── Browser ─────────────────────────┐
        │  index.html (from S3 website endpoint, plain HTTP)        │
        │                                                           │
        │   sign-in ──HTTP POST──► cognito-idp.<region>.amazonaws   │
        │            ◄── IdToken (JWT) ─────────────────────────────│
        │                                                           │
        │   api call ──HTTP──► API Gateway  (Authorization: token)  │
        │   upload   ──HTTP PUT──► S3 presigned URL                 │
        └───────────────────────────────────────────────────────────┘
```

**Why this is safe despite HTTP:** the page is served over HTTP, but every
sensitive call it makes (Cognito, API Gateway, S3) is **HTTPS**. Mixed-content
blocking stops HTTP resources on an HTTPS page — not the reverse. In production
you'd front the S3 bucket with **CloudFront + an ACM cert** for real HTTPS.

## 🧠 Key concepts learned

| Concept | Meaning here |
|---|---|
| **Static site on S3** | Files only; the browser does all the work. No servers to patch or scale. |
| **Bucket policy vs ACL** | Policy-based public read is the modern way. Block Public ACLs can stay ON. |
| **Website endpoint vs REST endpoint** | `s3-website.<region>.amazonaws.com` supports index/error documents; the REST endpoint does not. |
| **No SDK needed** | Cognito's `SignUp` / `InitiateAuth` are plain JSON APIs — one `fetch` with an `X-Amz-Target` header. |
| **Token in the `Authorization` header** | The raw JWT (no `Bearer` prefix) as configured in the authorizer's `identity-source`. |
| **Presigned upload from JS** | `fetch(uploadUrl, {method:"PUT", body:file})` sends the file straight to S3. |

## ⚠️ Notes / simplifications (and what a real app would do)

- Token is held **in a JS variable** (memory) — XSS-safe-ish, lost on refresh.
  A real app would use refresh tokens + `httpOnly` cookies.
- `USER_PASSWORD_AUTH` sends the password to Cognito (over TLS). **SRP** would
  avoid sending it at all.
- Origin CORS is `*` for dev; production would pin the exact website/CloudFront
  origin.
- No CloudFront in front (planned as an extension) → no HTTPS, no CDN, no WAF.

## 🔬 Drills

```bash
WEB=expense-tracker-web-896618135736
aws s3 ls s3://$WEB/
curl -s -o /dev/null -w "%{http_code}\n" http://$WEB.s3-website.eu-central-1.amazonaws.com/
aws s3api get-bucket-policy --bucket $WEB
```

Open the site, sign up, add an expense, attach a receipt — then check the
DynamoDB item and the S3 object appear.

## 🎯 Interview questions this unlocks

1. How do you host a frontend cheaply with no servers? When is S3+CloudFront enough vs needing SSR?
2. Why is a public **bucket policy** needed, and how does Block Public Access interact with it?
3. Where should a SPA store JWTs, and what are the risks?
4. How does the browser upload a file straight to S3 without a backend?
5. Why is mixed content fine in one direction but not the other?
6. What would CloudFront add here? *(→ HTTPS/custom domain, caching, WAF, geo restrictions, OAC to keep S3 private)*

## 💰 Cost

- S3 website hosting: pennies. Serving a few KB per visit.
- No CloudFront cost yet (S3 → internet egress is cheap for tiny files).

## ⏭️ Next

**Step 6 — end-to-end verification** and turn the results into evidence.
