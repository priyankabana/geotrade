/** Break a company on purpose and see who it reaches.
 *
 *  Replay shows what a real event did. This asks a question nobody has asked
 *  yet: if this company stopped delivering tomorrow, who has already written
 *  down that it would hurt them?
 *
 *  The walk runs in the browser, over the same edges and with the constants the
 *  server sends with them, because the published build has no database behind
 *  it and a simulator that only worked on a laptop would not be a feature. The
 *  constants travel with the data for exactly one reason: so this cannot
 *  quietly drift to a different decay than scripts/propagate.py and produce
 *  numbers that look like Atlas's without being Atlas's.
 */
import { useEffect, useMemo, useState } from 'react'
import * as api from '../client'
import type { Graph, GraphEdge } from '../client'

type Hit = {
  uid: string; name: string; score: number; hops: number
  via: string | null; edge: GraphEdge | null
}

/** Port of walk() in scripts/propagate.py. Same order, same comparisons. */
function walk(g: Graph, seed: string, severity: number): Hit[] {
  const { maxHops, decay, floor } = g.walk

  // out[b] = everyone who disclosed depending on b, so a hit on b reaches them.
  const out = new Map<string, GraphEdge[]>()
  for (const e of g.edges) {
    const arr = out.get(e.to)
    if (arr) arr.push(e); else out.set(e.to, [e])
  }

  const best = new Map<string, Hit>()
  const seedName = g.edges.find(e => e.to === seed)?.toName
    ?? g.edges.find(e => e.from === seed)?.fromName ?? seed
  best.set(seed, { uid: seed, name: seedName, score: severity, hops: 1, via: null, edge: null })

  for (let hop = 2; hop <= maxHops; hop++) {
    const next: Hit[] = []
    for (const cur of [...best.values()]) {
      if (cur.hops !== hop - 1) continue
      for (const e of out.get(cur.uid) ?? []) {
        const score = cur.score * e.weight * e.confidence * decay
        if (score < floor) continue
        const held = best.get(e.from)
        if (!held || score > held.score) {
          next.push({ uid: e.from, name: e.fromName, score, hops: hop, via: cur.name, edge: e })
        }
      }
    }
    for (const n of next) {
      const held = best.get(n.uid)
      if (!held || n.score > held.score) best.set(n.uid, n)
    }
  }

  return [...best.values()].filter(h => h.uid !== seed).sort((a, b) => b.score - a.score)
}

