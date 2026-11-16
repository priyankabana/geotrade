/** Data access. The reference layer is live; failures surface as empty states, never
 *  as invented data. */
import type { CompanyDetail, CompanyRow, CountryTile, ExposureResponse, SectorMove } from '@shared/api'
import type { Pt } from './components/Globe3D'

const BASE = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'
// Files written by scripts/snapshot_api.py: the real API's own responses,
// frozen so a page with no database behind it still shows the real graph.
const SNAPSHOT = import.meta.env.VITE_SNAPSHOT_URL ?? '/data'

export type Mode = 'live' | 'snapshot' | 'offline' | 'checking'

/** Resolved once by probe(), so one failed request does not send every later
 *  call back through an 8-second timeout on an API that is not there. */
let source: 'live' | 'snapshot' | null = null

/** Mirror of the filename rule in scripts/snapshot_api.py.
 *
 *  Only the last path segment is rewritten, and it is decoded first: callers
 *  percent-encode company uids, so `XASX:CBA` arrives as `XASX%3ACBA` and has
 *  to become `XASX-CBA` - the same name the exporter wrote - rather than
 *  `XASX-3ACBA`, which is what encoding it twice would give. */
const snapshotUrl = (path: string): string => {
  const parts = path.split('?')[0].replace(/^\/+/, '').split('/')
  const last = decodeURIComponent(parts.pop() ?? '').replace(/[^A-Za-z0-9._-]/g, '-')
  return `${SNAPSHOT}/${[...parts, last].join('/')}.json`
}

async function fetchJson<T>(url: string): Promise<T> {
  const r = await fetch(url, { signal: AbortSignal.timeout(8000) })
  if (!r.ok) throw new Error(`${r.status} ${url}`)
  return r.json() as Promise<T>
}

async function j<T>(path: string): Promise<T> {
  if (source === 'snapshot') return fetchJson<T>(snapshotUrl(path))
  try {
    return await fetchJson<T>(BASE + path)
  } catch (e) {
    // A live API that answered probe() and then failed on one path is a real
    // error and should surface as one. Falling back here would paper over it
    // with stale data and report the result as current.
    if (source === 'live') throw e
    return fetchJson<T>(snapshotUrl(path))
  }
}
const safe = async <T,>(p: string, fallback: T): Promise<T> => {
  try { return await j<T>(p) } catch { return fallback }
}

export type SnapshotMeta = {
  builtAt: string; scope: string
  entities: number; edges: number; companyPages: number; files: number
}
let snapshotMeta: SnapshotMeta | null = null
export const getSnapshotMeta = () => snapshotMeta

/** A live API wins; the snapshot is what a deployed page falls back to. */
export const probe = async (): Promise<Mode> => {
  // A page served over https may not fetch an http:// origin - the browser
  // blocks it before the request is made. On the deployed build that is every
  // local API, so probing one is not a slow path to a maybe, it is eight
  // seconds spent on a certainty.
  const liveBlocked = typeof window !== 'undefined'
    && window.location.protocol === 'https:' && BASE.startsWith('http://')
  if (!liveBlocked) {
    try {
      await fetchJson(BASE + '/v1/health')
      source = 'live'
      return 'live'
    } catch { /* fall through */ }
  }
  try {
    snapshotMeta = await fetchJson<SnapshotMeta>(snapshotUrl('/v1/snapshot'))
    source = 'snapshot'
    return 'snapshot'
  } catch { /* fall through */ }
  return 'offline'
}
export const getCountries = () => safe<CountryTile[]>('/v1/globe/countries', [])
export const getPoints    = () => safe<Pt[]>('/v1/globe/points?limit=30000', [])
export const getSectors   = (iso2: string) => safe<SectorMove[]>(`/v1/countries/${iso2}/sectors`, [])
export const getCompanies = (iso2: string, s: string) =>
  safe<CompanyRow[]>(`/v1/countries/${iso2}/sectors/${s}/companies?limit=400`, [])
export type EventRow = {
  eventId: string; key: string; name: string; eventType: string
  becamePublicUtc: string; firstOccurredUtc: string | null
  confirmationLevel: string; severity: number | null
  commodities: string[]; chokepoints: string[]
  locations: { name: string | null; lat: number; lon: number; country: string | null }[]
  totalExposed: number; surprisingCount: number
}

export type Metrics = {
  graph: { citedEdges: number; relationships: number; concentrationBacked: number
           companiesWithEdges: number }
  corpus: { documents: number; earliestFiling: string | null; latestFiling: string | null }
  exposure: { events: number; rows: number; surprising: number; surpriseRate: number }
  measuredPrecision: Record<string, { judged: number; correct: number; method: string }>
}

export const getMetrics = () => safe<Metrics | null>('/v1/metrics', null)

export const getEvents = () => safe<EventRow[]>('/v1/events', [])
export const getExposure = (key: string) =>
  safe<ExposureResponse | null>(`/v1/events/${encodeURIComponent(key)}/exposure?limit=40`, null)

export const getCompany   = (uid: string) =>
  safe<CompanyDetail | null>(`/v1/companies/${encodeURIComponent(uid)}`, null)

// --- signals ----------------------------------------------------------------
export type Signal = {
  signalId: string
  symbol: string; assetName: string; assetClass: string; currency: string | null
  companyUid: string | null
  direction: 'up' | 'down' | 'unclear'
  basis: 'cited_dependency' | 'rule'
  magnitude: number; hops: number | null; ruleId: string | null
  rationale: string; asOf: string; scorerVersion: string
  event: {
    eventId: string; key: string; name: string; eventType: string
    severity: number | null; becamePublicUtc: string; feed: string
  }
  citation: {
    quote: string; filerName: string | null; docType: string | null
    filedAt: string | null; url: string | null
  } | null
}

export type SignalSummary = {
  buckets: { assetClass: string; direction: string; basis: string
             count: number; avgMagnitude: number }[]
  feeds: { feed: string; events: number; signals: number }[]
  totals: { cited: number; rule: number; assets: number; events: number }
}

/** Every signal, once.
 *
 *  Deliberately unfiltered. The API takes filter parameters, but a snapshot is
 *  addressed by path alone, so one file per filter combination would be a
 *  combinatorial pile of near-identical JSON. There are a few hundred rows;
 *  fetching them once and filtering in the browser is both smaller and the
 *  same answer. */
export const getSignals = () => safe<Signal[]>('/v1/signals?limit=1000', [])
export const getSignalsSummary = () => safe<SignalSummary | null>('/v1/signals/summary', null)
