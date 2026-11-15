import type { CSSProperties } from 'react'
import type { EventRow } from '../client'

/* Replay scrubber over real events in the database. The date shown is the date
   the world learned, which is the only date a graph read may use. */
export default function Timeline({ events, idx, onPick }:
  { events: EventRow[]; idx: number; onPick: (i: number) => void }) {
  if (events.length < 2) return null
  const ts = events.map(e => new Date(e.becamePublicUtc).getTime())
  const t0 = Math.min(...ts), t1 = Math.max(...ts)
  const pos = (t: string) => ((new Date(t).getTime() - t0) / (t1 - t0 || 1)) * 100
  const cur = events[idx]

  return (
    <div className="timeline">
      <div className="tl-head">
        <span className="tl-title">Replay</span>
        <span className="tl-sub">{cur.name}</span>
        <span className="tl-asof num">graph as of {cur.becamePublicUtc.slice(0, 10)}</span>
      </div>
      <div className="tl-track">
        <div className="tl-line" />
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
