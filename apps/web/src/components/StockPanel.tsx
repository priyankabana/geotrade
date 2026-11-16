/** Market view for one company: chart, fundamentals, news, and a technical read.
 *
 *  These are TradingView's embedded widgets, and that is a deliberate choice
 *  rather than a shortcut. A price chart, a P/E and a technical rating are
 *  commodity data that somebody else already computes correctly and is
 *  licensed to display; re-deriving them from a scraped feed would be worse
 *  data wearing our name.
 *
 *  It also keeps the line this project draws in the right place. TradingView's
 *  gauge says BUY or SELL and is clearly theirs, computed from price action.
 *  Atlas's own panel beside it says who depends on whom and shows the filed
 *  sentence. Two different claims, two different authorities, neither
 *  borrowing credibility from the other.
 */
import { useEffect, useRef, useState } from 'react'

/** Which theme the page is actually painted in.
 *
 *  The widgets are iframes from another origin, so they cannot read our CSS
 *  variables and will not inherit anything. Hard-coding them light put four
 *  white slabs in the middle of a dark page. This reads the same two signals
 *  the stylesheet does - an explicit data-theme, else the OS preference - and
 *  keeps listening, because a reader can change it while the page is open. */
export function useTheme(): 'light' | 'dark' {
  const read = (): 'light' | 'dark' => {
    if (typeof document === 'undefined') return 'light'
    const forced = document.documentElement.getAttribute('data-theme')
    if (forced === 'dark' || forced === 'light') return forced
    return window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
  }
  const [theme, setTheme] = useState<'light' | 'dark'>(read)
  useEffect(() => {
    const mq = window.matchMedia?.('(prefers-color-scheme: dark)')
    const sync = () => setTheme(read())
    mq?.addEventListener('change', sync)
    const obs = new MutationObserver(sync)
    obs.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] })
    return () => { mq?.removeEventListener('change', sync); obs.disconnect() }
  }, [])
  return theme
}

/** ISO 10383 MIC, which is what our listings carry, to the exchange prefix
 *  TradingView addresses symbols by. An exchange we have no mapping for gets
 *  no widget rather than a wrong one: a chart of the right ticker on the wrong
 *  exchange is a different company's price. */
const TV_EXCHANGE: Record<string, string> = {
  XNAS: 'NASDAQ', XNGS: 'NASDAQ', XNCM: 'NASDAQ', XNMS: 'NASDAQ',
  XNYS: 'NYSE', ARCX: 'AMEX', XASE: 'AMEX', BATS: 'AMEX',
  XLON: 'LSE', XETR: 'XETR', XFRA: 'FWB', XPAR: 'EURONEXT',
  XAMS: 'EURONEXT', XBRU: 'EURONEXT', XLIS: 'EURONEXT',
  XSWX: 'SIX', XVTX: 'SIX', XMIL: 'MIL', XMAD: 'BME', XWBO: 'VIE',
  XSTO: 'OMXSTO', XCSE: 'OMXCOP', XHEL: 'OMXHEX', XOSL: 'OSL',
  XTSE: 'TSX', XTSX: 'TSXV', XASX: 'ASX', XNZE: 'NZX',
  XTKS: 'TSE', XHKG: 'HKEX', XSES: 'SGX', XKRX: 'KRX', XTAI: 'TWSE',
  XNSE: 'NSE', XBOM: 'BSE', XBSP: 'BMFBOVESPA', XMEX: 'BMV',
  XJSE: 'JSE', XTAE: 'TASE', XIST: 'BIST', XWAR: 'GPW',
}

export function tvSymbol(listings: { exchangeMic: string; ticker: string; isPrimary: boolean }[]) {
  const sorted = [...listings].sort((a, b) => Number(b.isPrimary) - Number(a.isPrimary))
  for (const l of sorted) {
    const ex = TV_EXCHANGE[(l.exchangeMic || '').toUpperCase()]
    if (ex && l.ticker) return `${ex}:${l.ticker.replace(/[^A-Za-z0-9.]/g, '')}`
  }
  return null
}

