import { useEffect, useMemo, useState } from 'react'
import Globe3D, { type ArcSpec, type Pt } from './components/Globe3D'
import Timeline from './components/Timeline'
import { CountryList, SectorList, CompanyList, EdgeList, ExposureList, Empty } from './components/Panels'
import { AS_OF, EVENT_AT, EVENT_CAMERA, EXPOSURE, TIMELINE } from './example'
import * as api from './client'
import type { CompanyDetail, CompanyRow, CountryTile, SectorMove } from '@shared/api'

const PRODUCT = import.meta.env.VITE_PRODUCT_NAME ?? 'GeoTrade'
const EDGAR = (cik: string) => `https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=${cik}`

type Surface = 'live' | 'replay' | 'simulate'
type View =
  | { k: 'home' }
  | { k: 'country'; iso2: string }
  | { k: 'sector'; iso2: string; sector: SectorMove }
  | { k: 'company'; uid: string; back: View }
  | { k: 'event' }

export default function App() {
  const [mode, setMode] = useState<api.Mode>('checking')
  const [meta, setMeta] = useState<api.Meta | null>(null)
  const [surface, setSurface] = useState<Surface>('live')
  const [view, setView] = useState<View>({ k: 'home' })
  const [tab, setTab] = useState<'up' | 'down'>('up')
  const [tl, setTl] = useState(TIMELINE.length - 1)

  const [countries, setCountries] = useState<CountryTile[]>([])
  const [points, setPoints] = useState<Pt[]>([])
  const [sectors, setSectors] = useState<SectorMove[] | null>(null)
  const [companies, setCompanies] = useState<CompanyRow[] | null>(null)
  const [detail, setDetail] = useState<CompanyDetail | null | undefined>(undefined)

  const ready = mode === 'live' || mode === 'snapshot'
  useEffect(() => {
    api.probe().then(m => { setMode(m); if (m === 'snapshot') api.getMeta().then(setMeta) })
  }, [])
  useEffect(() => {
    if (!ready) return
    api.getCountries().then(setCountries)
    api.getPoints().then(setPoints)
  }, [ready])

  const iso = view.k === 'country' || view.k === 'sector' ? view.iso2 : null
  useEffect(() => { if (iso) { setSectors(null); api.getSectors(iso).then(setSectors) } }, [iso])
  useEffect(() => {
    if (view.k !== 'sector') return
    setCompanies(null); api.getCompanies(view.iso2, view.sector.atlasSector).then(setCompanies)
  }, [view.k === 'sector' ? view.sector.atlasSector + view.iso2 : null])
  useEffect(() => {
    if (view.k !== 'company') return
    setDetail(undefined); api.getCompany(view.uid).then(setDetail)
  }, [view.k === 'company' ? view.uid : null])

  const byUid = useMemo(() => new Map(points.map(p => [p.uid, p])), [points])
  const showEvent = surface !== 'live' || view.k === 'event'

  const located = points.reduce((a, p) => a + (p.w ?? 1), 0)
  const centroid = (iso2: string) => {
    const ps = points.filter(p => p.country === iso2)
    const w = ps.reduce((a, p) => a + (p.w ?? 1), 0)
    if (!w) return null
    return { lat: ps.reduce((a, p) => a + p.lat * (p.w ?? 1), 0) / w,
             lon: ps.reduce((a, p) => a + p.lon * (p.w ?? 1), 0) / w, altitude: 1.6 }
  }

  const focus =
    showEvent ? EVENT_CAMERA
    : view.k === 'company' && detail?.hq.lat != null
      ? { lat: detail.hq.lat, lon: detail.hq.lon!, altitude: 1.4 }
    : iso ? centroid(iso)
    : null

  const highlight = useMemo(() => {
    if (showEvent) return new Set(EXPOSURE.rows.map(r => r.companyUid))
    if (view.k === 'company') return new Set([view.uid])
    if (view.k === 'sector') return new Set((companies ?? []).slice(0, 120).map(c => c.companyUid))
    return undefined
  }, [showEvent, view, companies])

  const arcs: ArcSpec[] = useMemo(() => {
    if (!showEvent) return []
    return EXPOSURE.rows.flatMap(r => {
      const p = byUid.get(r.companyUid)
      return p ? [{ startLat: EVENT_AT.lat, startLng: EVENT_AT.lon,
                    endLat: p.lat, endLng: p.lon, surprising: r.isSurprising }] : []
    })
  }, [showEvent, byUid])

  const go = (v: View) => { setView(v); if (v.k !== 'event') setSurface('live') }
  // Only the most recent timeline entry has illustrative edges behind it.
  const modelled = surface !== 'replay' || tl === TIMELINE.length - 1

  return (
    <div className="shell">
      <header className="topbar">
        <span className="brand">{PRODUCT}</span>
        <span className="proto" title="Reference data is live. Dependency edges and events are illustrative.">
          {mode === 'snapshot' ? 'static demo' : 'prototype'}
        </span>
        <nav className="surfaces">
          {(['live', 'replay', 'simulate'] as Surface[]).map(s => (
            <button key={s} aria-selected={surface === s}
                    onClick={() => { setSurface(s); setView(s === 'live' ? { k: 'home' } : { k: 'event' }) }}>
              {s}
            </button>
          ))}
        </nav>
        <span className="status">
          <i className={ready ? 'ok' : 'bad'} />
          {ready
            ? `${countries.reduce((a, c) => a + c.companyCount, 0).toLocaleString()} companies · ${countries.length} countries`
            : mode === 'checking' ? 'connecting…' : 'data offline'}
        </span>
        <span className="asof num">
          {surface === 'replay' ? `as of ${TIMELINE[tl].t}`
            : meta ? `snapshot ${meta.generatedOn}` : `as of ${AS_OF.slice(0, 10)}`}
        </span>
      </header>

      <div className={`main${surface === 'replay' ? ' with-timeline' : ''}`}>
        <div className="stage">
          <Globe3D
            points={points}
            selected={iso}
            onSelectCountry={c => go(c ? { k: 'country', iso2: c } : { k: 'home' })}
            focus={focus}
            highlight={highlight}
            arcs={arcs}
            rings={showEvent ? [{ lat: EVENT_AT.lat, lng: EVENT_AT.lon }] : []}
            mode={view.k === 'home' && !showEvent ? 'coverage' : 'detail'}
          />
          {view.k === 'home' && !showEvent && (
            <div className="stage-caption">
              <h1>Who depends on whom</h1>
              <p>Built from what companies have already said in public.
                 Every edge carries the sentence that proves it.</p>
            </div>
          )}
          {surface === 'replay' && <Timeline idx={tl} onPick={setTl} />}
          <div className="attrib">
            Contains data from GeoNames, CC BY 4.0 · company identity from SEC EDGAR ·
            imagery NASA · not investment advice
          </div>
        </div>

        <aside className="panel">
          <div className="panel-head">
            <div className="crumbs">
              {view.k !== 'home' && <><button onClick={() => go({ k: 'home' })}>World</button><span> / </span></>}
              {view.k === 'sector' && <><button onClick={() => go({ k: 'country', iso2: view.iso2 })}>{view.iso2}</button><span> / </span></>}
              {view.k === 'company' && <><button onClick={() => setView(view.back)}>back</button><span> / </span></>}
              {view.k === 'home' && 'Coverage'}
            </div>
            <div className="title">
              {view.k === 'home' ? 'Coverage by country'
                : view.k === 'country' ? (countries.find(c => c.country === view.iso2)?.name ?? view.iso2)
                : view.k === 'sector' ? view.sector.name
                : view.k === 'company' ? (detail?.commonName ?? view.uid)
                : (surface === 'replay' ? TIMELINE[tl].label : EXPOSURE.event.name)}
            </div>
            <div className="sub">
              {view.k === 'home' ? `${located.toLocaleString()} headquarters on the globe`
                : view.k === 'country' ? `${countries.find(c => c.country === view.iso2)?.companyCount ?? 0} companies · ${countries.find(c => c.country === view.iso2)?.sectorCount ?? 0} sectors`
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
              modelled ? (
                <>
                  <div className="notice">
                    <strong>Worked example, not a live result.</strong>
                    Extraction has not run, so the graph holds no dependency edges yet. Companies,
                    tickers and coordinates are real and in the database; the quoted sentences are
                    placeholders and the scores come from a stub scorer.
                  </div>
                  <ExposureList data={EXPOSURE} onPick={uid => setView({ k: 'company', uid, back: { k: 'event' } })} />
                </>
              ) : (
                /* Only one event has illustrative edges. Saying so beats showing the
                   Taiwan numbers under a 2023 headline, which is just wrong. */
                <>
                  <dl className="kv">
                    <dt>Event</dt><dd>{TIMELINE[tl].label}</dd>
                    <dt>Date</dt><dd className="num">{TIMELINE[tl].t}</dd>
                    <dt>Graph as of</dt><dd className="num">{TIMELINE[tl].t}</dd>
                  </dl>
                  <Empty title="No exposure modelled for this event yet"
                         body={`The graph is read as it stood on ${TIMELINE[tl].t} — never with anything filed later. Once extraction has run, every event on this timeline resolves the same way. Today only the Taiwan Strait example carries illustrative edges.`} />
                </>
              )
            ) : view.k === 'home' ? (
              <CountryList tiles={countries} onPick={c => go({ k: 'country', iso2: c })} />
            ) : view.k === 'country' ? (
              sectors === null ? <Empty title="Loading…" body="" />
                : <SectorList sectors={sectors} onPick={s => go({ k: 'sector', iso2: view.iso2, sector: s })} />
            ) : view.k === 'sector' ? (
              companies === null ? <Empty title="Loading…" body="" />
                : <CompanyList companies={companies} total={view.sector.companyCount} snapshot={mode === 'snapshot'}
                               onPick={c => setView({ k: 'company', uid: c.companyUid, back: view })} />
            ) : detail === undefined ? <Empty title="Loading…" body="" />
              : detail === null ? <Empty title="Company not in this build" body={`${view.uid} has no company-level record here.`} /> : (
              <>
                <dl className="kv">
                  <dt>Legal name</dt><dd>{detail.legalName}</dd>
                  <dt>Sector</dt><dd>{detail.atlasSector}</dd>
                  <dt>HQ</dt><dd>{detail.hq.city ?? '—'}, {detail.countryHq}</dd>
                  <dt>Listing</dt><dd className="num">{detail.listings.map(l => `${l.exchangeMic}:${l.ticker}`).join(' · ') || '—'}</dd>
                  <dt>Identifiers</dt><dd className="num">
                    {detail.identifiers.map(i => i.scheme === 'CIK'
                      ? <a key={i.value} href={EDGAR(i.value)} target="_blank" rel="noreferrer">CIK {i.value} ↗</a>
                      : <span key={i.value}>{i.scheme} {i.value} </span>)}
                    {!detail.identifiers.length && '—'}
                  </dd>
                  {detail.formerNames.length > 0 && <><dt>Formerly</dt><dd>{detail.formerNames.slice(0, 3).join('; ')}</dd></>}
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
