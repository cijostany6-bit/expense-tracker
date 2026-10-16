#!/usr/bin/env python3
"""
Real-world load test for the Expense Tracker API.  (stdlib only — no pip installs)

It signs in as the demo user, then fires many concurrent HTTP requests at the
live API and reports throughput, latency percentiles (p50 / p90 / p99) and the
error rate — the same numbers you'd put in a performance section of a report.

This is READ-ONLY by default (GET /expenses + GET /summary), so it is safe to run
against the live stack and costs ~nothing.

Usage
-----
    python3 scripts/loadtest.py --requests 400 --concurrency 40
    python3 scripts/loadtest.py --requests 200 --concurrency 20 --mix write
"""

import argparse
import json
import statistics
import time
import urllib.error
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor

REGION    = "eu-central-1"
CLIENT_ID = "4grucsnelng73rhl3c1kbasi7j"
API       = "https://4haajttqgh.execute-api.eu-central-1.amazonaws.com"
USERNAME  = "demo.cijo@example.com"
PASSWORD  = "Testpass1"


# ── tiny HTTP helpers (urllib keeps this dependency-free) ───────────────────

def _req(method, url, body=None, headers=None, timeout=30):
    data = json.dumps(body).encode() if body is not None else None
    hdrs = {"Content-Type": "application/json"}
    if headers:
        hdrs.update(headers)
    req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as res:
        return res.status, json.loads(res.read() or b"{}")


def get_token():
    url = f"https://cognito-idp.{REGION}.amazonaws.com/"
    _, out = _req(
        "POST", url,
        {"AuthFlow": "USER_PASSWORD_AUTH", "ClientId": CLIENT_ID,
         "AuthParameters": {"USERNAME": USERNAME, "PASSWORD": PASSWORD}},
        {"X-Amz-Target": "AWSCognitoIdentityProviderService.InitiateAuth",
         "Content-Type": "application/x-amz-json-1.1"},
    )
    return out["AuthenticationResult"]["IdToken"]


# ── the work each virtual user does ─────────────────────────────────────────

def timed(fn):
    t0 = time.perf_counter()
    try:
        status = fn()
    except urllib.error.HTTPError as e:
        status = e.code
    except Exception:
        status = 0                      # connection error / timeout
    return status, (time.perf_counter() - t0) * 1000.0     # ms


def read_call(token):
    def go():
        _, _ = _req("GET", API + "/expenses", headers={"Authorization": token})
        return 200
    return go


def summary_call(token):
    def go():
        _, _ = _req("GET", API + "/summary", headers={"Authorization": token})
        return 200
    return go


def write_call(token):
    eid = str(uuid.uuid4())
    def go():
        _, _ = _req("POST", API + "/expenses",
                    {"amount": 3.5, "currency": "EUR", "category": "other",
                     "note": f"loadtest {eid[:8]}"},
                    {"Authorization": token})
        # clean up immediately so the table doesn't grow
        _req("DELETE", f"{API}/expenses/{eid}", headers={"Authorization": token})
        return 201
    return go


def percentile(values, pct):
    if not values:
        return 0.0
    s = sorted(values)
    k = int(round((pct / 100.0) * (len(s) - 1)))
    return s[max(0, min(len(s) - 1, k))]


# ── main ────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--requests", type=int, default=400)
    ap.add_argument("--concurrency", type=int, default=40)
    ap.add_argument("--mix", choices=["read", "write", "mixed"], default="read")
    args = ap.parse_args()

    print(f"→ signing in as {USERNAME} …")
    token = get_token()
    print("  got IdToken ✓")

    # warm-up: absorb the Lambda cold start before measuring
    print("→ warm-up call …")
    timed(read_call(token))

    jobs = []
    for i in range(args.requests):
        if args.mix == "read":
            jobs.append(read_call(token) if i % 4 else summary_call(token))
        elif args.mix == "write":
            jobs.append(write_call(token))
        else:
            jobs.append(write_call(token) if i % 5 == 0 else read_call(token))

    print(f"→ firing {args.requests} requests at concurrency {args.concurrency} (mix={args.mix}) …")
    wall_start = time.perf_counter()
    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        results = list(pool.map(lambda f: timed(f), jobs))
    wall = time.perf_counter() - wall_start

    latencies = [ms for status, ms in results if status in (200, 201)]
    errors = [(status, ms) for status, ms in results if status not in (200, 201)]
    n = len(results)

    print("\n────────────── RESULTS ──────────────")
    print(f"  requests      : {n}")
    print(f"  concurrency   : {args.concurrency}")
    print(f"  wall time     : {wall:.2f} s")
    print(f"  throughput    : {n / wall:,.1f} req/s")
    print(f"  succeeded     : {len(latencies)}  ({100 * len(latencies) / n:.1f}%)")
    print(f"  errors        : {len(errors)}  ({100 * len(errors) / n:.1f}%)")
    if latencies:
        print(f"  latency mean  : {statistics.mean(latencies):.0f} ms")
        print(f"  latency p50   : {percentile(latencies, 50):.0f} ms")
        print(f"  latency p90   : {percentile(latencies, 90):.0f} ms")
        print(f"  latency p99   : {percentile(latencies, 99):.0f} ms")
        print(f"  latency max   : {max(latencies):.0f} ms")
    if errors:
        from collections import Counter
        print(f"  error codes   : {dict(Counter(s for s, _ in errors))}")
    print("─────────────────────────────────────")
    print("\nTip: compare p99 to p50 — a big gap means some requests hit a cold")
    print("start or a throttled service. That's the number to talk about.")


if __name__ == "__main__":
    main()
