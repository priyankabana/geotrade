/** One company, full width.
 *
 *  This used to live in the 430px panel beside the globe, which was the wrong
 *  home for it twice over: a price chart squeezed into a third of a column is
 *  unreadable, and the globe answers "where in the world" - a question the
 *  reader has already finished asking by the time they are looking at one
 *  company's filings.
 */
import type { CompanyDetail } from '@shared/api'
import { EdgeList, Empty } from './Panels'
import StockPanel from './StockPanel'

type Tab = 'up' | 'down' | 'market'

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

        <dl className="cmeta">
          <div><dt>Legal name</dt><dd>{detail.legalName}</dd></div>
          <div><dt>Sector</dt><dd>{detail.atlasSectorName ?? detail.atlasSector ?? '—'}</dd></div>
          <div><dt>Headquarters</dt><dd>{detail.hq.city ?? '—'}{detail.countryHq ? `, ${detail.countryHq}` : ''}</dd></div>
          <div><dt>Filings held</dt><dd className="num">{detail.documentCount}</dd></div>
          <div><dt>Cited dependencies</dt><dd className="num">{upN} out · {downN} in</dd></div>
          <div className="wide"><dt>Identifiers</dt>
            <dd className="num">{detail.identifiers.map(i => `${i.scheme} ${i.value}`).join(' · ') || '—'}</dd></div>
        </dl>

        <nav className="ctabs">
          <button aria-selected={tab === 'up'} onClick={() => setTab('up')}>
            Depends on <span className="n num">{upN}</span>
          </button>
          <button aria-selected={tab === 'down'} onClick={() => setTab('down')}>
            Depended on by <span className="n num">{downN}</span>
          </button>
          <button aria-selected={tab === 'market'} onClick={() => setTab('market')}>
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