export default function Simulator({ onOpenCompany, seedUid }: {
  onOpenCompany: (uid: string) => void
  /** Break the company you arrived with, rather than making the reader find
   *  it again in a list of several hundred. */
  seedUid?: string | null
}) {
  const [g, setG] = useState<Graph | null>(null)
  const [seed, setSeed] = useState<string>(seedUid ?? '')
  const [severity, setSeverity] = useState(0.8)
  const [q, setQ] = useState('')

  useEffect(() => { if (seedUid) setSeed(seedUid) }, [seedUid])
  useEffect(() => { api.getGraph().then(g => {
    setG(g)
    // Exposed so the parity check in tests/test_simulator.py can run the
    // same walk against the same bytes the page is using.
    ;(window as unknown as { __atlasGraph?: unknown }).__atlasGraph = g
  }) }, [])

  /** Only companies somebody has actually named are worth breaking: a company
   *  with nothing pointing at it reaches nobody, and offering it as a choice
   *  would promise a result that is always empty. */
  const targets = useMemo(() => {
    if (!g) return []
    const m = new Map<string, { uid: string; name: string; n: number }>()
    for (const e of g.edges) {
      const got = m.get(e.to)
      if (got) got.n++
      else m.set(e.to, { uid: e.to, name: e.toName, n: 1 })
    }
    return [...m.values()].sort((a, b) => b.n - a.n || a.name.localeCompare(b.name))
  }, [g])

  useEffect(() => { if (!seed && targets.length) setSeed(targets[0].uid) }, [targets, seed])

  const shown = useMemo(() => {
    const t = q.trim().toLowerCase()
    return t ? targets.filter(x => x.name.toLowerCase().includes(t)
                               || x.uid.toLowerCase().includes(t)).slice(0, 40)
             : targets.slice(0, 40)
  }, [targets, q])

  const hits = useMemo(() => (g && seed) ? walk(g, seed, severity) : [], [g, seed, severity])
  const chosen = targets.find(t => t.uid === seed)

  if (!g) return <div className="board"><p className="small dim">loading the graph…</p></div>

  return (
    <div className="board sim">
      <div className="board-head">
        <div>
          <h1>If this company stopped delivering</h1>
          <p className="small">
            Pick a company and set how hard it is hit. Everyone below is reached
            through a sentence another company filed.
          </p>
        </div>
        <div className="tiles">
          {/* "beyond the first hop" counted every hit, because the seed is
              the only thing at hop 1 and it is excluded. A tile that always
              equals the one beside it is not telling anyone anything. */}
          <div className="tile"><b className="num">{hits.length}</b><span>companies reached</span></div>
          <div className="tile"><b className="num">{hits.filter(h => h.hops >= 3).length}</b><span>only via another company</span></div>
          <div className="tile"><b className="num">{g.edges.length}</b><span>edges walked</span></div>
        </div>
      </div>

      <div className="sim-controls">
        <div className="sim-pick">
          <label>Company</label>
          <input value={q} placeholder={chosen?.name ?? 'Filter…'}
                 onChange={e => setQ(e.target.value)} />
          <div className="sim-list">
            {shown.map(t => (
              <button key={t.uid} aria-selected={t.uid === seed}
                      onClick={() => { setSeed(t.uid); setQ('') }}>
                <span>{t.name}</span>
                <span className="num dim">{t.n} named it</span>
              </button>
            ))}
          </div>
        </div>

        <div className="sim-sev">
          <label>Severity <b className="num">{(severity * 100).toFixed(0)}</b></label>
          <input type="range" min={0.1} max={1} step={0.05} value={severity}
                 onChange={e => setSeverity(Number(e.target.value))} />
          <p className="small dim">
            How hard the shock lands. It scales every number below and nothing else.
          </p>
        </div>
      </div>

      {hits.length === 0 ? (
        <p className="small dim">
          Nobody we hold a filing for has disclosed depending on {chosen?.name ?? 'this company'}.
        </p>
      ) : (
        <div className="signals">
          {hits.map((h, i) => (
            <div className={`sig down`} key={h.uid}>
              <button className="sig-head sim-row" onClick={() => onOpenCompany(h.uid)}>
                <span className="rank num">{i + 1}</span>
                <span className="sym">{h.uid.split(':')[1]}</span>
                <span className="aname">{h.name}</span>
                <span className="cls">{h.hops} hop{h.hops === 1 ? '' : 's'}</span>
                <span className="mag">
                  <i style={{ width: `${Math.min(100, h.score * 100)}%` }} />
                  <b className="num">{(h.score * 100).toFixed(0)}</b>
                </span>
                <span className="ev">{h.via ? `via ${h.via}` : ''}</span>
              </button>
              {h.edge && (
                <div className="sig-body">
                  <blockquote>
                    “{h.edge.citation.quote}”
                    <cite>
                      {h.edge.fromName}
                      {h.edge.citation.docType ? ` · ${h.edge.citation.docType}` : ''}
                      {h.edge.citation.filedAt ? ` · filed ${h.edge.citation.filedAt.slice(0, 10)}` : ''}
                      {h.edge.citation.url && <> · <a href={h.edge.citation.url} target="_blank" rel="noreferrer">source ↗</a></>}
                    </cite>
                  </blockquote>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
      <p className="disclaimer">
        Hypothetical. Nothing here has happened - it is what the filings say would be felt if it did.
      </p>
    </div>
  )
}
