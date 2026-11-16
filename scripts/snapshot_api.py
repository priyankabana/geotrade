#!/usr/bin/env python3
"""Freeze every API response into static files the CDN can serve.

The deployed front end has no database behind it. A browser on an https:// page
is not allowed to open http://localhost, so the Vercel build could reach the
API on nobody's machine but the viewer's - which meant the published site
showed an empty globe and an "API offline" banner to everyone who opened it.

Rather than run a second, divergent code path in the browser, this walks the
real API over every URL the front end can ask for and writes each response to
disk under the same path. The snapshot is therefore not a re-implementation of
the endpoints: it is their output, produced by the same SQL, and it cannot
disagree with them.

The endpoint surface is finite because every parameter is either absent or a
limit, and the front end calls each one at a fixed limit. That is what makes
this honest rather than lossy - there is no query the live API answers that the
snapshot cannot.

Run it against the published extract, not the working database:

    python3 -I scripts/export_public_db.py
    ATLAS_APP_DSN=postgresql://atlas_app:atlas_app@localhost:5432/atlas_public \\
      python3 -m uvicorn main:app --port 8001      # from apps/api
    python3 -I scripts/snapshot_api.py --api http://localhost:8001
"""
import json, os, pathlib, re, shutil, sys, urllib.error, urllib.request
from datetime import datetime, timezone

API = "http://localhost:8001"
OUT = pathlib.Path("apps/web/public/data")
for i, a in enumerate(sys.argv):
    if a == "--api":
        API = sys.argv[i + 1]
    if a == "--out":
        OUT = pathlib.Path(sys.argv[i + 1])

UNSAFE = re.compile(r"[^A-Za-z0-9._-]")
written: dict[str, str] = {}


def slug(seg: str) -> str:
    """Company uids look like `XASX:CBA` and event keys like `hormuz-2026`.

    A colon survives a URL path but not every static host, and the front end
    percent-encodes it before asking, so both sides agree on this instead."""
    return UNSAFE.sub("-", seg)


def get(path: str):
    with urllib.request.urlopen(API + path, timeout=30) as r:
        return json.loads(r.read())


def save(path: str, body) -> None:
    bare = path.split("?")[0].strip("/")
    parts = bare.split("/")
    name = "/".join(parts[:-1] + [slug(parts[-1])]) + ".json"
    if name in written and written[name] != bare:
        # Two different URLs landing on one file would silently serve one
        # company's evidence on another company's page.
        sys.exit(f"snapshot filename collision: {bare} and {written[name]} -> {name}")
    written[name] = bare
    f = OUT / name
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(body, separators=(",", ":")))


def main():
    try:
        health = get("/v1/health")
    except urllib.error.URLError as e:
        sys.exit(f"no API at {API} ({e}). Start one against atlas_public first.")
    if OUT.exists():
        shutil.rmtree(OUT)

    uids: set[str] = set()

    for p in ("/v1/health", "/v1/metrics"):
        save(p, get(p))

    points = get("/v1/globe/points?limit=30000")
    save("/v1/globe/points", points)
    uids.update(p["uid"] for p in points if p.get("uid"))

    countries = get("/v1/globe/countries")
    save("/v1/globe/countries", countries)

    for ctry in countries:
        iso = ctry["country"]
        sectors = get(f"/v1/countries/{iso}/sectors")
        save(f"/v1/countries/{iso}/sectors", sectors)
        for s in sectors:
            code = s["atlasSector"]
            rows = get(f"/v1/countries/{iso}/sectors/{code}/companies?limit=400")
            save(f"/v1/countries/{iso}/sectors/{code}/companies", rows)
            uids.update(r["companyUid"] for r in rows if r.get("companyUid"))

    # The signals board fetches these two once and filters in the browser, so
    # two files cover every filter combination the interface can produce.
    # The simulator walks this in the browser, so the published build needs it.
    save("/v1/graph", get("/v1/graph"))
    save("/v1/signals", get("/v1/signals?limit=1000"))
    save("/v1/signals/summary", get("/v1/signals/summary"))

    events = get("/v1/events")
    save("/v1/events", events)
    for ev in events:
        key = ev["key"]
        exp = get(f"/v1/events/{key}/exposure?limit=40")
        save(f"/v1/events/{key}/exposure", exp)
        # An exposed company is reachable from the event panel, so its page has
        # to be in the snapshot even if no country/sector list reached it.
        for row in exp.get("exposed", []) or []:
            if row.get("companyUid"):
                uids.add(row["companyUid"])

    for uid in sorted(uids):
        try:
            save(f"/v1/companies/{uid}", get(f"/v1/companies/{uid}"))
        except urllib.error.HTTPError as e:
            if e.code != 404:
                raise

    meta = {
        "builtAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "scope": "public extract - evidence-bearing entities only",
        "entities": health["entities"], "edges": health["edges"],
        "companyPages": len(uids), "files": len(written),
    }
    save("/v1/snapshot", meta)

    size = sum(f.stat().st_size for f in OUT.rglob("*.json"))
    print(f"{len(written)} files, {size/1_048_576:.1f} MB -> {OUT}")
    print(f"  {meta['entities']} entities, {meta['edges']} edges, "
          f"{len(uids)} company pages")


if __name__ == "__main__":
    main()
