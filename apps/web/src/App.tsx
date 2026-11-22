import { useEffect, useMemo, useRef, useState } from 'react'
import Globe3D, { type ArcSpec, type Pt } from './components/Globe3D'
import Timeline from './components/Timeline'
import { CountryList, SectorList, CompanyList, ExposureList, Empty } from './components/Panels'
import * as api from './client'
import SignalsBoard from './components/SignalsBoard'
import Newsroom from './components/Newsroom'
import { tvSymbol } from './components/StockPanel'
import CompanyPage from './components/CompanyPage'
import Search from './components/Search'
import SectorQuotes from './components/SectorQuotes'
import Simulator from './components/Simulator'
import type { CompanyDetail, CompanyRow, CountryTile, ExposureResponse, SectorMove } from '@shared/api'
import { format, parentOf, parse, type Route } from './route'

const PRODUCT = import.meta.env.VITE_PRODUCT_NAME ?? 'Atlas'

// 'signals' is the analysis surface. The globe answers where; it answers
// what now, and it is a board rather than a map because ranking is reading.
import type { Surface } from './route'
type View =
  | { k: 'home' }
  | { k: 'globe' }
  | { k: 'country'; iso2: string }
  | { k: 'sector'; iso2: string; sector: SectorMove }
  | { k: 'company'; uid: string; back: View }
  | { k: 'event' }

