/**
 * The API contract. Agreed here before web and api go build against imagined shapes.
 *
 * Read path budget: p95 under 200ms. Every exposure figure is precomputed; nothing
 * on this surface is calculated during a page load.
 */

export type IsoDate = string;      // 'YYYY-MM-DD'
export type IsoDateTime = string;  // ISO 8601, always UTC, always with 'Z'
export type CompanyUid = string;   // '{MIC}:{TICKER}', e.g. 'XNAS:UCTT'
export type Iso2 = string;         // ISO 3166-1 alpha-2

/** Every read takes an as_of. There is no endpoint that omits it. */
export interface AsOfParam { asOf?: IsoDateTime }   // defaults to now(), explicitly

/* ----------------------------------------------------------------- citation
 * The citation is a first-class object, not a tooltip. It is what the product
 * sells, so it is modelled before anything that references it.
 */
export interface Citation {
  chunkId: string;
  documentId: string;
  /** The exact sentence. Rendered verbatim, never paraphrased. */
  quote: string;
  charStart: number;
  charEnd: number;
  docType: string;              // '10-K' | 'transcript' | 'annual_report' | ...
  sectionLabel: string | null;  // 'Item 1A. Risk Factors'
  /** When this became public. Not the period it covers. */
  filedAtUtc: IsoDateTime;
  periodEnd: IsoDate | null;
  sourceUrl: string;
  filerName: string;
}

/* -------------------------------------------------------- globe + drill-down
 * GET /v1/globe/countries?asOf=
 * Country aggregates for the globe. Click a country -> sectors.
 */
export interface CountryTile {
  country: Iso2;
  name: string;
  companyCount: number;
  /** Companies with >=1 outbound dependency edge in the graph as of asOf. */
  mappedCompanyCount: number;
  sectorCount: number;
  /** Live events touching this country. Drives the globe's accent colour. */
  activeEventCount: number;
  /** Null when no verified price source covers this market - see sources.md. */
  sectorMoveSummary: SectorMove[] | null;
}

/** GET /v1/countries/{iso2}/sectors?asOf= */
export interface SectorMove {
  atlasSector: string;
  name: string;
  companyCount: number;
  /** Median daily % change across the sector. Null if no licensed price source. */
  medianChangePct: number | null;
  asOfTradeDate: IsoDate | null;
  /** How many companies here are exposed to a currently-active event. */
  exposedCompanyCount: number;
}

/** GET /v1/countries/{iso2}/sectors/{sector}/companies?asOf=&limit= */
export interface CompanyRow {
  companyUid: CompanyUid;
  commonName: string;
  legalName: string;
  marketCapBand: 'mega' | 'large' | 'mid' | 'small' | 'micro';
  marketCapUsd: number | null;
  changePct: number | null;
  /** Edges out of this company that we can cite. The honest density signal. */
  citedEdgeCount: number;
  /** Explains the move with cited evidence where we have it, else null.
   *  Never a generated narrative with no document behind it. */
  moveContext: MoveContext | null;
}

export interface MoveContext {
  /** Events whose propagation reaches this company, ranked. */
  events: { eventId: string; name: string; hops: number; isSurprising: boolean }[];
  citations: Citation[];
}

/* ------------------------------------------------------------------- company
 * GET /v1/companies/{companyUid}?asOf=
 */
export interface CompanyDetail {
  companyUid: CompanyUid;
  legalName: string;
  commonName: string;
  formerNames: string[];
  countryHq: Iso2;
  hq: { lat: number; lon: number; city: string | null };
  atlasSector: string;
  marketCapBand: CompanyRow['marketCapBand'];
  fiscalYearEnd: string;        // 'MM-DD'
  status: 'active' | 'delisted' | 'acquired' | 'merged' | 'suspended';
  listings: { exchangeMic: string; ticker: string; isPrimary: boolean }[];
  identifiers: { scheme: string; value: string }[];
  dependsOn: EdgeSummary[];     // upstream
  dependedOnBy: EdgeSummary[];  // downstream
  /** Disclosed dependence with no counterparty named. Shown as an honest absence,
   *  never as a placeholder node. */
  unnamedDependencies: { quote: string; citation: Citation }[];
  documentCount: number;
  lastFiledAtUtc: IsoDateTime | null;
}

