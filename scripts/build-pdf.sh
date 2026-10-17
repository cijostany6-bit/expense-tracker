#!/usr/bin/env bash
# Build one shareable PDF of the whole learning site (the guide docs + the
# interactive course).
#
# Why it's built in parts: a single ~90-page print job is unreliable in headless
# Chrome ("Printing failed"). So we render the guide and each course module as
# separate small jobs and stitch them together losslessly with pypdf
# (scripts/pdf-merge.py). If pypdf is missing we fall back to writing the parts
# side by side rather than to a bloated merge.
#
# The page itself (learn/print.html) reuses the *real* site renderers — marked.js
# for the docs, course.js for the diagrams — so the PDF matches the live site.
#
# Usage:  scripts/build-pdf.sh [output.pdf]
#         (default: dist/expense-tracker-guide.pdf)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="${1:-$ROOT/dist/expense-tracker-guide.pdf}"
PORT="${PDF_PORT:-8791}"

# ── locate Chrome ──
CHROME="${CHROME_BIN:-/Applications/Google Chrome.app/Contents/MacOS/Google Chrome}"
if [ ! -x "$CHROME" ]; then
  CHROME="$(command -v google-chrome || command -v chromium || command -v chromium-browser || true)"
fi
if [ -z "${CHROME:-}" ] || [ ! -x "$CHROME" ]; then
  echo "✖ Google Chrome not found. Install it, or set CHROME_BIN=/path/to/chrome." >&2
  exit 1
fi

mkdir -p "$(dirname "$OUT")"
TMP="$(mktemp -d)"

# ── serve the repo (Chrome needs http:// so the page can fetch the docs) ──
echo "▶ serving $ROOT on http://localhost:$PORT"
python3 -m http.server "$PORT" --directory "$ROOT" >/dev/null 2>&1 &
SRV=$!
cleanup(){ kill "$SRV" 2>/dev/null || true; rm -rf "$TMP"; }
trap cleanup EXIT

BASE="http://localhost:$PORT/learn/print.html"
for _ in $(seq 1 60); do
  curl -sf "$BASE" -o /dev/null && break
  sleep 0.25
done

strip_scripts(){  # $1 in.html  $2 out.html  (remove <script> so nothing re-runs)
  python3 - "$1" "$2" <<'PY'
import re, sys
src, dst = sys.argv[1], sys.argv[2]
h = open(src, encoding="utf-8").read()
h = re.sub(r"<script\b[^>]*>.*?</script>", "", h, flags=re.S | re.I)
open(dst, "w", encoding="utf-8").write(h)
PY
}

render_part(){  # $1 part  $2 out.pdf   → 0 on success
  local part="$1" out="$2"
  local dom="$TMP/dom-$part.html"
  local stat="$TMP/page-$part.html"
  "$CHROME" --headless=new --disable-gpu --no-sandbox --hide-scrollbars \
    --virtual-time-budget=60000 --user-data-dir="$TMP/profile" \
    --dump-dom "$BASE?part=$part" > "$dom" 2>/dev/null
  strip_scripts "$dom" "$stat"
  rm -f "$out"
  "$CHROME" --headless --disable-gpu --no-pdf-header-footer --print-to-pdf="$out" "$stat" >/dev/null 2>&1
  [ -s "$out" ]
}

PARTS=()
echo "▶ part: guide"
if render_part guide "$TMP/p-guide.pdf"; then PARTS+=("$TMP/p-guide.pdf"); else echo "  ⚠ guide failed"; fi

for f in "$ROOT"/learn/course/module-*.html; do
  [ -e "$f" ] || continue
  n="$(basename "$f" | sed -E 's/^module-0*([0-9]+).*$/\1/')"
  echo "▶ part: m$n"
  if render_part "m$n" "$TMP/p-m$n.pdf"; then PARTS+=("$TMP/p-m$n.pdf"); else echo "  ⚠ m$n failed"; fi
done

if [ "${#PARTS[@]}" -eq 0 ]; then echo "✖ nothing rendered" >&2; exit 1; fi

# ── merge losslessly with pypdf (copies streams verbatim; PDFKit would bloat 9×) ──
if ! python3 -c "import pypdf" 2>/dev/null; then
  echo "▶ installing pypdf (user scope) for lossless merging…"
  python3 -m pip install --user --quiet pypdf >/dev/null 2>&1 || true
fi

MERGED=""
if python3 -c "import pypdf" 2>/dev/null; then
  echo "▶ merging ${#PARTS[@]} part(s) with pypdf"
  if python3 "$ROOT/scripts/pdf-merge.py" "$OUT" "${PARTS[@]}"; then MERGED=1; fi
fi

if [ -z "$MERGED" ]; then
  echo "⚠ pypdf unavailable — writing the parts as separate PDFs instead"
  i=1
  for p in "${PARTS[@]}"; do
    cp "$p" "${OUT%.pdf}-part$i.pdf"
    echo "  · ${OUT%.pdf}-part$i.pdf"
    i=$((i + 1))
  done
  printf '✔ wrote %d part(s) next to %s\n' "${#PARTS[@]}" "$OUT"
  exit 0
fi

printf '✔ %s (%s)\n' "${OUT#"$ROOT"/}" "$(du -h "$OUT" | cut -f1)"
