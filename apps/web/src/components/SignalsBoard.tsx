/** The analysis surface: every asset a disruption touches, ranked.
 *
 *  The globe answers "where", this answers "what now". It is deliberately a
 *  different shape - a dense board rather than a map - because ranking forty
 *  assets is a reading task, not a spatial one.
 *
 *  The column that matters most is `basis`. A row is either backed by a
 *  sentence a company filed, or by a rule this project is asserting, and the
 *  board never blurs the two. Filter to `cited` and what remains is only what
 *  somebody put their name to in a regulatory document.
 */
import { useEffect, useMemo, useState } from 'react'
import * as api from '../client'
import type { Signal, SignalSummary } from '../client'

const CLASSES = [
  ['', 'All'], ['commodity', 'Commodities'], ['equity_index', 'Equity Indices'],
  ['fx', 'Forex'], ['crypto', 'Crypto'], ['stock', 'Stocks'],
  ['etf', 'ETFs'], ['bond', 'Bonds'],
] as const

/** Feed ids are how the ingester names its adapters. On screen they should say
 *  where the event came from, in words. */
const FEED_LABEL: Record<string, string> = {
  'gdelt-doc': 'Detected in world news',
  'gdelt-company': 'Detected in company news',
  'usgs-earthquake': 'USGS earthquake feed',
  'nasa-eonet': 'NASA hazard tracker',
  'benchmark': 'Historical benchmark event',
}

const CLASS_LABEL: Record<string, string> = {
  commodity: 'commodity', equity_index: 'index', fx: 'fx',
  crypto: 'crypto', stock: 'stock', etf: 'etf', bond: 'bond',
}

const fmt = (n: number) => (n * 100).toFixed(0)

