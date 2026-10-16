# Step 4 — API Gateway (the public front door)

**Date:** 2026-10-16 · **Region:** `eu-central-1` · **Status:** ✅ deployed, all routes protected by JWT

---

## 🎯 Goal

A public HTTPS endpoint that (a) routes to Lambda, (b) **rejects any request
without a valid Cognito JWT before Lambda is even invoked**, and (c) handles
CORS for the browser.

## ⚙️ What was created

```bash
API_ID=$(aws apigatewayv2 create-api --name expense-tracker-api --protocol-type HTTP \
  --cors-configuration '{"AllowOrigins":["*"],"AllowMethods":["GET","POST","DELETE","OPTIONS"],
    "AllowHeaders":["authorization","content-type"],"MaxAge":3600}' --query ApiId --output text)

aws apigatewayv2 create-integration --api-id $API_ID --integration-type AWS_PROXY \
  --integration-uri arn:aws:lambda:eu-central-1:896618135736:function:expense-tracker-api \
  --payload-format-version 2.0

AUTH_ID=$(aws apigatewayv2 create-authorizer --api-id $API_ID --name cognito-jwt \
  --authorizer-type JWT --identity-source '$request.header.Authorization' \
  --jwt-configuration Issuer=https://cognito-idp.eu-central-1.amazonaws.com/eu-central-1_jswIynPzT,Audience=4grucsnelng73rhl3c1kbasi7j \
  --query AuthorizerId --output text)

# every route requires the JWT authorizer
for R in "GET /expenses" "POST /expenses" "DELETE /expenses/{id}" \
         "POST /expenses/{id}/receipt-url" "GET /summary"; do
  aws apigatewayv2 create-route --api-id $API_ID --route-key "$R" \
    --authorization-type JWT --authorizer-id $AUTH_ID --target integrations/<id>
done

aws apigatewayv2 create-stage --api-id $API_ID --stage-name '$default' --auto-deploy
```

| Property | Value |
|---|---|
| API | `expense-tracker-api` · id `4haajttqgh` |
| Type | **HTTP API** |
| Endpoint | `https://4haajttqgh.execute-api.eu-central-1.amazonaws.com` |
| Authorizer | `cognito-jwt` (issuer = user pool, audience = app client) |
| Stage | `$default` (auto-deploy) |
| Integration | `AWS_PROXY`, payload format **2.0** |

## 📊 Where it sits

```
 Browser ──HTTPS──► ┌──────────────────────────────────────────────┐
                    │            API GATEWAY  (HTTP API)           │
                    │                                              │
   no/!invalid JWT  │  ┌─────────────┐   valid JWT?                │
   ────────────────►│  │ JWT          │   ── yes ──► route match    │
        ❌ 401       │  │ authorizer   │              │              │
                    │  └─────────────┘              ▼              │
                    │        ▲                ┌───────────┐         │
                    │        │ verify against │ integration│        │
                    │   Cognito JWKS         └─────┬─────┘         │
                    └──────────────────────────────┼───────────────┘
                                                   │ AWS_PROXY (v2.0 event)
                                                   ▼
                                                Lambda
```

**Critical property:** an invalid token is rejected **at the edge**. Lambda
never runs, so an attacker hammering the endpoint doesn't burn your compute.

## 🧠 Key concepts learned

| Concept | Meaning here |
|---|---|
| **HTTP API vs REST API** | HTTP API is simpler/cheaper (~70% cheaper), fast, native JWT authorizers. REST API adds API keys, usage plans, request validation, private endpoints. We only need routing + JWT → HTTP API. |
| **AWS_PROXY integration** | API Gateway forwards the whole request as an event and returns Lambda's `{statusCode, headers, body}` verbatim. No mapping templates. |
| **Payload format 2.0** | Simpler event shape (`requestContext.http.method` instead of `httpMethod`). |
| **JWT authorizer** | Validates signature (via Cognito JWKS), `iss`, `aud` and `exp` at the edge and injects verified `claims` into the event. |
| **`identity-source`** | Which header carries the token: `$request.header.Authorization`. |
| **Stage `$default` + auto-deploy** | The URL has *no* stage prefix, and changes deploy automatically. |
| **CORS at the API** | API Gateway answers `OPTIONS` preflight itself — Lambda never sees it. |

## 🔬 Drills

```bash
API=https://4haajttqgh.execute-api.eu-central-1.amazonaws.com

# 1) no token -> 401, Lambda not even invoked
curl -s -o /dev/null -w "%{http_code}\n" $API/expenses

# 2) tampered token -> 401
curl -s -o /dev/null -w "%{http_code}\n" $API/expenses -H "Authorization: not.a.jwt"

# 3) with a good token -> 200
curl -s $API/expenses -H "Authorization: $TOKEN"

# inspect the API definition
aws apigatewayv2 get-routes --api-id 4haajttqgh --query 'Items[].{route:RouteKey,auth:AuthorizationType}'
aws apigatewayv2 get-authorizer --api-id 4haajttqgh --authorizer-id dato8f
aws apigatewayv2 get-stage --api-id 4haajttqgh --stage-name '$default'
```

## 🎯 Interview questions this unlocks

1. HTTP API vs REST API — what do you give up, what do you gain?
2. How does a **JWT authorizer** work, and why is edge validation better than validating inside Lambda?
3. What is a **Lambda proxy** integration vs a custom integration with mapping templates?
4. How do you **rate-limit** or **throttle** an API? *(→ usage plans/throttling; REST API feature; or WAF)*
5. What does **CORS** actually protect, and why is preflight handled by the gateway?
6. How do you expose this on a **custom domain** with TLS? *(→ ACM cert + API Gateway custom domain)*
7. How would you version this API (`/v1`)? *(→ stage or path)*
8. Where would **WAF**, **CloudFront** and **API keys** fit if this went public? *(→ planned for Project C)*

## 💰 Cost

- HTTP API free tier: **1M requests/month** (12-month) then ~$1.00/M.
- No idle cost — pay only per request.

## ⏭️ Next

**Step 5 — the frontend** hosted on S3.
