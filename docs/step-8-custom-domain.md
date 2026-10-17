# Step 8 — A real domain on HTTPS: GoDaddy → Route 53 → ACM → CloudFront

Step 7 gave the app HTTPS on a `*.cloudfront.net` address. Step 8 makes it look
like a product: **`https://worldofvpc.online`**, with a padlock and no domain in
the URL that screams "demo".

The whole thing is one idea — *three different layers that beginners conflate* —
plus a couple of AWS-specific rules that trip everyone up once.

---

## 8.1 — Three layers, three services

People say "my domain" and mean three unrelated things. Keep them separate and
this step is easy:

| Layer | Question it answers | Who owns it here |
|---|---|---|
| **Registration** | Who *rents* the name? | **GoDaddy** (we bought it there) |
| **DNS** | Which server answers lookups? | **Route 53** (a hosted zone) |
| **Certificate** | Who vouches it's really us over TLS? | **ACM** |

You can register at GoDaddy and still host DNS at AWS — that's exactly what we
do. The domain never has to move; only the **nameservers** (NS) do.

```
   GoDaddy (registrar)                 AWS account
   ┌───────────────────┐   NS records  ┌─────────────────────────────┐
   │ worldofvpc.online │ ────────────▶ │ Route 53 hosted zone        │
   └───────────────────┘   delegate    │  • ACM validation CNAMEs    │
                                       │  • apex + www alias → CF    │
                                       └──────────────┬──────────────┘
                                                      │
                          ACM cert (us-east-1) ───────┤
                                                      ▼
                                              CloudFront (HTTPS)
```

---

## 8.2 — The gotcha we actually hit

Before creating anything, we looked at the domain and found it already pointing
at **Route 53 nameservers**:

```
ns-991.awsdns-59.net, ns-1819.awsdns-35.co.uk, …
```

…but there was **no hosted zone** for it. Result: the TLD delegated to Route 53,
Route 53 had no zone to answer for, and the whole domain returned **`SERVFAIL`** —
it resolved to *nothing*.

> **Lesson:** a nameserver delegation with no matching zone is worse than no
> delegation. Always confirm the zone exists in *the account you have access to*.

The fix was to create a fresh hosted zone and repoint GoDaddy at its NS values.

---

## 8.3 — The build, in order

**1. Create the hosted zone** (this is the authority for the domain):

```bash
aws route53 create-hosted-zone --name worldofvpc.online \
  --caller-reference "worldofvpc-$(date +%s)"
```

Route 53 answers with four NS values. **At GoDaddy**, set those as the custom
nameservers (DNS → Nameservers → *I'll use my own*). Propagation is minutes to a
few hours.

**2. Get a certificate** — in **`us-east-1`**, and only there:

```bash
aws acm request-certificate --region us-east-1 \
  --domain-name worldofvpc.online \
  --subject-alternative-names www.worldofvpc.online \
  --validation-method DNS
```

> **Why `us-east-1`?** CloudFront is a *global* service, but it only accepts
> certificates issued in **us-east-1** (N. Virginia). An `eu-central-1`
> certificate will simply not appear in the dropdown. This is the single most
> common CloudFront-certificate mistake.

**3. Add the validation CNAMEs** to the hosted zone. ACM gives you one CNAME per
name; because the zone is in the same account, we could write them directly:

```bash
aws route53 change-resource-record-sets --hosted-zone-id <zone> \
  --change-batch file://acm-validation.json
```

The cert flips to `ISSUED` on its own once DNS sees the records.

**4. Attach the domain to CloudFront** — add the alternate domain names (CNAMEs)
and swap the viewer certificate:

```
Aliases:            worldofvpc.online, www.worldofvpc.online
ViewerCertificate:  ACM certificate  (sni-only, TLSv1.2_2021)
```

**5. Point DNS at CloudFront** — an **alias** record, apex *and* `www`:

```bash
# Type A (and AAAA), AliasTarget -> the CloudFront distribution
```

> **Why an alias and not a CNAME?** DNS forbids a CNAME at the **zone apex**
> (`worldofvpc.online` itself). An alias record is AWS-specific sugar that *can*
> sit at the apex and points straight at CloudFront — no cost, and it follows the
> distribution's IPs automatically.

---

## 8.4 — Why not just keep the `*.cloudfront.net` cert?

Because a résumé says "I shipped a product", and a product has a name. But note
what stayed the same: the **origin is still the S3 website**, the app code didn't
change, and CORS already allowed `*`. Swapping the front door from
`d3ssxu6u8n5flg.cloudfront.net` to `worldofvpc.online` was **pure
configuration**.

---

## 💰 Cost

| Item | Cost |
|---|---|
| Route 53 hosted zone | **$0.50 / month** (the first real cost in this project) |
| Alias records → CloudFront | free |
| ACM certificate | free |
| DNS queries | first 1B/month free |

The hosted zone is the only unavoidable charge — and it's the price of owning a
name with proper DNS.

---

## 💬 Interview questions this step unlocks

- **"What's the difference between a registrar and a DNS host?"** — the registrar
  rents the name; the DNS host answers lookups. You delegate between them with NS
  records. Ours are split (GoDaddy + Route 53).
- **"Why must an ACM cert for CloudFront live in `us-east-1`?"** — CloudFront is
  global and only reads certificates from that region.
- **"Can you CNAME the apex of a zone?"** — no; use a Route 53 **alias** record.
- **"How does ACM prove you own the domain?"** — DNS validation: it asks you to
  publish a specific CNAME, then queries for it.
- **"The domain resolved to nothing. Where do you look?"** — check the *delegation*
  (registrar NS) against the *zone* (does it exist, in this account?). Ours was
  delegated with no zone → `SERVFAIL`.