/** TradingView's widgets are injected by a script tag that reads its own JSON
 *  body, which does not fit React's model at all - so the container is managed
 *  by hand and torn down completely on every change. Reusing the node leaves
 *  the previous company's chart underneath the new one. */
function TV({ src, config, height }: { src: string; config: object; height: number }) {
  const host = useRef<HTMLDivElement>(null)
  const json = JSON.stringify(config)
  useEffect(() => {
    const el = host.current
    if (!el || el.childElementCount) return
    const mount = document.createElement('div')
    mount.className = 'tradingview-widget-container__widget'
    el.appendChild(mount)
    const script = document.createElement('script')
    script.src = src
    script.async = true
    script.innerHTML = json
    el.appendChild(script)
    // Deliberately no teardown. Clearing the container here threw
    // "Cannot read properties of null (reading 'querySelector')" out of
    // TradingView's own script: it finishes loading after the effect has
    // already emptied the node it was handed. The `key` below gives React a
    // different element whenever the symbol changes, so the stale widget is
    // unmounted as a whole subtree and the script is never left holding a
    // container we gutted underneath it.
  }, [src, json])
  return <div className="tradingview-widget-container" ref={host} style={{ height }} />
}

const BASE = { isTransparent: true, locale: 'en' }

export default function StockPanel({ symbol, name }: { symbol: string; name: string }) {
  const theme = useTheme()
  // Every widget is keyed on the theme as well as the symbol, so a change
  // rebuilds the iframe instead of leaving the old palette in place.
  const base = { ...BASE, colorTheme: theme }
  return (
    <div className="stock">
      <div className="stock-grid">
        <section className="tv-chart">
          <h4>Price</h4>
          <TV key={`chart-${symbol}-${theme}`} height={420}
              src="https://s3.tradingview.com/external-embedding/embed-widget-advanced-chart.js"
              /* autosize needs a parent with a resolved height; inside a
                 flex column it resolved to about 150px and left most of the
                 box empty. An explicit height is what the widget honours. */
              config={{ ...base, symbol, width: '100%', height: 420, interval: 'D',
                        timezone: 'Etc/UTC', style: '2', hide_side_toolbar: true,
                        allow_symbol_change: false, save_image: false }} />
        </section>

        <section className="tv-side">
          <h4>Technical rating <span className="by">TradingView</span></h4>
          <TV key={`ta-${symbol}-${theme}`} height={400}
              src="https://s3.tradingview.com/external-embedding/embed-widget-technical-analysis.js"
              config={{ ...base, symbol, interval: '1D', width: '100%', height: 400,
                        showIntervalTabs: true, displayMode: 'single' }} />
        </section>
      </div>

      <div className="stock-grid">
        <section>
          <h4>Fundamentals <span className="by">TradingView</span></h4>
          <TV key={`fin-${symbol}-${theme}`} height={400}
              src="https://s3.tradingview.com/external-embedding/embed-widget-financials.js"
              config={{ ...base, symbol, displayMode: 'regular', width: '100%',
                        height: 400, largeChartUrl: '' }} />
        </section>
        <section>
          <h4>News <span className="by">TradingView</span></h4>
          <TV key={`news-${symbol}-${theme}`} height={400}
              src="https://s3.tradingview.com/external-embedding/embed-widget-timeline.js"
              config={{ ...base, feedMode: 'symbol', symbol, displayMode: 'regular',
                        width: '100%', height: 400 }} />
        </section>
      </div>

      <p className="disclaimer">
        Market data by{' '}
        <a href={`https://www.tradingview.com/symbols/${symbol.replace(':', '-')}/`}
           target="_blank" rel="noreferrer">TradingView</a>. Not investment advice.
      </p>
    </div>
  )
}
