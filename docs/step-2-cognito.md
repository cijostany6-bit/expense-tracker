# Step 2 — Cognito (identity & authentication)

**Date:** 2026-10-16 · **Region:** `eu-central-1` · **Status:** ✅ working

---

## 🎯 Goal

Real user sign-up / sign-in without writing any password storage, hashing,
reset flows or MFA ourselves. Cognito issues a signed **JWT**; API Gateway
verifies it and tells Lambda *who* is calling.

## ⚙️ What was created

```bash
# 1) the user pool  (username = email)
aws cognito-idp create-user-pool \
  --pool-name expense-tracker-user-pool \
  --username-attributes email \
  --auto-verified-attributes email \
  --mfa-configuration OFF \
  --policies '{"PasswordPolicy":{"MinimumLength":8,"RequireUppercase":true,"RequireLowercase":true,"RequireNumbers":true,"RequireSymbols":false}}'

# 2) a PUBLIC app client (no secret — it runs in a browser)
aws cognito-idp create-user-pool-client \
  --user-pool-id eu-central-1_jswIynPzT \
  --client-name expense-tracker-web \
  --no-generate-secret \
  --explicit-auth-flows ALLOW_USER_PASSWORD_AUTH ALLOW_REFRESH_TOKEN_AUTH ALLOW_USER_SRP_AUTH \
  --prevent-user-existence-errors ENABLED

# 3) a PreSignUp Lambda trigger so sign-up auto-confirms (demo convenience)
aws cognito-idp update-user-pool --user-pool-id eu-central-1_jswIynPzT \
  --auto-verified-attributes email --mfa-configuration OFF \
  --policies '...' \
  --lambda-config PreSignUp=arn:aws:lambda:eu-central-1:896618135736:function:expense-tracker-autoconfirm
```

| Property | Value |
|---|---|
| User pool | `eu-central-1_jswIynPzT` (`expense-tracker-user-pool`) |
| App client | `4grucsnelng73rhl3c1kbasi7j` (no secret) |
| Sign-in | email + password (min 8, upper, lower, number) |
| MFA | off (demo) |
| PreSignUp trigger | `expense-tracker-autoconfirm` (auto-confirm + auto-verify) |

## 📊 Where it sits

```
   ┌──────────┐  (1) SignUp / InitiateAuth          ┌────────────────────┐
   │ Browser  │ ───────────────────────────────────►│  COGNITO           │
   │          │                                      │  user pool         │
   │          │ ◄─────────── (2) IdToken (JWT) ──────│  + PreSignUp λ     │
   └────┬─────┘                                      └────────────────────┘
        │ (3) call API with  Authorization: <IdToken>
        ▼
   ┌──────────────────┐  validate JWT signature,     ┌──────────┐
   │  API GATEWAY     │  issuer, audience, expiry    │ JWKS     │
   │  JWT authorizer  │◄────────────────────────────►│ (public  │
   └────────┬─────────┘                              │  keys)   │
            │ claims.sub → userId                    └──────────┘
            ▼
        Lambda
```

**Key idea:** Cognito signs tokens with a private key; the public keys (JWKS)
are published at a well-known URL, so API Gateway can verify tokens with **no
call back to Cognito and no shared secret**.

## 🧠 Key concepts learned

| Concept | Meaning here |
|---|---|
| **User pool** | The directory of users + password policy + MFA + triggers. |
| **App client** | How an application authenticates to the pool. *Public* client (SPA/mobile) = **no secret**; *confidential* (server) = secret. |
| **ID token vs access token** | **ID token** carries identity claims (`sub`, `email`) → used for the API authorizer (`aud` = client id). **Access token** is for Cognito's own APIs / scopes. |
| **JWT** | `header.payload.signature` — base64url parts. The payload is readable; the **signature** is what makes it trustworthy. |
| **`sub` claim** | Immutable unique user id — our DynamoDB partition key. Never the email (emails change). |
| **Lambda triggers** | Cognito calls your Lambda at lifecycle points (PreSignUp, PostConfirmation, PreTokenGeneration…). We use PreSignUp to auto-confirm. |
| **`prevent_user_existence_errors`** | Stops login from revealing whether an account exists (enumeration protection). |

## ⚠️ Gotcha we hit

`update-user-pool` **resets any setting you don't pass** to its default. Our
first call set only `--lambda-config`, which silently cleared
`AutoVerifiedAttributes`. Also `--username-attributes` is **create-only** and
errors on update. Lesson: always pass the full set of settings you care about
on an `update-user-pool` call, then **verify with `describe-user-pool`**.

## 🔬 Drills

```bash
POOL=eu-central-1_jswIynPzT; CLIENT=4grucsnelng73rhl3c1kbasi7j

# what does the pool look like now?
aws cognito-idp describe-user-pool --user-pool-id $POOL \
  --query 'UserPool.{triggers:LambdaConfig,mfa:MfaConfiguration,policies:Policies.PasswordPolicy}'

# create a user without an email flow (admin path)
aws cognito-idp admin-create-user --user-pool-id $POOL --username you@example.com \
  --user-attributes Name=email,Value=you@example.com --message-action SUPPRESS

# get a token and DECODE it (paste the middle part into base64url)
TOKEN=$(aws cognito-idp initiate-auth --auth-flow USER_PASSWORD_AUTH --client-id $CLIENT \
  --auth-parameters USERNAME=demo.cijo@example.com,PASSWORD=Testpass1 \
  --query 'AuthenticationResult.IdToken' --output text)
echo "$TOKEN" | cut -d. -f2 | base64 -d 2>/dev/null; echo

# the public keys Cognito signs with
curl -s https://cognito-idp.eu-central-1.amazonaws.com/$POOL/.well-known/jwks.json | python3 -m json.tool | head -20
```

## 🎯 Interview questions this unlocks

1. What's the difference between a **public** and **confidential** app client?
2. ID token vs access token vs refresh token — what is each for?
3. How does API Gateway verify a JWT **without calling Cognito**? *(→ JWKS + signature check)*
4. Where do you store tokens in a browser, and what are the XSS/CSRF trade-offs? *(→ memory vs localStorage vs httpOnly cookie)*
5. What is `USER_PASSWORD_AUTH` vs `USER_SRP_AUTH`, and why is SRP better? *(→ password never leaves the client)*
6. How do you do **roles/permissions** per user? *(→ Cognito groups → `cognito:groups` claim)*
7. How would you add **MFA**, **social login**, or **SAML** to this pool?
8. What's account-enumeration protection and why does it matter?

## 💰 Cost

- Cognito free tier: **10,000 monthly active users** — this app uses one.
- PreSignUp Lambda invocations: negligible.

## ⏭️ Next

**Step 3 — IAM + Lambda**: least-privilege execution role and the API logic.
