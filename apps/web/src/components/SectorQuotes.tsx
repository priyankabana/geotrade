/** How the companies in this sector are trading right now.
 *
 *  Atlas has no price of its own and is not going to invent one: `docs/sources.md`
 *  has no cleared market-data row, and the API has always returned
 *  `changePct: null` rather than a number it could not stand behind.
 *
 *  So this does not compute a sector average - it shows the constituents and
 *  lets TradingView quote them. An average over a handful of names would also
 *  be the wrong statistic: these are the companies in the sector that carry
 *  evidence, not the sector's index membership, and calling their mean "the
 *  sector" would be a claim about a universe we are not holding.
 */
import { useMemo } from 'react'
import { TV, tvFromUid, useTheme } from './StockPanel'
import type { CompanyRow } from '@shared/api'

const MAX = 12

export default function SectorQuotes({ companies, sectorName }: {
  companies: CompanyRow[]
  sectorName: string
}) {
  const theme = useTheme()
  const symbols = useMemo(() => {
    const out: [string, string][] = []
    const seen = new Set<string>()
    for (const c of companies) {
      const sym = tvFromUid(c.companyUid)
      if (!sym || seen.has(sym)) continue
      seen.add(sym)
      out.push([sym, c.commonName])
      if (out.length >= MAX) break
    }
    return out
  }, [companies])

  if (symbols.length < 2) return null

  return (
    <div className="sector-quotes">
      {/* Clicking a row here leaves for TradingView, and that surprised a
          reader who reasonably expected our own company page. We cannot
          intercept a click inside a cross-origin iframe, and suppressing
          TradingView's links would breach the terms the free widget comes
          with - so the honest fix is to say where the rows go. The list
          underneath is ours and stays in the app. */}
      <h4>Today <span className="by">TradingView ↗</span></h4>
      <TV key={`q-${sectorName}-${theme}-${symbols.length}`} height={44 + symbols.length * 38}
          src="https://s3.tradingview.com/external-embedding/embed-widget-market-quotes.js"
          config={{
            colorTheme: theme, isTransparent: true, locale: 'en',
            width: '100%', height: 44 + symbols.length * 38, showSymbolLogo: false,
            symbolsGroups: [{ name: sectorName, symbols:
              symbols.map(([s, d]) => ({ name: s, displayName: d })) }],
          }} />
      <p className="quotes-note">Rows open TradingView. The list below stays here.</p>
    </div>
  )
}
