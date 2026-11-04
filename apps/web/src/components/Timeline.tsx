import type { CSSProperties } from 'react'
import { TIMELINE } from '../example'

/* Replay scrubber. The point-in-time boundary is drawn on it, because the single
   most important property of a backtest is that it cannot see past that line. */
export default function Timeline({ idx, onPick }: { idx: number; onPick: (i: number) => void }) {
  const t0 = new Date(TIMELINE[0].t).getTime()
  const t1 = new Date(TIMELINE[TIMELINE.length - 1].t).getTime()
  const pos = (t: string) => ((new Date(t).getTime() - t0) / (t1 - t0)) * 100

  return (
    <div className="timeline">
      <div className="tl-head">
        <span className="tl-title">Replay</span>
        <span className="tl-sub">{TIMELINE[idx].label}</span>
        <span className="tl-asof num">graph as of {TIMELINE[idx].t}</span>
      </div>
      <div className="tl-track">
        <div className="tl-line" />
        <div className="tl-fill" style={{ width: `${pos(TIMELINE[idx].t)}%` }} />
        {TIMELINE.map((e, i) => {
          // 2021 carries three events weeks apart; printing the year three times
          // just produces mush, so only the first of a year is labelled.
          const first = TIMELINE.findIndex(x => x.t.slice(0, 4) === e.t.slice(0, 4)) === i
          return (
            <button key={e.t} className={`tl-pip${i === idx ? ' on' : ''}`}
                    style={{ left: `${pos(e.t)}%` } as CSSProperties}
                    onClick={() => onPick(i)} title={`${e.t} — ${e.label}`}>
              <span className="tl-dot" />
              <span className="tl-year num">{first || i === idx ? e.t.slice(0, 4) : ''}</span>
            </button>
          )
        })}
      </div>
    </div>
  )
}
