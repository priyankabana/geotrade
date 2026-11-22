/** One company, full width.
 *
 *  This used to live in the 430px panel beside the globe, which was the wrong
 *  home for it twice over: a price chart squeezed into a third of a column is
 *  unreadable, and the globe answers "where in the world" - a question the
 *  reader has already finished asking by the time they are looking at one
 *  company's filings.
 *
 *  The lead sentence is the part worth defending. A reader who lands here from
 *  a shared link has no idea why this company is in the graph at all, and the
 *  tabs answer that only after they pick one. So the page says it in a line
 *  first, in words, built from the counts it already has.
 */
import type { CompanyDetail } from '@shared/api'
import { EdgeList, Empty } from './Panels'
import StockPanel from './StockPanel'

type Tab = 'up' | 'down' | 'market'

/** What this company's position in the graph actually amounts to.
 *
 *  Deliberately plain about absence. "No disclosed dependencies" reads like a
 *  gap in our data; it is usually a fact about disclosure rules, and saying so
 *  stops a reader drawing the wrong conclusion from an empty tab.
 */
function lead(d: CompanyDetail): string {
  const up = d.dependsOn.length
  const down = d.dependedOnBy.length
  const docs = d.documentCount
  const filings = `${docs} filing${docs === 1 ? '' : 's'}`

  if (!up && !down) {
    return `We hold ${filings} for this company and neither it nor anyone else `
         + `has named a dependency in them. Being absent from the graph is not `
         + `the same as being unexposed: a buyer is never required to name its `
         + `suppliers, which is why this graph is built from the suppliers' side.`
  }
  const parts: string[] = []
  if (up) parts.push(`names ${up} counterpart${up === 1 ? 'y' : 'ies'} it depends on`)
  if (down) parts.push(`${down} compan${down === 1 ? 'y' : 'ies'} have named it as one of theirs`)
  return `Across ${filings}, this company ${parts.join(', and ')}. `
       + `Every edge below carries the sentence from the filing that proves it.`
}

export default function CompanyPage({
  detail, tab, setTab, onBack, tvSym,
}: {
  detail: CompanyDetail
  tab: Tab
  setTab: (t: Tab) => void
  onBack: () => void
  tvSym: string | null
}) {
  const primary = detail.listings.find(l => l.isPrimary) ?? detail.listings[0]
  const upN = detail.dependsOn.length
  const downN = detail.dependedOnBy.length

  return (
    <div className="cpage">
      <header className="cpage-head">
        <button className="crumb" onClick={onBack}>← back</button>

        <div className="cpage-id">
          <h1>{detail.commonName}</h1>
          <span className="num ticker">
            {primary ? `${primary.exchangeMic}:${primary.ticker}` : '—'}
          </span>
        </div>

        <p className="clead">{lead(detail)}</p>

        <dl className="cmeta">
          <div><dt>Legal name</dt><dd>{detail.legalName}</dd></div>
          <div><dt>Sector</dt><dd>{detail.atlasSectorName ?? detail.atlasSector ?? '—'}</dd></div>
          <div><dt>Headquarters</dt><dd>{detail.hq.city ?? '—'}{detail.countryHq ? `, ${detail.countryHq}` : ''}</dd></div>
          <div><dt>Filings held</dt><dd className="num">{detail.documentCount}</dd></div>
          <div><dt>Cited dependencies</dt><dd className="num">{upN} out · {downN} in</dd></div>
          {/* Every venue, not just the primary. A reader checking a ticker
              against their broker needs the one they are looking at. */}
          <div className="wide"><dt>Listings</dt>
            <dd className="num">
              {detail.listings.length
                ? detail.listings.map(l => `${l.exchangeMic}:${l.ticker}`).join(' · ')
                : '—'}
            </dd></div>
          <div className="wide"><dt>Identifiers</dt>
            <dd className="num">{detail.identifiers.map(i => `${i.scheme} ${i.value}`).join(' · ') || '—'}</dd></div>
        </dl>

        <nav className="ctabs">
          <button aria-selected={tab === 'up'} onClick={() => setTab('up')}>
            <span className="tn num">01</span>
            Depends on <span className="n num">{upN}</span>
          </button>
          <button aria-selected={tab === 'down'} onClick={() => setTab('down')}>
            <span className="tn num">02</span>
            Depended on by <span className="n num">{downN}</span>
          </button>
          <button aria-selected={tab === 'market'} onClick={() => setTab('market')}>
            <span className="tn num">03</span>
            Chart &amp; news
          </button>
        </nav>
      </header>

      <div className="cpage-body">
        {tab === 'market' ? (
          tvSym
            ? <StockPanel symbol={tvSym} name={detail.commonName}
                          companyUid={detail.companyUid} />
            : <Empty title="No chart for this listing"
                     body={`We hold ${detail.listings.map(l => `${l.exchangeMic}:${l.ticker}`).join(', ') || 'no listing'} for this company, and none of those venues maps to a TradingView symbol we can address with confidence. A chart of the right ticker on the wrong exchange is a different company's price, so we show none.`} />
        ) : tab === 'up' ? (
          upN
            ? <EdgeList edges={detail.dependsOn} label="Depends on" />
            : <Empty title="No disclosed dependencies"
                     body="This company has not named a counterparty it depends on in any filing we hold. That is the normal case: a large buyer is never required to name its suppliers, which is the whole reason this graph is built from the suppliers' side." />
        ) : (
          downN
            ? <EdgeList edges={detail.dependedOnBy} label="Depended on by" />
            : <Empty title="Nobody has named this company"
                     body="No filing we hold discloses a dependency on this company. It may still be depended upon — only that nobody has had to say so in a document we have read." />
        )}
      </div>
    </div>
  )
}
