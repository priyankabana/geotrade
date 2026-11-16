import { useEffect, useMemo, useState } from 'react'
import Globe3D, { type ArcSpec, type Pt } from './components/Globe3D'
import Timeline from './components/Timeline'
import { CountryList, SectorList, CompanyList, EdgeList, ExposureList, Empty } from './components/Panels'
import * as api from './client'
import type { CompanyDetail, CompanyRow, CountryTile, ExposureResponse, SectorMove } from '@shared/api'

const PRODUCT = import.meta.env.VITE_PRODUCT_NAME ?? 'Atlas'

type Surface = 'live' | 'replay' | 'simulate'
type View =
  | { k: 'home' }
  | { k: 'country'; iso2: string }
  | { k: 'sector'; iso2: string; sector: SectorMove }
  | { k: 'company'; uid: string; back: View }
  | { k: 'event' }

export default function App() {
  const [mode, setMode] = useState<api.Mode>('checking')
  const [surface, setSurface] = useState<Surface>('live')
  const [view, setView] = useState<View>({ k: 'home' })
  const [tab, setTab] = useState<'up' | 'down'>('up')

  const [countries, setCountries] = useState<CountryTile[]>([])
  const [points, setPoints] = useState<Pt[]>([])
  const [sectors, setSectors] = useState<SectorMove[] | null>(null)
  const [companies, setCompanies] = useState<CompanyRow[] | null>(null)
  const [detail, setDetail] = useState<CompanyDetail | null>(null)

  const [events, setEvents] = useState<api.EventRow[]>([])
  const [evIdx, setEvIdx] = useState(0)
  const [exposure, setExposure] = useState<ExposureResponse | null>(null)
  const [metrics, setMetrics] = useState<api.Metrics | null>(null)

  useEffect(() => { api.probe().then(setMode) }, [])
  useEffect(() => {
    if (mode !== 'live') return
    api.getCountries().then(setCountries)
    api.getMetrics().then(setMetrics)
    api.getPoints().then(setPoints)
    api.getEvents().then(evs => {
      setEvents(evs)
      // open on the event with the most to show
      const best = evs.reduce((b, e, i) => (e.surprisingCount > (evs[b]?.surprisingCount ?? -1) ? i : b), 0)
      setEvIdx(best)
    })
  }, [mode])

  const current = events[evIdx]
  useEffect(() => {
    if (!current) return
    setExposure(null)
    api.getExposure(current.key).then(setExposure)
  }, [current?.key])

  const iso = view.k === 'country' || view.k === 'sector' ? view.iso2 : null
  useEffect(() => { if (iso) { setSectors(null); api.getSectors(iso).then(setSectors) } }, [iso])
  useEffect(() => {
    if (view.k !== 'sector') return
    setCompanies(null); api.getCompanies(view.iso2, view.sector.atlasSector).then(setCompanies)
  }, [view.k === 'sector' ? view.sector.atlasSector + view.iso2 : null])
  useEffect(() => {
    if (view.k !== 'company') return
    setDetail(null); api.getCompany(view.uid).then(setDetail)
  }, [view.k === 'company' ? view.uid : null])

  const byUid = useMemo(() => new Map(points.map(p => [p.uid, p])), [points])
  const showEvent = surface !== 'live' || view.k === 'event'
  const evLoc = current?.locations?.[0]

  const centroid = (iso2: string) => {
    const ps = points.filter(p => p.country === iso2)
    if (!ps.length) return null
    return { lat: ps.reduce((a, p) => a + p.lat, 0) / ps.length,
             lon: ps.reduce((a, p) => a + p.lon, 0) / ps.length, altitude: 1.6 }
  }

  const focus =
    showEvent && evLoc ? { lat: 26, lon: (evLoc.lon + 180) % 360 - 10, altitude: 2.2 }
    : view.k === 'company' && detail?.hq.lat != null
      ? { lat: detail.hq.lat, lon: detail.hq.lon!, altitude: 1.4 }
    : iso ? centroid(iso)
    : null

  const highlight = useMemo(() => {
    if (showEvent) return new Set((exposure?.rows ?? []).map(r => r.companyUid).filter(Boolean) as string[])
    if (view.k === 'company') return new Set([view.uid])
    if (view.k === 'sector') return new Set((companies ?? []).slice(0, 120).map(c => c.companyUid))
    return undefined
  }, [showEvent, exposure, view, companies])

  const arcs: ArcSpec[] = useMemo(() => {
    if (!showEvent || !evLoc || !exposure) return []
    return exposure.rows.flatMap(r => {
      const p = r.companyUid ? byUid.get(r.companyUid) : undefined
      return p ? [{ startLat: evLoc.lat, startLng: evLoc.lon,
                    endLat: p.lat, endLng: p.lon, surprising: r.isSurprising }] : []
    })
  }, [showEvent, exposure, evLoc, byUid])

  const go = (v: View) => { setView(v); if (v.k !== 'event') setSurface('live') }
  const totalCompanies = countries.reduce((a, c) => a + c.companyCount, 0)

  return (
    <div className="shell">
      <div className="mockstrip" style={{ background: mode === 'live' ? 'var(--surprise)' : 'var(--accent)' }}>
        {mode === 'checking' && 'connecting to API…'}
        {mode === 'live' && `Live — extraction has run. Every dependency below links to the sentence in the filing that supports it.`}
        {mode === 'offline' && (
          /* On a deployed HTTPS page the browser refuses to fetch an http://
             localhost API at all, so "start the API" is advice that cannot
             work here. Say what will. */
          typeof window !== 'undefined' && window.location.protocol === 'https:'
            ? 'This is the interface only. The graph lives in a database on your own machine, and a page served over HTTPS is not allowed to reach it — run the project locally and open localhost:5173.'
            : 'API offline — start it with: make up'
        )}
      </div>

      <header className="topbar">
        <span className="brand">{PRODUCT}</span>
        <nav className="surfaces">
          {(['live', 'replay', 'simulate'] as Surface[]).map(s => (
            <button key={s} aria-selected={surface === s}
                    onClick={() => { setSurface(s); setView(s === 'live' ? { k: 'home' } : { k: 'event' }) }}>
              {s}
            </button>
          ))}
        </nav>
        <span className="status">
          <i className={mode === 'live' ? 'ok' : 'bad'} />
          {mode === 'live'
            ? `${totalCompanies.toLocaleString()} companies · ${countries.length} countries`
              + (metrics ? ` · ${metrics.graph.relationships} cited relationships` : '')
            : mode === 'checking' ? 'connecting…' : 'API offline'}
        </span>
        <span className="asof num">
          as of {(showEvent && current ? current.becamePublicUtc.slice(0, 10) : 'today')}
        </span>
      </header>

      <div className={`main${surface === 'replay' ? ' with-timeline' : ''}`}>
        <div className="stage">
          <Globe3D
            points={points} selected={iso}
            onSelectCountry={c => go(c ? { k: 'country', iso2: c } : { k: 'home' })}
            focus={focus} highlight={highlight} arcs={arcs}
            rings={showEvent && evLoc ? [{ lat: evLoc.lat, lng: evLoc.lon }] : []}
            mode={view.k === 'home' && !showEvent ? 'coverage' : 'detail'}
          />
          {view.k === 'home' && !showEvent && (
            <div className="stage-caption">
              <h1>Who depends on whom</h1>
              <p>Built from what companies have already said in public.
                 Every edge carries the sentence that proves it.</p>
            </div>
          )}
          {surface === 'replay' && <Timeline events={events} idx={evIdx} onPick={setEvIdx}
                                              earliestFiling={metrics?.corpus.earliestFiling} />}
        </div>

        <aside className="panel">
          <div className="panel-head">
            <div className="crumbs">
              {view.k !== 'home' && <><button onClick={() => go({ k: 'home' })}>World</button><span> / </span></>}
              {view.k === 'sector' && <><button onClick={() => go({ k: 'country', iso2: view.iso2 })}>{view.iso2}</button><span> / </span></>}
              {view.k === 'company' && <><button onClick={() => setView(view.back)}>back</button><span> / </span></>}
              {view.k === 'home' && 'Coverage by country'}
            </div>
            <div className="title">
              {view.k === 'home' ? 'Coverage by country'
                : view.k === 'country' ? (countries.find(c => c.country === view.iso2)?.name ?? view.iso2)
                : view.k === 'sector' ? view.sector.name
                : view.k === 'company' ? (detail?.commonName ?? view.uid)
                : (current?.name ?? 'Exposure')}
            </div>
            <div className="sub">
              {view.k === 'home' ? `${points.length.toLocaleString()} headquarters on the globe`
                : view.k === 'country' ? `${countries.find(c => c.country === view.iso2)?.companyCount ?? 0} companies · ${countries.find(c => c.country === view.iso2)?.mappedCompanyCount ?? 0} with cited edges`
                : view.k === 'sector' ? `${view.sector.companyCount} companies`
                : view.k === 'company' ? view.uid
                : 'Ranked by disclosed dependence'}
            </div>
          </div>

          {view.k === 'company' && (
            <div className="tabs">
              <button aria-selected={tab === 'up'} onClick={() => setTab('up')}>Depends on</button>
              <button aria-selected={tab === 'down'} onClick={() => setTab('down')}>Depended on by</button>
            </div>
          )}

          <div className="panel-body">
            {showEvent ? (
              exposure === null ? <Empty title="Walking the graph…" body="" />
              : exposure.rows.length === 0 ? (
                <>
                  <div className="notice">
                    <strong>Nothing reachable at this date.</strong>
                    The graph is read as it stood on {current?.becamePublicUtc.slice(0, 10)}. Every
                    filing we hold was published after that, so none of it may be used. That is the
                    point-in-time rule doing its job rather than a gap in the data.
                  </div>
                  <Empty title="No exposure for this event"
                         body="Pick a more recent event on the timeline to see the graph populated." />
                </>
              ) : (
                <ExposureList data={exposure}
                  onPick={uid => setView({ k: 'company', uid, back: { k: 'event' } })} />
              )
            ) : view.k === 'home' ? (
              <CountryList tiles={countries} onPick={c => go({ k: 'country', iso2: c })} />
            ) : view.k === 'country' ? (
              sectors === null ? <Empty title="Loading…" body="" />
                : <SectorList sectors={sectors} onPick={s => go({ k: 'sector', iso2: view.iso2, sector: s })} />
            ) : view.k === 'sector' ? (
              companies === null ? <Empty title="Loading…" body="" />
                : <CompanyList companies={companies} onPick={c => setView({ k: 'company', uid: c.companyUid, back: view })} />
            ) : detail === null ? <Empty title="Loading…" body="" /> : (
              <>
                <dl className="kv">
                  <dt>Legal name</dt><dd>{detail.legalName}</dd>
                  <dt>Sector</dt><dd>{detail.atlasSector}</dd>
                  <dt>HQ</dt><dd>{detail.hq.city ?? '—'}, {detail.countryHq}</dd>
                  <dt>Filings held</dt><dd className="num">{detail.documentCount}</dd>
                  <dt>Identifiers</dt><dd className="num">{detail.identifiers.map(i => `${i.scheme} ${i.value}`).join(' · ') || '—'}</dd>
                </dl>
                {tab === 'up' ? <EdgeList edges={detail.dependsOn} label="Depends on" />
                              : <EdgeList edges={detail.dependedOnBy} label="Depended on by" />}
              </>
            )}
          </div>
        </aside>
      </div>
    </div>
  )
}
