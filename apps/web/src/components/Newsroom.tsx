/** Every headline the project holds, newest first, across all companies.
 *
 *  The company page answers "what is being said about this firm". A reader
 *  arriving in the morning has a different question - "what happened" - and
 *  answering it by making them open companies one at a time is not an answer.
 *
 *  What is on screen is a headline, a publisher and a link. Never the article
 *  body: that belongs to the outlet, and the click goes to them. It is why
 *  this comes from GDELT's index rather than from scraping the sites whose
 *  terms forbid it.
 */
import { useEffect, useMemo, useState } from 'react'
import * as api from '../client'
import type { FeedItem, Newsroom as Feed } from '../client'

const MARKETS = [
  ['', 'All markets'], ['XNAS', 'Nasdaq'], ['XNYS', 'NYSE'],
  ['XETR', 'Xetra'], ['XFRA', 'Frankfurt'], ['XLON', 'London'],
] as const

/** "4h ago" reads faster than a timestamp when the whole list is recent. */
function ago(iso: string | null): string {
  if (!iso) return ''
  const mins = Math.round((Date.now() - Date.parse(iso)) / 60000)
  if (!Number.isFinite(mins) || mins < 0) return ''
  if (mins < 60) return `${mins}m ago`
  if (mins < 1440) return `${Math.round(mins / 60)}h ago`
  return `${Math.round(mins / 1440)}d ago`
}

/** Two kinds of row share this feed and a reader must be able to tell them
 *  apart: a filing is the company speaking under a legal obligation, a
 *  headline is somebody writing about it. */
const publisher = (d: string | null) =>
  d === 'sec.gov' ? 'SEC filing' : (d || '').replace(/^www\./, '')

export default function Newsroom({ onOpenCompany }: {
  onOpenCompany: (uid: string) => void
}) {
  const [feed, setFeed] = useState<Feed | null>(null)
  const [loaded, setLoaded] = useState(false)
  const [market, setMarket] = useState('')
  const [q, setQ] = useState('')

  useEffect(() => { api.getNewsroom().then(f => { setFeed(f); setLoaded(true) }) }, [])

  // Filtering in the browser, not in the request: the published build reads
  // static files addressed by path and cannot vary on a query string, so one
  // fetch filtered here behaves the same live and offline.
  const rows = useMemo(() => {
    const items = feed?.items ?? []
    const needle = q.trim().toLowerCase()
    return items.filter(i =>
      (!market || i.market === market) &&
      (!needle ||
        i.company.toLowerCase().includes(needle) ||
        (i.ticker || '').toLowerCase().includes(needle) ||
        i.headline.toLowerCase().includes(needle)))
  }, [feed, market, q])

  // Grouped by company, companies ordered by their most recent headline, so
  // the firm something just happened to is at the top.
  const groups = useMemo(() => {
    const by = new Map<string, { item: FeedItem; rows: FeedItem[] }>()
    for (const r of rows) {
      const g = by.get(r.companyUid)
      if (g) g.rows.push(r)
      else by.set(r.companyUid, { item: r, rows: [r] })
    }
    return [...by.values()].sort((a, b) =>
      (b.rows[0].publishedAt || '').localeCompare(a.rows[0].publishedAt || ''))
  }, [rows])

  if (!loaded) return <div className="news-room"><p className="muted">Loading headlines…</p></div>

  const totals = feed?.totals
  return (
    <div className="news-room">
      <div className="news-head">
        <div>
          <h2>Newsroom</h2>
          <p className="muted">
            {totals
              ? `${totals.headlines.toLocaleString()} headlines across `
                + `${totals.companies.toLocaleString()} companies in the graph`
              : 'No headlines stored yet'}
            {feed?.lastCheckedUtc ? ` · last checked ${ago(feed.lastCheckedUtc)}` : ''}
          </p>
        </div>
        <div className="news-filters">
          <input value={q} onChange={e => setQ(e.target.value)}
                 placeholder="Filter by company, ticker or headline" />
          <select value={market} onChange={e => setMarket(e.target.value)}>
            {MARKETS.map(([v, label]) => <option key={v} value={v}>{label}</option>)}
          </select>
        </div>
      </div>

      {groups.length === 0 ? (
        <p className="muted">
          Nothing matches that filter. Headlines are fetched one company at a
          time against GDELT's rate limit, so coverage fills in gradually.
        </p>
      ) : (
        <div className="news-grid">
          {groups.map(g => (
            <section key={g.item.companyUid} className="news-card">
              <header>
                <button className="linkish" onClick={() => onOpenCompany(g.item.companyUid)}>
                  {g.item.company}
                </button>
                <span className="tick num">{g.item.ticker}</span>
                <span className="mkt">{g.item.market}</span>
              </header>
              <ul>
                {g.rows.slice(0, 6).map(r => (
                  <li key={r.url}>
                    <a href={r.url} target="_blank" rel="noopener noreferrer">{r.headline}</a>
                    <span className={r.domain === 'sec.gov' ? 'src filed' : 'src'}>
                      {publisher(r.domain)}{r.publishedAt ? ` · ${ago(r.publishedAt)}` : ''}
                    </span>
                  </li>
                ))}
              </ul>
              {g.rows.length > 6 && (
                <button className="linkish more" onClick={() => onOpenCompany(g.item.companyUid)}>
                  {g.rows.length - 6} more on {g.item.ticker}
                </button>
              )}
            </section>
          ))}
        </div>
      )}
      <p className="news-foot muted">
        Filings come from SEC EDGAR and open the document the company filed.
        Headlines are indexed by GDELT and open the publisher's own page.
      </p>
    </div>
  )
}
