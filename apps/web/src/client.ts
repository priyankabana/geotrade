/** Data access. The reference layer is real; failures surface as empty states, never
 *  as invented data.
 *
 *  The API is tried first (VITE_API_URL, default http://localhost:8000). If it cannot be
 *  reached, every call falls back to the static snapshot under /snapshot/, written by
 *  scripts/build_snapshot.py. The snapshot holds aggregates for every country plus a
 *  capped named sample (see docs/sources.md), so the deployed demo works with no backend. */
import type { CompanyDetail, CompanyRow, CountryTile, SectorMove } from '@shared/api'
import type { Pt } from './components/Globe3D'

const BASE = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'
export type Mode = 'live' | 'snapshot' | 'offline' | 'checking'

export type Meta = {
  generatedOn: string
  entities: number
  countries: number
  geolocated: number
  publishedCompanies: number
  /** iso2 -> atlasSector -> companies with a company-level record in the snapshot */
  published: Record<string, Record<string, number>>
  companiesWithEdges: number
}

async function j<T>(url: string, ms = 8000): Promise<T> {
  const r = await fetch(url, { signal: AbortSignal.timeout(ms) })
  if (!r.ok) throw new Error(`${r.status} ${url}`)
  return r.json() as Promise<T>
}
const safe = async <T,>(url: string, fallback: T): Promise<T> => {
  try { return await j<T>(url) } catch { return fallback }
}
const snap = (p: string) => `${import.meta.env.BASE_URL}snapshot/${p}`

let metaP: Promise<Meta | null> | null = null
export const getMeta = () => (metaP ??= safe<Meta | null>(snap('meta.json'), null))

/** Resolved once: true when the API answered /v1/health, false means use the snapshot. */
let liveP: Promise<boolean> | null = null
const isLive = () => (liveP ??= j(BASE + '/v1/health', 3000).then(() => true, () => false))

export const probe = async (): Promise<Mode> => {
  if (await isLive()) return 'live'
  return (await getMeta()) ? 'snapshot' : 'offline'
}

export const getCountries = async () => (await isLive())
  ? safe<CountryTile[]>(BASE + '/v1/globe/countries', [])
  : safe<CountryTile[]>(snap('countries.json'), [])

type SnapPoints = { named: Pt[]; anon: [number, number, number, string][] }
export const getPoints = async (): Promise<Pt[]> => {
  if (await isLive()) return safe<Pt[]>(BASE + '/v1/globe/points?limit=30000', [])
  const s = await safe<SnapPoints | null>(snap('points.json'), null)
  if (!s) return []
  // Companies outside the named sample are counts only: one weighted, unnamed
  // coordinate per country, which is all the globe needs to draw the bins.
  return [...s.named, ...s.anon.map(([lat, lon, w, country]) =>
    ({ uid: '', name: '', sector: '', country, lat, lon, w }))]
}

export const getSectors = async (iso2: string) => (await isLive())
  ? safe<SectorMove[]>(`${BASE}/v1/countries/${iso2}/sectors`, [])
  : safe<SectorMove[]>(snap(`sectors/${iso2}.json`), [])

export const getCompanies = async (iso2: string, s: string): Promise<CompanyRow[]> => {
  if (await isLive()) return safe<CompanyRow[]>(`${BASE}/v1/countries/${iso2}/sectors/${s}/companies?limit=400`, [])
  const m = await getMeta()
  if (!m?.published[iso2]?.[s]) return []
  return safe<CompanyRow[]>(snap(`companies/${iso2}/${s}.json`), [])
}

let detailsP: Promise<Record<string, CompanyDetail>> | null = null
export const getCompany = async (uid: string): Promise<CompanyDetail | null> => {
  if (await isLive()) return safe<CompanyDetail | null>(`${BASE}/v1/companies/${encodeURIComponent(uid)}`, null)
  const all = await (detailsP ??= safe<Record<string, CompanyDetail>>(snap('company.json'), {}))
  return all[uid] ?? null
}
