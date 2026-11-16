#!/usr/bin/env bash
# Assemble the public site: landing page at /, the globe at /app/, and a frozen
# snapshot of the API's responses at /data/.
#
# The snapshot exists because a deployed HTTPS page may not fetch
# http://localhost, so there is no database the published build can reach. It
# is built from `atlas_public` - the extract of evidence-bearing rows that
# docs/sources.md permits us to publish - and it is produced by calling the
# real API rather than by reimplementing it, so the deployed site cannot
# disagree with the one on your machine.
#
#   scripts/build_site.sh [outdir]
set -euo pipefail
cd "$(dirname "$0")/.."

OUT="${1:-build/site}"
PORT=8001
DSN="postgresql://atlas_app:atlas_app@localhost:5432/${ATLAS_PUBLIC_DB:-atlas_public}"

echo "==> public extract"
python3 -I scripts/export_public_db.py >/dev/null

# A server left over from the last build still holds the port, so the new one
# exits and the snapshot is taken from whatever code the old process loaded.
# That is silent and it is wrong: the published site then lags the repository
# by one or more builds, which is exactly the kind of bug you only find by
# wondering why a fix "didn't work".
echo "==> API on :$PORT against the extract"
pkill -f "uvicorn main:app --port $PORT" 2>/dev/null || true
for _ in $(seq 1 15); do lsof -ti :$PORT >/dev/null 2>&1 || break; sleep 1; done
( cd apps/api && ATLAS_APP_DSN="$DSN" nohup python3 -I -m uvicorn main:app \
    --port $PORT --host 127.0.0.1 >/tmp/atlas_public_api.log 2>&1 </dev/null & ) >/dev/null 2>&1
for _ in $(seq 1 40); do
  curl -s --max-time 2 "localhost:$PORT/v1/health" >/dev/null 2>&1 && break
  sleep 1
done
curl -s --max-time 3 "localhost:$PORT/v1/health" >/dev/null \
  || { echo "API did not start; see /tmp/atlas_public_api.log"; exit 1; }

echo "==> snapshot (api pid $(lsof -ti :$PORT | head -1))"
python3 -I scripts/snapshot_api.py --api "http://localhost:$PORT"

echo "==> frontend"
( cd apps/web && npm run build >/dev/null )

echo "==> assemble $OUT"
rm -rf "$OUT"
mkdir -p "$OUT/app"
# Copy the whole build rather than the parts of it I remembered. Listing
# `assets` and `data` by hand shipped a site with no globe, because the
# textures the globe loads from /textures/ live in public/ and were not on the
# list. The build knows what it contains; this should not have a second opinion.
cp -R apps/web/dist/. "$OUT/"
# The app is the project, so it answers at the root. It used to sit at /app/
# behind a landing page, which meant the first thing a visitor saw was prose
# about the thing rather than the thing.
#
# /app/ keeps working: links to it already exist, and a URL that someone may
# have saved should not break because we rearranged the site.
cp "$OUT/index.html" "$OUT/app/index.html"
cp apps/landing/index.html "$OUT/about.html"
mkdir -p "$OUT/about" && cp apps/landing/index.html "$OUT/about/index.html"

cat > "$OUT/vercel.json" <<'JSON'
{
  "$schema": "https://openapi.vercel.sh/vercel.json",
  "framework": null,
  "installCommand": "echo no install",
  "buildCommand": "echo already built",
  "outputDirectory": ".",
  "cleanUrls": false,
  "headers": [
    {
      "source": "/data/(.*)",
      "headers": [
        { "key": "Content-Type", "value": "application/json; charset=utf-8" },
        { "key": "Cache-Control", "value": "public, max-age=300, s-maxage=86400" }
      ]
    },
    {
      "source": "/assets/(.*)",
      "headers": [
        { "key": "Cache-Control", "value": "public, max-age=31536000, immutable" }
      ]
    }
  ]
}
JSON

# The deploy target runs from $OUT, and the assemble step wipes it, so the
# project link has to be put back or `vercel deploy` would create a new project
# named after the directory instead of updating the existing one.
[ -d apps/web/.vercel ] && cp -R apps/web/.vercel "$OUT/.vercel"

echo
echo "$(find "$OUT" -type f | wc -l | tr -d ' ') files, $(du -sh "$OUT" | cut -f1) in $OUT"