export default function SignalsBoard() {
  const [all, setAll] = useState<Signal[] | null>(null)
  const [sum, setSum] = useState<SignalSummary | null>(null)
  const [cls, setCls] = useState('')
  const [dir, setDir] = useState('')
  const [basis, setBasis] = useState('')
  const [open, setOpen] = useState<string | null>(null)

  useEffect(() => {
    api.getSignalsSummary().then(setSum)
    api.getSignals().then(setAll)
  }, [])

  // Filtering happens here rather than in a request, because the published
  // build reads static files addressed by path and cannot vary on a query
  // string. One fetch, filtered three ways, behaves identically live.
  const rows = useMemo(() => {
    if (!all) return null
    return all.filter(s =>
      (!cls   || s.assetClass === cls) &&
      (!dir   || s.direction  === dir) &&
      (!basis || s.basis      === basis))
  }, [all, cls, dir, basis])

  // Chart data: one row per asset class, split by direction. Computed from the
  // summary rather than from the filtered rows, so changing a filter does not
  // silently change what the chart is a chart of.
  const chart = useMemo(() => {
    if (!sum) return []
    const by: Record<string, { up: number; down: number }> = {}
    for (const b of sum.buckets) {
      by[b.assetClass] ??= { up: 0, down: 0 }
      if (b.direction === 'up') by[b.assetClass].up += b.count
      if (b.direction === 'down') by[b.assetClass].down += b.count
    }
    const max = Math.max(1, ...Object.values(by).map(v => v.up + v.down))
    return Object.entries(by)
      .map(([k, v]) => ({ k, ...v, total: v.up + v.down, max }))
      .sort((a, b) => b.total - a.total)
  }, [sum])

  const present = useMemo(
    () => new Set((sum?.buckets ?? []).filter(b => b.count > 0).map(b => b.assetClass)),
    [sum])

  const t = sum?.totals

  return (
    <div className="board">
      <div className="board-head">
        <div>
          <h1>What this disruption touches</h1>
          <p className="small">Assets ranked by how hard each event presses on them.</p>
        </div>
        {t && (
          <div className="tiles">
            <div className="tile"><b className="num">{t.cited}</b><span>cited by a filing</span></div>
            <div className="tile"><b className="num">{t.rule}</b><span>asserted by a rule</span></div>
            <div className="tile"><b className="num">{t.assets}</b><span>assets</span></div>
            <div className="tile"><b className="num">{t.events}</b><span>events</span></div>
          </div>
        )}
      </div>

      {chart.length > 0 && (
        <div className="chart">
          <div className="chart-title">Signals by asset class
            <span className="legend"><i className="up" /> pushes up <i className="down" /> pushes down</span>
          </div>
          {chart.map(c => (
            <div className="bar-row" key={c.k}>
              <span className="bar-label">{CLASSES.find(x => x[0] === c.k)?.[1] ?? c.k}</span>
              <span className="bar-track">
                <i className="up"   style={{ width: `${(c.up / c.max) * 100}%` }} />
                <i className="down" style={{ width: `${(c.down / c.max) * 100}%` }} />
              </span>
              <span className="bar-n num">{c.total}</span>
            </div>
          ))}
        </div>
      )}

      <div className="filters">
        <div className="fgroup">
          {/* Only classes that actually have signals. A Crypto tab that always
              returns nothing is a promise the data does not keep. */}
          {CLASSES.filter(([v]) => !v || present.has(v)).map(([v, label]) => (
            <button key={v} aria-selected={cls === v} onClick={() => setCls(v)}>{label}</button>
          ))}
        </div>
        <div className="fgroup">
          {[['', 'Any direction'], ['up', 'Pushes up'], ['down', 'Pushes down']].map(([v, l]) => (
            <button key={v} aria-selected={dir === v} onClick={() => setDir(v)}>{l}</button>
          ))}
        </div>
        <div className="fgroup">
          {[['', 'All evidence'], ['cited_dependency', 'Cited only'], ['rule', 'Rules only']].map(([v, l]) => (
            <button key={v} aria-selected={basis === v} onClick={() => setBasis(v)}>{l}</button>
          ))}
        </div>
      </div>

      {rows === null && <p className="small dim">loading…</p>}
      {rows?.length === 0 && (
        <p className="small dim">
          No signal matches that filter.
        </p>
      )}

      <div className="signals">
        {rows?.map((s, i) => {
          const id = s.signalId
          const isOpen = open === id
          return (
            <div className={`sig ${s.direction}`} key={id}>
              <button className="sig-head" onClick={() => setOpen(isOpen ? null : id)}>
                <span className="rank num">{i + 1}</span>
                <span className="sym">{s.symbol}</span>
                <span className="aname">{s.assetName}</span>
                <span className="cls">{CLASS_LABEL[s.assetClass] ?? s.assetClass}</span>
                <span className={`dir ${s.direction}`}>
                  {s.direction === 'up' ? '▲' : s.direction === 'down' ? '▼' : '—'}
                </span>
                <span className="mag">
                  <i style={{ width: `${Math.min(100, s.magnitude * 100)}%` }} />
                  <b className="num">{fmt(s.magnitude)}</b>
                </span>
                <span className={`badge ${s.basis === 'cited_dependency' ? 'cited' : 'rule'}`}>
                  {s.basis === 'cited_dependency' ? 'FILED' : 'RULE'}
                </span>
                <span className="ev">{s.event.name}</span>
              </button>
              {isOpen && (
                <div className="sig-body">
                  <p className="why">{s.rationale}</p>
                  {s.citation ? (
                    <blockquote>
                      “{s.citation.quote}”
                      <cite>
                        {s.citation.filerName} · {s.citation.docType}
                        {s.citation.filedAt ? ` · filed ${s.citation.filedAt.slice(0, 10)}` : ''}
                        {s.citation.url && <> · <a href={s.citation.url} target="_blank" rel="noreferrer">source ↗</a></>}
                      </cite>
                    </blockquote>
                  ) : (
                    /* `semi-supply-shock` is this repository's name for a rule,
                       not something a reader can be expected to decode. The
                       sentence above already says what the rule claims; the
                       slug stays in the API for anyone auditing it. */
                    <p className="small dim">Our own rule — no company filed this.</p>
                  )}
                  <p className="small dim">
                    {FEED_LABEL[s.event.feed] ?? s.event.feed} · {s.asOf.slice(0, 10)}
                  </p>
                </div>
              )}
            </div>
          )
        })}
      </div>

      <p className="disclaimer">Not investment advice.</p>
    </div>
  )
}