export default function App() {
  const [mode, setMode] = useState<api.Mode>('checking')
  const [tab, setTab] = useState<'up' | 'down' | 'market'>('up')

  // Where you are lives in the address bar, not in state, so a company can be
  // linked, bookmarked and reached with the back button. See route.ts.
  const [loc, setLoc] = useState(() =>
    parse(typeof window === 'undefined' ? '' : window.location.hash))
  useEffect(() => {
    const onHash = () => setLoc(parse(window.location.hash))
    window.addEventListener('hashchange', onHash)
    return () => window.removeEventListener('hashchange', onHash)
  }, [])
  const surface = loc.surface
  const route = loc.route

  // Whether this session has navigated at all. A reader who followed a link
  // straight to a company has no history to step back through, so the back
  // button has to land somewhere sensible rather than leave the site.
  const moved = useRef(false)

  const goTo = (r: Route, s: Surface = r.k === 'event' ? surface : 'live') => {
    const next = format({ surface: s, route: r })
    moved.current = true
    if (window.location.hash !== next) window.location.hash = next
    else setLoc(parse(next))
  }
  const goBack = () => {
    if (moved.current && window.history.length > 1) window.history.back()
    else goTo(parentOf(route))
  }

  const [countries, setCountries] = useState<CountryTile[]>([])
  const [points, setPoints] = useState<Pt[]>([])
  const [sectors, setSectors] = useState<SectorMove[] | null>(null)
  const [companies, setCompanies] = useState<CompanyRow[] | null>(null)
  const [detail, setDetail] = useState<CompanyDetail | null>(null)

  const [events, setEvents] = useState<api.EventRow[]>([])
  const [evIdx, setEvIdx] = useState(0)
  const [exposure, setExposure] = useState<ExposureResponse | null>(null)
  const [metrics, setMetrics] = useState<api.Metrics | null>(null)

  // The rest of this file still thinks in terms of View, so the route is
  // translated back into one. A sector arrives from the URL as a bare code and
  // is matched against the loaded list; until that list lands, the code stands
  // in for the name so a deep link renders immediately rather than blanking.
  const view: View = useMemo(() => {
    switch (route.k) {
      case 'country': return { k: 'country', iso2: route.iso2 }
      case 'sector': {
        const found = (sectors ?? []).find(x => x.atlasSector === route.sectorCode)
        return { k: 'sector', iso2: route.iso2,
                 sector: found ?? { atlasSector: route.sectorCode,
                                    name: route.sectorCode,
                                    companyCount: 0 } as SectorMove }
      }
      case 'company': return { k: 'company', uid: route.uid, back: { k: 'home' } }
      case 'globe':   return { k: 'globe' }
      case 'event':   return { k: 'event' }
      default:        return { k: 'home' }
    }
  }, [route, sectors])

  useEffect(() => { api.probe().then(setMode) }, [])
  useEffect(() => {
    // A snapshot is served by the same client through the same calls, so every
    // loader below is unchanged - only where the bytes come from differs.
    if (mode !== 'live' && mode !== 'snapshot') return
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

  const tvSym = detail ? tvSymbol(detail.listings) : null
  // Inside the two-pane tool, the world view is 'globe'. 'home' is the
  // landing and never reaches this branch.
  const atWorld = view.k === 'globe' || view.k === 'home'

  // The company currently under discussion, whatever surface is showing it.
  const focusUid = view.k === 'company' ? view.uid : null
  const focusName = detail && detail.companyUid === focusUid ? detail.commonName : null

  /** Where a surface switch should land.
   *
   *  Keeping the company is the whole point: ask the newsroom about the firm
   *  you were just reading rather than being sent back to the world. Replay
   *  is the exception - it reads the graph at a past date and needs an event
   *  selected, which a company does not supply.
   */
  const nextRouteFor = (s: Surface): Route => {
    if (s === 'replay') return { k: 'event' }
    if (focusUid) return { k: 'company', uid: focusUid }
    return s === 'simulate' ? { k: 'event' } : { k: 'globe' }
  }

  const totalCompanies = countries.reduce((a, c) => a + c.companyCount, 0)

  return (
    <div className="shell">
      {/* The strip only appears when something is wrong. A banner across a
          working page explaining that it is working is noise - the status line
          in the header already says which mode this is, and the snapshot's
          build date lives on the about page. */}
      {mode === 'offline' && (
        <div className="mockstrip">
          {typeof window !== 'undefined' && window.location.protocol === 'https:'
            ? 'No data loaded. If you are running this locally, start the API with: make up'
            : 'API offline - start it with: make up'}
        </div>
      )}

      <header className="topbar">
        <span className="brand">{PRODUCT}</span>
        <Search points={points} onPick={uid => goTo({ k: 'company', uid })} />
        <span className="status">
          <i className={mode === 'live' || mode === 'snapshot' ? 'ok' : 'bad'} />
          {mode === 'live' || mode === 'snapshot'
            ? `${totalCompanies.toLocaleString()} companies · ${countries.length} countries`
              + (metrics ? ` · ${metrics.graph.relationships} cited relationships` : '')
            : mode === 'checking' ? 'connecting…' : 'API offline'}
        </span>
        {/* The as-of date only means something while the graph is being read
            at a past date. On the live view it said "as of today", which is
            four words to tell the reader that now is now. */}
        {/* Only replay actually reads the graph at a past date. showEvent is
            true for every non-live surface, so keying off it put a date on
            the newsroom, where it describes nothing. */}
        {(surface === 'replay' || view.k === 'event') && current && (
          <span className="asof num">as of {current.becamePublicUtc.slice(0, 10)}</span>
        )}
      </header>

      {/* The surfaces float over the globe rather than sitting in the chrome:
          they are the main thing you do here, and a centred bar reads as a
          control for the thing behind it instead of a row of tabs. */}
      <nav className="surfaces">
        {(['live', 'signals', 'news', 'replay', 'simulate'] as Surface[]).map(s => (
          <button key={s} aria-selected={surface === s}
                  onClick={() => goTo(nextRouteFor(s), s)}>
            <span className="s-label">{s}</span>
          </button>
        ))}
      </nav>

      {/* The subject travels with you. Switching surface used to throw the
          company away and return to the world, so the five tabs behaved like
          five separate apps: you could reach a company from the newsroom but
          never ask the newsroom about the company you were reading. */}
      {focusUid && surface !== 'live' && (
        <div className="subject">
          <span className="subject-k num">subject</span>
          <strong>{focusName ?? focusUid}</strong>
          {/* Two ways out, because they are different intentions: read this
              company in full, or stop narrowing and see the whole surface. */}
          <button onClick={() => goTo({ k: 'company', uid: focusUid }, 'live')}>
            open
          </button>
          <button onClick={() => goTo({ k: 'globe' })} title="Stop narrowing to this company">
            clear ✕
          </button>
        </div>
      )}

      {surface === 'signals' ? (
         <SignalsBoard focusUid={focusUid} focusName={focusName}
                       onOpenCompany={uid => goTo({ k: 'company', uid }, 'live')} />
       )
       : surface === 'news' ? (
         <Newsroom focusName={focusName}
                   onOpenCompany={uid => goTo({ k: 'company', uid }, 'live')} />
       )
       : surface === 'simulate' ? (
         <Simulator seedUid={focusUid}
                    onOpenCompany={uid => goTo({ k: 'company', uid }, 'live')} />
       )
       /* A company gets the whole width. It used to share a 430px column with
          the globe, which made the chart unreadable and kept a map on screen
          for a question the reader had already stopped asking. */
       : view.k === 'company' ? (
         detail
           ? <CompanyPage detail={detail} tab={tab} setTab={setTab} tvSym={tvSym}
                          onBack={goBack} />
           : <div className="cpage"><div className="cpage-body">
               <Empty title="Loading…" body="" /></div></div>
       ) : (
      <div className={`main${surface === 'replay' ? ' with-timeline' : ''}`}>
        <div className="stage">
          <Globe3D
            points={points} selected={iso}
            onSelectCountry={c => goTo(c ? { k: 'country', iso2: c } : { k: 'home' })}
            focus={focus} highlight={highlight} arcs={arcs}
            rings={showEvent && evLoc ? [{ lat: evLoc.lat, lng: evLoc.lon }] : []}
            mode={atWorld && !showEvent ? 'coverage' : 'detail'}
          />
          {atWorld && !showEvent && (
            <div className="stage-caption">
              <h1>Who depends on <em>whom</em></h1>
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
              {!atWorld && <><button onClick={() => goTo({ k: 'globe' })}>World</button><span> / </span></>}
              {view.k === 'sector' && <><button onClick={() => goTo({ k: 'country', iso2: view.iso2 })}>{view.iso2}</button><span> / </span></>}
              {/* The root has no trail. It used to repeat the title verbatim,
                  so the panel opened by saying the same four words twice. */}
              {view.k === 'country' && <span className="here">{view.iso2}</span>}
            </div>
            <div className="title">
              {atWorld ? 'Coverage by country'
                : view.k === 'country' ? (countries.find(c => c.country === view.iso2)?.name ?? view.iso2)
                : view.k === 'sector' ? view.sector.name
                : (current?.name ?? 'Exposure')}
            </div>
            <div className="sub">
              {atWorld ? `${points.length.toLocaleString()} headquarters on the globe`
                : view.k === 'country' ? `${countries.find(c => c.country === view.iso2)?.companyCount ?? 0} companies · ${countries.find(c => c.country === view.iso2)?.mappedCompanyCount ?? 0} with cited edges`
                : view.k === 'sector' ? `${view.sector.companyCount} companies`
                : 'Ranked by disclosed dependence'}
            </div>
          </div>

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
                  onPick={uid => goTo({ k: 'company', uid })} />
              )
            ) : atWorld ? (
              <CountryList tiles={countries} onPick={c => goTo({ k: 'country', iso2: c })} />
            ) : view.k === 'country' ? (
              sectors === null ? <Empty title="Loading…" body="" />
                : <SectorList sectors={sectors}
                               onPick={s => goTo({ k: 'sector', iso2: view.iso2,
                                                   sectorCode: s.atlasSector })} />
            ) : (
              companies === null ? <Empty title="Loading…" body="" /> : (
                <>
                  <SectorQuotes companies={companies} sectorName={view.sector.name} />
                  <CompanyList companies={companies}
                               onPick={c => goTo({ k: 'company', uid: c.companyUid })} />
                </>
              )
            )}
          </div>
        </aside>
      </div>
      )}
    </div>
  )
}