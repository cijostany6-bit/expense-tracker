#!/usr/bin/env bash
# Deploy the web app + learning site to S3 and refresh the CloudFront cache.
#
# SAFETY: this never uses `--delete`. The bucket hosts two independent trees
# (the app at the root, and the learning site under learn/). A delete-sync of
# one clobbers the other — the reason this script exists.
#
# Usage:  scripts/deploy-web.sh
set -euo pipefail

BUCKET="${WEB_BUCKET:-expense-tracker-web-896618135736}"
DISTRIBUTION_ID="${DISTRIBUTION_ID:-E2CBQ3WW5YO2WF}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

echo "▶ deploying app/ -> s3://$BUCKET/"
aws s3 sync "$ROOT/app/" "s3://$BUCKET/" \
  --exclude "*.DS_Store" --exclude "index.html" --exclude "error.html" \
  --cache-control "public,max-age=300"

# entry points cached briefly so releases are picked up quickly
for f in index.html error.html; do
  aws s3 cp "$ROOT/app/$f" "s3://$BUCKET/$f" --cache-control "public,max-age=60"
done

echo "▶ deploying learn/ -> s3://$BUCKET/learn/"
aws s3 sync "$ROOT/learn/" "s3://$BUCKET/learn/" \
  --exclude "*.DS_Store" \
  --cache-control "public,max-age=300"

echo "▶ deploying docs -> s3://$BUCKET/learn/content/"
for f in "$ROOT"/docs/*.md; do
  aws s3 cp "$f" "s3://$BUCKET/learn/content/$(basename "$f")" \
    --cache-control "public,max-age=300"
done
aws s3 cp "$ROOT/README.md" "s3://$BUCKET/learn/content/readme.md" \
  --cache-control "public,max-age=300"

# README screenshots — the learning site renders README.md at /learn/, so its
# relative image paths (docs/img/…) must exist under /learn/docs/img/.
if [ -d "$ROOT/docs/img" ]; then
  echo "▶ deploying docs/img -> s3://$BUCKET/learn/docs/img/"
  aws s3 sync "$ROOT/docs/img/" "s3://$BUCKET/learn/docs/img/" \
    --exclude "*.DS_Store" --cache-control "public,max-age=86400"
fi

# the generated single-file PDF (built by scripts/build-pdf.sh), if present
PDF="$ROOT/dist/expense-tracker-guide.pdf"
if [ -f "$PDF" ]; then
  echo "▶ deploying guide PDF -> s3://$BUCKET/learn/expense-tracker-guide.pdf"
  aws s3 cp "$PDF" "s3://$BUCKET/learn/expense-tracker-guide.pdf" \
    --content-type "application/pdf" --cache-control "public,max-age=300"
else
  echo "ℹ no PDF found (run scripts/build-pdf.sh to generate dist/expense-tracker-guide.pdf)"
fi

echo "▶ invalidating CloudFront ($DISTRIBUTION_ID)"
aws cloudfront create-invalidation --distribution-id "$DISTRIBUTION_ID" \
  --paths "/*" --query 'Invalidation.Id' --output text

echo "✔ done"
