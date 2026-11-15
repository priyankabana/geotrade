/** Data access. The reference layer is live; failures surface as empty states, never
 *  as invented data. */
import type { CompanyDetail, CompanyRow, CountryTile, ExposureResponse, SectorMove } from '@shared/api'
import type { Pt } from './components/Globe3D'

const BASE = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'
export type Mode = 'live' | 'offline' | 'checking'

async function j<T>(path: string): Promise<T> {
  const r = await fetch(BASE + path, { signal: AbortSignal.timeout(8000) })
  if (!r.ok) throw new Error(`${r.status} ${path}`)
  return r.json() as Promise<T>
}
const safe = async <T,>(p: string, fallback: T): Promise<T> => {
  try { return await j<T>(p) } catch { return fallback }
}

export const probe = async (): Promise<Mode> => {
  try { await j('/v1/health'); return 'live' } catch { return 'offline' }
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

export const getEvents = () => safe<EventRow[]>('/v1/events', [])
export const getExposure = (key: string) =>
  safe<ExposureResponse | null>(`/v1/events/${encodeURIComponent(key)}/exposure?limit=40`, null)

export const getCompany   = (uid: string) =>
  safe<CompanyDetail | null>(`/v1/companies/${encodeURIComponent(uid)}`, null)
