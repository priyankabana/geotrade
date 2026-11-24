/** Live news, clustered into stories, with the calls that came out of them.
 *
 *  This surface is the second pipeline's front end. The globe answers who
 *  depends on whom from filings that are months old; this answers what
 *  happened this week and who it reaches, and the two meet in the third
 *  block: a company whose own week was quiet but whose supplier's was not.
 *
 *  Everything here is read from one static file written by the pipeline's own
 *  exporter, so the page costs one request and works with no database behind
 *  it, the same way the rest of the published build does.
 */
import { useEffect, useMemo, useState } from 'react'

type Headline = { title: string; url: string; domain: string; published_at: string | null }
type Company = { uid: string; ticker: string; name: string; country: string }
type Story = {
  id: number; label: string; article_count: number; last_seen: string
  headlines: Headline[] | null; companies: Company[] | null
}
type Call = {
  uid: string; ticker: string; name: string; country: string
  direction: 'up' | 'down'; strength: number
  article_count: number; filing_count: number; transcript_count: number
  graph_origins: number
  rationale: string; as_of: string
}
type Reached = {
  ticker: string; company: string; origin_ticker: string; origin: string
  hops: number; decayed_score: number; path: string; relation: string; evidence: string
}
type Transcript = {
  uid: string; ticker: string; name: string; country: string
  headline: string; call_date: string | null; fiscal_label: string
  speakers: number; char_count: number
  label: 'positive' | 'negative' | 'neutral' | null; score: number | null
  excerpt: string | null
}
type CalEvent = {
  uid: string; ticker: string; name: string; country: string
  event_date: string; period_label: string | null; status: string | null
}
type Payload = {
  builtAt: string
  summary: Record<string, number>
  stories: Story[]; decisions: Call[]; reached: Reached[]
  transcripts: Transcript[]; calendar: CalEvent[]
  disclaimer: string
}

const dayLabel = (iso: string) => {
  const d = new Date(iso + 'T00:00:00')
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}
const daysAway = (iso: string) => {
  const d = Math.round((new Date(iso + 'T00:00:00').getTime() - Date.now()) / 864e5)
  return d <= 0 ? 'today' : d === 1 ? 'tomorrow' : `in ${d} days`
}

const ago = (iso: string | null) => {
  if (!iso) return ''
  const h = (Date.now() - new Date(iso).getTime()) / 36e5
  if (h < 1) return 'just now'
  if (h < 24) return `${Math.round(h)}h ago`
  return `${Math.round(h / 24)}d ago`
}

