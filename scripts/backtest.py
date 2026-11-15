#!/usr/bin/env python3
"""Backtest harness over the event benchmark.

What this is: a regression harness. It replays every event in the benchmark
against the graph as it stood on that event's date, records what the walk
found, and fails if the numbers move without someone deciding they should.

What this is not: a validation of whether the companies we surface really were
affected. That needs ground truth - who actually reported an impact the
following quarter - which we do not have and do not pretend to. The metric
below that comes closest is `surprising`, and it measures discovery, not
correctness.

    python3 -I scripts/backtest.py            # report, compare to baseline
    python3 -I scripts/backtest.py --save     # accept current numbers as baseline

Exit status is 1 if any event regressed, so CI can gate on it.
"""
import os, sys, json, datetime
import psycopg

DSN      = os.environ.get("DATABASE_URL", "postgresql://atlas:atlas@localhost:5432/atlas")
BASELINE = "eval/backtest_baseline.json"
TOLERANCE = 0.20       # a fifth of the reach may move before we call it a regression


def measure(cur):
    cur.execute("""
        SELECT e.dedupe_key, e.name, e.became_public_utc,
               count(ep.entity_id)                              AS exposed,
               count(ep.entity_id) FILTER (WHERE ep.is_surprising) AS surprising,
               coalesce(max(ep.hops), 0)                        AS max_hops,
               round(coalesce(avg(ep.score), 0)::numeric, 4)    AS mean_score
        FROM event e
        LEFT JOIN exposure_precompute ep ON ep.event_id = e.id
        GROUP BY e.dedupe_key, e.name, e.became_public_utc
        ORDER BY e.became_public_utc
    """)
    out = {}
    for key, name, public, exposed, surprising, max_hops, mean_score in cur.fetchall():
        out[key] = dict(name=name, date=public.date().isoformat(), exposed=exposed,
                        surprising=surprising, max_hops=max_hops,
                        mean_score=float(mean_score))
    return out


def graph_facts(cur):
    cur.execute("SELECT count(*) FROM dependency_edge")
    edges = cur.fetchone()[0]
    cur.execute("""SELECT count(*) FROM (SELECT DISTINCT from_entity_id, to_entity_id,
                   edge_type FROM dependency_edge) t""")
    rels = cur.fetchone()[0]
    cur.execute("""SELECT count(*) FROM (SELECT DISTINCT from_entity_id, to_entity_id,
                   edge_type FROM dependency_edge
                   WHERE evidence_type = 'named_concentration') t""")
    conc = cur.fetchone()[0]
    cur.execute("SELECT count(*) FROM dependency_edge WHERE chunk_id IS NULL")
    uncited = cur.fetchone()[0]
    return dict(edges=edges, relationships=rels, concentration_backed=conc,
                uncited_edges=uncited)


def main():
    save = "--save" in sys.argv
    with psycopg.connect(DSN) as conn, conn.cursor() as cur:
        now, facts = measure(cur), graph_facts(cur)

    if facts["uncited_edges"]:
        print(f"  FAIL  {facts['uncited_edges']} edges carry no citation")
        sys.exit(1)

    reach   = sum(v["exposed"] for v in now.values())
    surp    = sum(v["surprising"] for v in now.values())
    with_any = sum(1 for v in now.values() if v["exposed"])

    print(f"  {len(now)} events replayed against {facts['edges']} cited edges "
          f"({facts['relationships']} relationships, {facts['concentration_backed']} "
          f"concentration-backed)")
    print(f"  {with_any} events reach at least one company; "
          f"{reach} company-event pairs, {surp} beyond hop 1\n")

    print(f"  {'event':<46}{'date':<12}{'exposed':>8}{'surprising':>12}{'hops':>6}")
    for key, v in sorted(now.items(), key=lambda kv: kv[1]["date"]):
        print(f"  {v['name'][:44]:<46}{v['date']:<12}{v['exposed']:>8}"
              f"{v['surprising']:>12}{v['max_hops']:>6}")

    os.makedirs("eval", exist_ok=True)
    payload = dict(generated=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                   graph=facts, events=now)

    if save or not os.path.exists(BASELINE):
        with open(BASELINE, "w") as fh:
            json.dump(payload, fh, indent=2, sort_keys=True)
        print(f"\n  baseline written to {BASELINE}")
        return

    with open(BASELINE) as fh:
        base = json.load(fh)

    problems = []
    for key, was in base["events"].items():
        is_ = now.get(key)
        if is_ is None:
            problems.append(f"event {key} has disappeared from the benchmark")
            continue
        if was["exposed"] and is_["exposed"] < was["exposed"] * (1 - TOLERANCE):
            problems.append(f"{key}: reach fell {was['exposed']} -> {is_['exposed']}")
        if is_["surprising"] < was["surprising"]:
            problems.append(f"{key}: surprising fell {was['surprising']} -> {is_['surprising']}")
    for key in set(now) - set(base["events"]):
        print(f"  new event in benchmark: {key}")

    print(f"\n  baseline {base['generated'][:10]}: "
          f"{base['graph']['relationships']} relationships, "
          f"{sum(v['exposed'] for v in base['events'].values())} reach")
    if problems:
        print("  REGRESSED:")
        for p in problems:
            print(f"    - {p}")
        sys.exit(1)
    print("  no regression")


if __name__ == "__main__":
    main()