export interface EdgeSummary {
  edgeId: string;
  counterparty: { companyUid: CompanyUid | null; name: string };
  edgeType: string;
  evidenceType: 'named_concentration' | 'named_narrative' | 'named_qa' | 'named_contract';
  substitutability: 'sole_source' | 'single_source' | 'limited' | 'multiple' | 'unstated';
  materialityPct: number | null;
  /** Deterministic, versioned scoring code produced this. Never a model. */
  confidence: number;
  scorerVersion: string;
  validFrom: IsoDateTime;
  validTo: IsoDateTime | null;
  citation: Citation;
}

/* --------------------------------------------------------------------- event
 * GET /v1/events/{eventId}/exposure?asOf=&limit=
 * The core product surface. Everything above is navigation into this.
 */
export interface ExposureResponse {
  event: EventSummary;
  /** The graph is read as it stood on this instant. Shown in the UI, not hidden. */
  asOf: IsoDateTime;
  scorerVersion: string;
  totalExposed: number;
  surprisingCount: number;
  rows: ExposureRow[];
}

export interface EventSummary {
  eventId: string;
  name: string;
  eventType: string;
  firstOccurredUtc: IsoDateTime | null;
  becamePublicUtc: IsoDateTime;
  /** 'unconfirmed' never drives a user-visible exposure claim. */
  confirmationLevel: 'unconfirmed' | 'corroborated' | 'primary_confirmed';
  locations: { name: string | null; lat: number; lon: number; country: Iso2 | null }[];
  chokepoints: string[];
  commodities: string[];
  sources: { url: string; headline: string | null; isPrimary: boolean }[];
}

export interface ExposureRow {
  companyUid: CompanyUid;
  commonName: string;
  countryHq: Iso2;
  atlasSector: string;
  marketCapBand: CompanyRow['marketCapBand'];
  score: number;
  hops: 1 | 2 | 3;
  /** The product's entire argument, as a boolean. These rows are visually
   *  distinguished from the obvious ones - see DESIGN.md. */
  isSurprising: boolean;
  /** Every hop, each with the sentence that proves it. The path IS the explanation. */
  path: EdgeSummary[];
}

/* ------------------------------------------------------- replay + simulation */

/** GET /v1/replay/{eventId}?asOf= — asOf is pinned to the event date and cannot
 *  be moved forward. The backtest harness is physically unable to see later edges. */
export interface ReplayResponse extends ExposureResponse {
  /** Revealed only after the user asks: who actually disclosed an impact later. */
  outcomes: {
    companyUid: CompanyUid;
    wasPredicted: boolean;
    citation: Citation;        // the filing where they reported it
  }[] | null;
}

/** POST /v1/simulate */
export interface SimulationRequest {
  shock: {
    kind: 'chokepoint' | 'company' | 'commodity' | 'country';
    target: string;
    severity: number;          // 0..1
  };
  universeId: string;
  asOf?: IsoDateTime;
  maxHops?: 1 | 2 | 3;         // capped at 3, see ADR on the three-hop limit
}

/* ------------------------------------------------------------- states + meta
 * Empty, loading and error states are designed, not afterthoughts. The API
 * gives the UI enough to render an honest empty state.
 */
export interface Coverage {
  universeCompanyCount: number;
  companiesWithEdges: number;
  /** Named explicitly so the UI can say "we have no coverage of 6 of your 40
   *  suppliers" rather than implying a confident silence. */
  uncoveredCompanyUids: CompanyUid[];
  vintage: string;
  graphAsOf: IsoDateTime;
}

export interface ApiError {
  code: 'not_found' | 'no_coverage' | 'no_price_source' | 'as_of_before_corpus' | 'rate_limited';
  message: string;
  detail?: Record<string, unknown>;
}
