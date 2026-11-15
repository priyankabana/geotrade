import type { CSSProperties } from 'react'
import type { EventRow } from '../client'

/* Replay scrubber over real events in the database. The date shown is the date
   the world learned, which is the only date a graph read may use. */
export default function Timeline({ events, idx, onPick, earliestFiling }:
  { events: EventRow[]; idx: number; onPick: (i: number) => void
    earliestFiling?: string | null }) {
  if (events.length < 2) return null
  const ts = events.map(e => new Date(e.becamePublicUtc).getTime())
  const t0 = Math.min(...ts), t1 = Math.max(...ts)
  const pos = (t: string) => ((new Date(t).getTime() - t0) / (t1 - t0 || 1)) * 100
  const cur = events[idx]

  /* The point-in-time boundary, drawn rather than described. No filing we hold
     was published before this date, so any event to the left of it can reach
     nobody - not because the data is missing but because using it would be
     look-ahead. Showing the line is the difference between a demo that looks
     broken and one that is making a point. */
  const boundary = earliestFiling
    ? Math.max(0, Math.min(100, pos(earliestFiling)))
    : null
  const beforeBoundary = boundary !== null && pos(cur.becamePublicUtc) < boundary

  return (
    <div className="timeline">
      <div className="tl-head">
        <span className="tl-title">Replay</span>
        <span className="tl-sub">{cur.name}</span>
        <span className="tl-asof num">graph as of {cur.becamePublicUtc.slice(0, 10)}</span>
        {beforeBoundary && (
          <span className="tl-warn">before our first filing — the graph is empty here</span>
        )}
      </div>
      <div className="tl-track">
        <div className="tl-line" />
        {boundary !== null && (
          <>
            <div className="tl-void" style={{ width: `${boundary}%` }}
                 title="No filing we hold was published before this date, so the graph is empty here." />
            <div className="tl-boundary" style={{ left: `${boundary}%` }}
                 title={`First filing we hold: ${earliestFiling!.slice(0, 10)}`}>
              <span className="tl-boundary-label num">
                first filing {earliestFiling!.slice(0, 10)}
              </span>
            </div>
          </>
        )}
        <div className="tl-fill" style={{ width: `${pos(cur.becamePublicUtc)}%` }} />
        {events.map((e, i) => {
          const yr = e.becamePublicUtc.slice(0, 4)
          const first = events.findIndex(x => x.becamePublicUtc.slice(0, 4) === yr) === i
          return (
            <button key={e.eventId} className={`tl-pip${i === idx ? ' on' : ''}`}
                    style={{ left: `${pos(e.becamePublicUtc)}%` } as CSSProperties}
                    onClick={() => onPick(i)}
                    title={`${e.becamePublicUtc.slice(0, 10)} — ${e.name} · ${e.totalExposed} exposed`}>
              <span className="tl-dot" />
              <span className="tl-year num">{first || i === idx ? yr : ''}</span>
            </button>
          )
        })}
      </div>
    </div>
  )
}
