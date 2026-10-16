# Step 1b — S3 (receipt storage)

**Date:** 2026-10-16 · **Region:** `eu-central-1` · **Status:** ✅ created & locked down

---

## 🎯 Goal

A **private** bucket that stores receipt files, with the browser uploading
**directly to S3** via time-limited URLs — files never pass through Lambda.

## ⚙️ What was created

```bash
BUCKET=expense-tracker-receipts-896618135736

aws s3api create-bucket --bucket "$BUCKET" \
  --create-bucket-configuration LocationConstraint=eu-central-1

# block ALL public access (this bucket is private)
aws s3api put-public-access-block --bucket "$BUCKET" \
  --public-access-block-configuration '{"BlockPublicAcls":true,"IgnorePublicAcls":true,"BlockPublicPolicy":true,"RestrictPublicBuckets":true}'

# encrypt at rest (SSE-S3 / AES256 — free)
aws s3api put-bucket-encryption --bucket "$BUCKET" \
  --server-side-encryption-configuration '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"}}]}'

# CORS so the browser can PUT the file directly
aws s3api put-bucket-cors --bucket "$BUCKET" \
  --cors-configuration '{"CORSRules":[{"AllowedOrigins":["*"],"AllowedMethods":["PUT","GET","HEAD"],"AllowedHeaders":["*"],"ExposeHeaders":["ETag"],"MaxAgeSeconds":3000}]}'
```

| Property | Value |
|---|---|
| Bucket | `expense-tracker-receipts-896618135736` |
| Public access | 🚫 fully blocked |
| Encryption | AES256 (SSE-S3) |
| CORS | PUT/GET/HEAD from any origin (dev) |
| Object layout | `receipts/{userId}/{expenseId}` |

## 📊 Where it sits

```
  Browser ──(1) POST /expenses/{id}/receipt-url──► API GW ──► Lambda
                                                                 │
                                            generates presigned PUT│
     Browser ◄────────(2) {uploadUrl}──────────────────────────────┘
        │
        └──(3) PUT file ──────────────────────► S3  ✅ (no Lambda involved)
```

**Why presigned URLs?** Lambda API Gateway have a **10 MB** payload limit and
streaming `Content-Length` invocations do **not** count against the 6 MB
*response* limit, but a binary file through Lambda is slow and costly. A
presigned URL lets S3 receive the bytes directly, and the URL expires.

## 🧠 Key concepts learned

| Concept | Meaning here |
|---|---|
| **Presigned URL** | A URL signed with the caller's credentials + expiry. Anyone holding it can perform **one specific** action until it expires (300 s here). |
| **Block Public Access** | Account/bucket-level guardrails that override ACLs/policies. We keep them ON for private buckets. |
| **SSE-S3 vs SSE-KMS** | SSE-S3 (AES256) is free and automatic. SSE-KMS adds key control + audit but costs ~$1/key/month + per-request charges. |
| **CORS** | Browser security: the *bucket* must opt in to cross-origin PUTs, otherwise the preflight fails. |
| **Global vs regional endpoint** | `s3.amazonaws.com` is the global endpoint; for non-us-east-1 buckets it returns **`307 Temporary Redirect`** to `s3.<region>.amazonaws.com`. Clients that don't follow redirects for PUT (incl. plain `curl`, and risky in browsers) fail. **Fix: sign against the regional endpoint.** |

## ⚠️ Bug we hit and fixed (great interview story)

The first presigned URL came back as
`https://expense-tracker-receipts-896618135736.s3.amazonaws.com/...` and the PUT
returned **HTTP 307**. Because the bucket lives in `eu-central-1`, the global
endpoint redirects. Fixed in `backend/handler.py`:

```python
s3 = boto3.client(
    "s3",
    region_name=REGION,
    endpoint_url=f"https://s3.{REGION}.amazonaws.com",   # ← pin regional endpoint
    config=Config(signature_version="s3v4", s3={"addressing_style": "virtual"}),
)
```

Result: PUT → **200**, object visible at `receipts/<userId>/<expenseId>`.

## 🔬 Drills

```bash
# list the receipts
aws s3 ls s3://expense-tracker-receipts-896618135736/receipts/ --recursive

# confirm public access is blocked
aws s3api get-public-access-block --bucket expense-tracker-receipts-896618135736

# confirm encryption
aws s3api get-bucket-encryption --bucket expense-tracker-receipts-896618135736

# confirm CORS
aws s3api get-bucket-cors --bucket expense-tracker-receipts-896618135736

# try to fetch an object WITHOUT a signature (must be 403)
curl -s -o /dev/null -w "%{http_code}\n" \
  https://expense-tracker-receipts-896618135736.s3.eu-central-1.amazonaws.com/receipts/...
```

## 🎯 Interview questions this unlocks

1. How do you let a user upload to a **private** bucket without exposing it? *(→ presigned URLs / CloudFront OAC)*
2. Why presigned URLs instead of streaming the file through Lambda?
3. `403` vs `307` on a presigned PUT — what do they each mean?
4. SSE-S3 vs SSE-KMS vs SSE-C — trade-offs?
5. What does **Block Public Access** protect against?
6. Why must a bucket have **CORS** for browser uploads but not for server uploads?
7. How would you enforce a **max file size** and **content type** on the upload? *(→ presigned POST policy with conditions)*
8. How would you make receipts viewable later without making them public? *(→ presigned GET, short TTL)*

## 💰 Cost

- Storage: **5 GB free** (12-month) then ~$0.023/GB.
- Requests: 2,000 PUT / 20,000 GET per month free (12-month).
- AES256 encryption: **free** (unlike KMS).
- Status: negligible for a portfolio workload.

## ⏭️ Next

**Step 2 — Cognito** for sign-up / sign-in and the JWT that authorises every API call.
