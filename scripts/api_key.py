#!/usr/bin/env python3
"""Mint, list and revoke API keys.

The key is shown once, at creation, and never stored. What we keep is its
SHA-256, so the table is useless to anyone who reads it - including us.

    python3 -I scripts/api_key.py new "Anushka laptop"
    python3 -I scripts/api_key.py list
    python3 -I scripts/api_key.py revoke <id>
"""
import os, sys, secrets, hashlib
import psycopg

DSN = os.environ.get("DATABASE_URL", "postgresql://atlas:atlas@localhost:5432/atlas")


def main():
    args = sys.argv[1:]
    cmd = args[0] if args else "list"
    with psycopg.connect(DSN) as conn, conn.cursor() as cur:
        if cmd == "new":
            name = args[1] if len(args) > 1 else "unnamed"
            tenant = args[2] if len(args) > 2 else None
            if tenant is None:
                cur.execute("SELECT id FROM tenant ORDER BY created_at LIMIT 1")
                row = cur.fetchone()
                if not row:
                    sys.exit("no tenant exists; create one first")
                tenant = row[0]
            key = "atlas_" + secrets.token_urlsafe(32)
            cur.execute("""INSERT INTO api_key (tenant_id, name, key_sha256)
                           VALUES (%s,%s,%s) RETURNING id""",
                        (tenant, name, hashlib.sha256(key.encode()).hexdigest()))
            kid = cur.fetchone()[0]
            conn.commit()
            print(f"  id      {kid}")
            print(f"  tenant  {tenant}")
            print(f"  key     {key}")
            print("\n  This is the only time the key is shown. We store only its hash.")
            print(f"\n  curl -H 'X-API-Key: {key}' localhost:8000/v1/health")

        elif cmd == "revoke":
            if len(args) < 2:
                sys.exit("usage: api_key.py revoke <id>")
            cur.execute("UPDATE api_key SET revoked_at = now() WHERE id = %s", (args[1],))
            conn.commit()
            print(f"  revoked {args[1]} ({cur.rowcount} row)")

        else:
            cur.execute("""SELECT k.id, k.name, t.name, k.created_at, k.last_used_at,
                                  k.revoked_at
                           FROM api_key k JOIN tenant t ON t.id = k.tenant_id
                           ORDER BY k.created_at""")
            rows = cur.fetchall()
            if not rows:
                print("  no keys yet - make one with: make key NAME='my laptop'")
            for kid, name, tname, made, used, revoked in rows:
                state = "REVOKED" if revoked else "active"
                print(f"  {str(kid)[:8]}  {state:8}  {name[:24]:26} tenant={tname:10} "
                      f"used={used.date() if used else 'never'}")


if __name__ == "__main__":
    main()
