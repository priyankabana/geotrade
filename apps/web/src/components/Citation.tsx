import type { Citation as C } from '@shared/api'

/* The citation is a first-class object, not a tooltip. If we cannot cite it,
   we do not assert it - so this component renders everywhere a claim appears. */
export default function Citation({ c }: { c: C }) {
  return (
    <div className="cite">
      <q>{c.quote}</q>
      <div className="meta">
        <span>{c.filerName}</span>
        <span>{c.docType}{c.sectionLabel ? ` · ${c.sectionLabel}` : ''}</span>
        <span className="num">filed {c.filedAtUtc.slice(0, 10)}</span>
        <a href={c.sourceUrl} target="_blank" rel="noreferrer">source ↗</a>
      </div>
    </div>
  )
}
