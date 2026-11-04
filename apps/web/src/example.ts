/**
 * The worked example used by Replay and Simulate.
 *
 * HONESTY RULE: every company, ticker and coordinate here is REAL and present in the
 * loaded database. The dependency edges and scores are ILLUSTRATIVE - extraction has
 * not run. Quotes carry an explicit placeholder, never invented filing text, and the
 * UI labels the screen as a worked example. Do not replace a placeholder with
 * plausible-sounding prose.
 */
import type { Citation, EdgeSummary, ExposureResponse } from '@shared/api'

export const AS_OF = '2026-01-01T00:00:00Z'
const Q = '[extraction has not run — the cited sentence appears here]'

const EDGAR = (cik: string) =>
  `https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=${cik}&type=10-K`

function cite(filer: string, url: string, filed: string, section: string, docType = '10-K'): Citation {
  return { chunkId: 'example', documentId: 'example', quote: Q, charStart: 0, charEnd: 0,
           docType, sectionLabel: section, filedAtUtc: filed, periodEnd: null,
           sourceUrl: url, filerName: filer }
}

function edge(to: string, toName: string, ev: EdgeSummary['evidenceType'],
              sub: EdgeSummary['substitutability'], pct: number | null, conf: number,
              c: Citation): EdgeSummary {
  return { edgeId: `${toName}-${Math.random().toString(36).slice(2, 7)}`,
           counterparty: { companyUid: to, name: toName }, edgeType: 'supplies',
           evidenceType: ev, substitutability: sub, materialityPct: pct,
           confidence: conf, scorerVersion: 'illustrative-0',
           validFrom: c.filedAtUtc, validTo: null, citation: c }
}

export const EVENT_AT = { lat: 24.5, lon: 119.5, label: 'Taiwan Strait' }
export const EVENT_CAMERA = { lat: 26, lon: 150, altitude: 2.2 }

const C = {
  UCTT: cite('Ultra Clean Holdings, Inc.', EDGAR('0001275014'), '2025-02-25T00:00:00Z', 'Item 1A. Risk Factors'),
  ICHR: cite('Ichor Holdings, Ltd.', EDGAR('0001652535'), '2025-02-21T00:00:00Z', 'Item 1. Business'),
  PLAB: cite('Photronics, Inc.', EDGAR('0000810136'), '2025-12-17T00:00:00Z', 'Item 1. Business'),
  AMKR: cite('Amkor Technology, Inc.', EDGAR('0001047127'), '2025-02-21T00:00:00Z', 'Item 1A. Risk Factors'),
  DIXON: cite('Dixon Technologies (India) Limited', 'https://www.nseindia.com/', '2025-07-30T00:00:00Z', 'Management Discussion & Analysis', 'annual_report'),
  KAYNES: cite('Kaynes Technology India Limited', 'https://www.nseindia.com/', '2025-08-12T00:00:00Z', 'Management Discussion & Analysis', 'annual_report'),
  CRUS: cite('Cirrus Logic, Inc.', EDGAR('0000772406'), '2025-05-23T00:00:00Z', 'Item 1A. Risk Factors'),
}

export const EXPOSURE: ExposureResponse = {
  event: {
    eventId: 'ex-taiwan-strait',
    name: 'Taiwan Strait shipping disruption',
    eventType: 'chokepoint',
    firstOccurredUtc: '2026-01-04T02:10:00Z',
    becamePublicUtc: '2026-01-04T06:00:00Z',
    confirmationLevel: 'unconfirmed',
    locations: [{ name: 'Taiwan Strait', lat: 24.5, lon: 119.5, country: 'TW' }],
    chokepoints: ['TAIWAN_STRAIT'],
    commodities: ['semiconductors', 'photomasks', 'substrates'],
    sources: [],
  },
  asOf: AS_OF,
  scorerVersion: 'illustrative-0',
  totalExposed: 7,
  surprisingCount: 5,
  rows: [
    { companyUid: 'XNAS:AMAT', commonName: 'Applied Materials', countryHq: 'US',
      atlasSector: 'SEMI_EQUIP', marketCapBand: 'mega', score: 0.84, hops: 1,
      isSurprising: false, path: [] },
    { companyUid: 'XNAS:LRCX', commonName: 'Lam Research', countryHq: 'US',
      atlasSector: 'SEMI_EQUIP', marketCapBand: 'mega', score: 0.79, hops: 1,
      isSurprising: false, path: [] },
    { companyUid: 'XNAS:UCTT', commonName: 'Ultra Clean Holdings', countryHq: 'US',
      atlasSector: 'ELECTRICAL_EQUIP', marketCapBand: 'mid', score: 0.61, hops: 2,
      isSurprising: true,
      path: [edge('XNAS:LRCX', 'Lam Research', 'named_concentration', 'limited', 34, 0.91, C.UCTT),
             edge('XNAS:AMAT', 'Applied Materials', 'named_concentration', 'limited', 28, 0.89, C.UCTT)] },
    { companyUid: 'XNAS:ICHR', commonName: 'Ichor Holdings', countryHq: 'US',
      atlasSector: 'SEMI_EQUIP', marketCapBand: 'small', score: 0.57, hops: 2,
      isSurprising: true,
      path: [edge('XNAS:LRCX', 'Lam Research', 'named_concentration', 'limited', 44, 0.93, C.ICHR)] },
    { companyUid: 'XNAS:PLAB', commonName: 'Photronics', countryHq: 'US',
      atlasSector: 'SEMI_EQUIP', marketCapBand: 'small', score: 0.52, hops: 2,
      isSurprising: true,
      path: [edge('XNAS:AMAT', 'Applied Materials', 'named_narrative', 'sole_source', null, 0.80, C.PLAB)] },
    { companyUid: 'XNSE:DIXON', commonName: 'Dixon Technologies', countryHq: 'IN',
      atlasSector: 'ELECTRONIC_COMPONENTS', marketCapBand: 'mid', score: 0.41, hops: 3,
      isSurprising: true,
      path: [edge('XNAS:AMKR', 'Amkor Technology', 'named_narrative', 'limited', null, 0.74, C.DIXON),
             edge('XNAS:AMAT', 'Applied Materials', 'named_narrative', 'limited', null, 0.68, C.AMKR)] },
    { companyUid: 'XNSE:KAYNES', commonName: 'Kaynes Technology India', countryHq: 'IN',
      atlasSector: 'ELECTRONIC_COMPONENTS', marketCapBand: 'mid', score: 0.38, hops: 3,
      isSurprising: true,
      path: [edge('XNAS:AMKR', 'Amkor Technology', 'named_narrative', 'limited', null, 0.71, C.KAYNES),
             edge('XNAS:LRCX', 'Lam Research', 'named_narrative', 'limited', null, 0.66, C.AMKR)] },
  ],
}

/** Replay timeline. Dates and events are real; the exposure counts are illustrative. */
export const TIMELINE = [
  { t: '2019-07-01', label: 'Japan restricts 3 materials to Korea', n: 4 },
  { t: '2021-02-15', label: 'Texas storm Uri — Austin fabs down', n: 6 },
  { t: '2021-03-19', label: 'Renesas Naka fab fire', n: 9 },
  { t: '2021-03-23', label: 'Ever Given blocks Suez', n: 7 },
  { t: '2023-08-01', label: 'China gallium & germanium controls', n: 11 },
  { t: '2026-01-04', label: 'Taiwan Strait disruption', n: 7 },
]
