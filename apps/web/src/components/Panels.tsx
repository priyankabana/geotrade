import type { CompanyRow, CountryTile, EdgeSummary, ExposureResponse, SectorMove } from '@shared/api'
import Citation from './Citation'

const BAND: Record<string, string> = {
  mega: 'mega', large: 'large', mid: 'mid', small: 'small', micro: 'micro',
}

/* Coverage by country. The globe shows where the data is; this says how much, and
   gives a target you can hit without aiming at a moving sphere. */
/** The ten countries the project set out to cover.
 *
 *  They sit at the top of the list whatever their company count, because the
 *  list answers "where do we cover" before it answers "where is the data
 *  thickest". Sorting purely by count buried India below Lithuania, which
 *  says nothing about either country and quite a lot about our filing feed.
 */
const COVERED = ['US', 'IN', 'CA', 'AU', 'GB', 'DE', 'JP', 'CN', 'FR', 'HK']

export function CountryList({ tiles, onPick }:
  { tiles: CountryTile[]; onPick: (iso2: string) => void }) {
  if (!tiles.length) return <Empty title="No coverage loaded" body="Start the API and reload." />
  const max = Math.max(...tiles.map(t => t.companyCount))
  const rank = (c: string) => {
    const i = COVERED.indexOf(c)
    return i === -1 ? COVERED.length : i
  }
  const ordered = [...tiles].sort((a, b) =>
    rank(a.country) - rank(b.country) || b.companyCount - a.companyCount)
  return <>{ordered.map(t => (
    <button key={t.country} className="row row-country" onClick={() => onPick(t.country)}>
      <span className="iso num">{t.country}</span>
      <span>{t.name}</span>
      <span className="bar"><i style={{ width: `${(t.companyCount / max) * 100}%` }} /></span>
      <span className="num">{t.companyCount.toLocaleString()}</span>
    </button>
  ))}</>
}

export function SectorList({ sectors, onPick }:
  { sectors: SectorMove[]; onPick: (s: SectorMove) => void }) {
  if (!sectors.length) return <Empty title="No sectors loaded for this country"
    body="Only the United States has companies loaded. Collect the other markets into data/companies/ and reload." />
  return <>
    {sectors.map(s => (
      <button key={s.atlasSector} className="row row-sector" onClick={() => onPick(s)}>
        <span>{s.name}</span>
        <span className="num muted">{s.companyCount} cos</span>
        <span className="num">{s.exposedCompanyCount > 0
          ? <span className="hazard">{s.exposedCompanyCount} exposed</span>
          : <span className="muted">-</span>}</span>
      </button>
    ))}
    <PriceNote />
  </>
}

function PriceNote() {
  return <div className="empty" style={{ paddingTop: 14 }}>
    <h3>Sector price movement is not shown</h3>
    <p className="sub">Exchange price data is licensed in all six markets. No price source is
      loaded until it has a verified row in <code>docs/sources.md</code> with a quoted licence.
      Until then this column stays empty rather than showing a number we cannot defend.</p>
  </div>
}

export function CompanyList({ companies, onPick }:
  { companies: CompanyRow[]; onPick: (c: CompanyRow) => void }) {
  if (!companies.length) return <Empty title="No companies in this sector yet"
    body="The universe is loaded but extraction has not run, so no dependency edges exist here." />
  return <>{companies.map(c => (
    <button key={c.companyUid} className="row row-company" onClick={() => onPick(c)}>
      <span>{c.commonName}</span>
      <span className="num muted">{BAND[c.marketCapBand]}</span>
      <span className="num">{c.citedEdgeCount > 0
        ? `${c.citedEdgeCount} cited`
        : <span className="muted">no edges</span>}</span>
    </button>
  ))}</>
}

export function EdgeList({ edges, label }: { edges: EdgeSummary[]; label: string }) {
  if (!edges.length) return <div className="empty"><h3>{label}: none cited</h3>
    <p className="sub">An absence here means we found no sentence naming a counterparty - not
      that none exists. The 10% disclosure threshold hides smaller relationships entirely.</p></div>
  return <div style={{ padding: '10px 16px' }}>
    <div className="crumbs">{label}</div>
    {edges.map(e => (
      <div key={e.edgeId} style={{ marginBottom: 14 }}>
        <div><strong>{e.counterparty.name}</strong>{' '}
          <span className={e.evidenceType === 'named_concentration' ? 'tier-hard' : 'tier-soft'}
                title={e.evidenceType === 'named_concentration'
                  ? 'The filing states a percentage. Every edge of this kind we audited was correct.'
                  : 'The filing names the counterparty but gives no figure. About two thirds of these were correct when audited.'}>
            {e.evidenceType === 'named_concentration' ? 'disclosed %' : 'named only'}
          </span>{' '}
          <span className="num muted">
            {/* "depends on" means two different things and the reader deserves to
                know which: revenue riding on a customer, or an input bought from
                a supplier. */}
            {e.edgeType === 'customer_concentration' ? 'revenue from this customer' : 'input from this supplier'}
            {e.corroboratingCitations && e.corroboratingCitations > 1
              ? ` · cited ${e.corroboratingCitations}×` : ''}
            {e.substitutability !== 'unstated' ? ' · ' + e.substitutability.replace('_', ' ') : ''}
            {e.materialityPct != null
              ? ` · ${e.materialityPct}% of ${e.materialityBasis ?? 'a basis the filing does not state'}`
              : ''}
            {' · confidence '}{e.confidence.toFixed(2)}
          </span></div>
        <Citation c={e.citation} />
      </div>
    ))}
  </div>
}

export function ExposureList({ data, onPick }:
  { data: ExposureResponse; onPick: (uid: string) => void }) {
  return <>
    <div className="kv">
      <dt>Event</dt><dd>{data.event.name}</dd>
      <dt>Became public</dt><dd className="num">{data.event.becamePublicUtc.slice(0, 16).replace('T', ' ')}Z</dd>
      <dt>Confirmation</dt><dd>{data.event.confirmationLevel === 'unconfirmed'
        ? <span className="hazard">unconfirmed - not shown to users in production</span>
        : data.event.confirmationLevel}</dd>
      <dt>Graph as of</dt><dd className="num">{data.asOf.slice(0, 10)}</dd>
      <dt>Exposed</dt><dd className="num">{data.totalExposed} companies,{' '}
        <span className="surprise-mark">{data.surprisingCount} you would not have listed</span></dd>
    </div>
    {data.rows.map(r => (
      <div key={r.companyUid} className={r.isSurprising ? 'surprise-row' : ''}>
        <button className="row row-exp" onClick={() => onPick(r.companyUid)}>
          <span className="surprise-mark">{r.isSurprising ? '◆' : ''}</span>
          <span>{r.commonName}</span>
          <span className="num muted">{r.hops} hop{r.hops > 1 ? 's' : ''}</span>
          <span className="num">{r.score.toFixed(2)}</span>
        </button>
        {r.path.length > 0 && (
          <div className="path" style={{ margin: '0 16px 10px 28px' }}>
            {r.path.map(h => (
              <div className="hop" key={h.edgeId}>
                <span className="arrow">→ depends on </span>
                <strong>{h.counterparty.name}</strong>
                <Citation c={h.citation} />
              </div>
            ))}
          </div>
        )}
      </div>
    ))}
  </>
}

export function Empty({ title, body }: { title: string; body: string }) {
  return <div className="empty"><h3>{title}</h3><p className="sub">{body}</p></div>
}