export default function Stories({ onOpenCompany }: {
  onOpenCompany: (uid: string) => void
}) {
  const [data, setData] = useState<Payload | null>(null)
  const [failed, setFailed] = useState(false)
  const [tab, setTab] = useState<
    'stories' | 'calls' | 'earnings' | 'calendar' | 'reached'>('stories')

  useEffect(() => {
    fetch('data/v1/stories.json')
      .then(r => (r.ok ? r.json() : Promise.reject(r.status)))
      .then(setData)
      .catch(() => setFailed(true))
  }, [])

  const s = data?.summary
  const counts = useMemo(() => ([
    { k: 'companies tracked', v: s?.companies },
    { k: 'countries', v: s?.countries },
    { k: 'name variants matched', v: s?.aliases },
    { k: 'articles read', v: s?.articles },
    { k: 'passages scored', v: s?.scored },
    { k: 'earnings releases', v: s?.earnings_releases },
    { k: 'earnings calls', v: s?.transcripts },
  ]), [s])

  if (failed) {
    return <div className="board"><p className="small dim">
      The story file has not been published yet. Run
      {' '}<code>python3 export_for_site.py</code> in newsflow, then rebuild.
    </p></div>
  }
  if (!data) return <div className="board"><p className="small dim">loading…</p></div>

  return (
    <div className="board stories">
      <h1 className="board-h">What the market is talking about</h1>
      <p className="board-sub">
        Headlines are grouped so one event covered by forty outlets counts once,
        scored against a finance word list, and read together with the company's
        own filings. {data.disclaimer}
      </p>

      <dl className="figures sm">
        {counts.map(c => (
          <div key={c.k}><dt>{c.k}</dt>
            <dd className="num">{c.v?.toLocaleString() ?? '-'}</dd></div>
        ))}
      </dl>

      <nav className="ctabs">
        <button aria-selected={tab === 'stories'} onClick={() => setTab('stories')}>
          <span className="tn num">01</span> Stories <span className="n num">{data.stories.length}</span>
        </button>
        <button aria-selected={tab === 'calls'} onClick={() => setTab('calls')}>
          <span className="tn num">02</span> Direction called <span className="n num">{data.decisions.length}</span>
        </button>
        <button aria-selected={tab === 'earnings'} onClick={() => setTab('earnings')}>
          <span className="tn num">03</span> Earnings calls <span className="n num">{(data.transcripts ?? []).length}</span>
        </button>
        <button aria-selected={tab === 'calendar'} onClick={() => setTab('calendar')}>
          <span className="tn num">04</span> Coming up <span className="n num">{(data.calendar ?? []).length}</span>
        </button>
        <button aria-selected={tab === 'reached'} onClick={() => setTab('reached')}>
          <span className="tn num">05</span> Reached through the graph <span className="n num">{data.reached.length}</span>
        </button>
      </nav>

      {tab === 'stories' && (
        <div className="story-grid">
          {data.stories.map(st => (
            <article key={st.id} className="story-card">
              <header>
                <span className="num st-n">{st.article_count} outlet{st.article_count === 1 ? '' : 's'}</span>
                <span className="num st-when">{ago(st.last_seen)}</span>
              </header>
              <h3>{(st.headlines?.[0]?.title ?? st.label) || 'Untitled story'}</h3>
              {/* Syndicated copy carries the same headline from outlet to
                  outlet, so repeating it three times fills the card and tells
                  the reader nothing. Where the wording differs it is worth
                  showing; where it does not, the outlets are the information. */}
              {(() => {
                const all = st.headlines ?? []
                const lead = (all[0]?.title ?? '').toLowerCase()
                const different = all.slice(1).filter(h =>
                  h.title.toLowerCase() !== lead)
                if (different.length) {
                  return (
                    <ul className="st-more">
                      {different.slice(0, 2).map(h => (
                        <li key={h.url}>
                          <a href={h.url} target="_blank" rel="noreferrer">{h.title}</a>
                          <span className="dim"> {h.domain}</span>
                        </li>
                      ))}
                    </ul>
                  )
                }
                const outlets = [...new Set(all.map(h => h.domain).filter(Boolean))]
                return outlets.length ? (
                  <p className="st-outlets">
                    {all[0]?.url && (
                      <a href={all[0].url} target="_blank" rel="noreferrer">read it</a>
                    )}
                    <span className="dim"> {outlets.slice(0, 3).join(', ')}
                      {st.article_count > outlets.length
                        ? ` and ${st.article_count - outlets.length} more`
                        : ''}</span>
                  </p>
                ) : null
              })()}
              {!!(st.companies ?? []).length && (
                <footer>
                  {(st.companies ?? []).map(c => (
                    <button key={c.uid} className="chip"
                            onClick={() => onOpenCompany(c.uid)}>
                      {c.name} <span className="num">{c.ticker}</span>
                    </button>
                  ))}
                </footer>
              )}
            </article>
          ))}
        </div>
      )}

      {tab === 'calls' && (
        <div className="calls">
          {data.decisions.map(c => (
            <article key={c.uid + c.as_of} className="call">
              <div className="call-head">
                <span className={`dir ${c.direction}`}>{c.direction}</span>
                <button className="inline-link" onClick={() => onOpenCompany(c.uid)}>
                  {c.name}
                </button>
                <span className="num dim">{c.ticker} · {c.country}</span>
                <span className="num strength">{c.strength.toFixed(3)}</span>
              </div>
              <p className="call-why">{c.rationale}</p>
              <div className="call-basis num">
                {c.article_count} news · {c.filing_count} filing section
                {c.filing_count === 1 ? '' : 's'}
                {c.transcript_count > 0 && ` · ${c.transcript_count} earnings call${c.transcript_count === 1 ? '' : 's'}`}
                {c.graph_origins > 0 && ` · ${c.graph_origins} through the graph`}
              </div>
            </article>
          ))}
        </div>
      )}

      {tab === 'earnings' && (
        <>
          <p className="lede">
            Earnings calls we have read in full. Each line is one call, the way
            it scored against the finance word list, and the single sentence
            that most earned that score. Click a company to open it on the globe.
          </p>
          <div className="calls">
            {(data.transcripts ?? []).map((t, i) => (
              <article key={t.uid + i} className="call">
                <div className="call-head">
                  {t.label && t.label !== 'neutral' && (
                    <span className={`dir ${t.label === 'positive' ? 'up' : 'down'}`}>
                      {t.label === 'positive' ? 'up' : 'down'}
                    </span>
                  )}
                  <button className="inline-link" onClick={() => onOpenCompany(t.uid)}>
                    {t.name}
                  </button>
                  <span className="num dim">{t.ticker} · {t.country}</span>
                  {t.fiscal_label && <span className="num tag">{t.fiscal_label}</span>}
                  <span className="num strength">
                    {t.call_date ? ago(t.call_date + 'T00:00:00') : ''}
                  </span>
                </div>
                {t.excerpt && <p className="call-why">“{t.excerpt}”</p>}
                <div className="call-basis num">
                  {t.speakers} speaker{t.speakers === 1 ? '' : 's'} ·{' '}
                  {t.char_count.toLocaleString()} characters read
                  {t.score != null && ` · scored ${t.score >= 0 ? '+' : ''}${t.score.toFixed(3)}`}
                </div>
              </article>
            ))}
          </div>
        </>
      )}

      {tab === 'calendar' && (
        <>
          <p className="lede">
            What is coming up: the next earnings dates on the calendar, soonest
            first. Everything else on this page reads text that already exists;
            this is the one line that points forward.
          </p>
          <div className="cal">
            {(data.calendar ?? []).map((e, i) => (
              <button key={e.uid + i} className="cal-row"
                      onClick={() => onOpenCompany(e.uid)}>
                <span className="cal-date">
                  <b>{dayLabel(e.event_date)}</b>
                  <i className="num dim">{daysAway(e.event_date)}</i>
                </span>
                <span className="cal-co">
                  {e.name} <span className="num dim">{e.ticker} · {e.country}</span>
                </span>
                {e.period_label && <span className="num tag">{e.period_label}</span>}
              </button>
            ))}
            {!(data.calendar ?? []).length && (
              <p className="small dim">No earnings dates ahead of today on file.</p>
            )}
          </div>
        </>
      )}

      {tab === 'reached' && (
        <>
          <p className="lede">
            These companies had little or no news of their own. What moved them
            arrived along a dependency one of them disclosed in a filing, and the
            sentence that proves the link is printed with each one.
          </p>
          <div className="calls">
            {data.reached.map((r, i) => (
              <article key={i} className="call">
                <div className="call-head">
                  <span className={`dir ${r.decayed_score < 0 ? 'down' : 'up'}`}>
                    {r.decayed_score < 0 ? 'down' : 'up'}
                  </span>
                  <strong>{r.company}</strong>
                  <span className="num dim">
                    from {r.origin}, a {r.relation} it named, {r.hops} hop
                    {r.hops === 1 ? '' : 's'} away
                  </span>
                  <span className="num strength">{r.decayed_score.toFixed(4)}</span>
                </div>
                <p className="call-why">“{r.evidence}”</p>
                <div className="call-basis num">{r.path}</div>
              </article>
            ))}
          </div>
        </>
      )}
    </div>
  )
}
