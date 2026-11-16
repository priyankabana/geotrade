/** Find a company by name or ticker.
 *
 *  Runs entirely against the points already loaded for the globe, so it needs
 *  no endpoint of its own and works identically against a live API and a
 *  published snapshot - which matters, because a snapshot is addressed by path
 *  and could not answer a search query at all.
 */
import { useEffect, useMemo, useRef, useState } from 'react'
import type { Pt } from './Globe3D'

const MAX = 8

/** Does `term` begin any word of `name`? */
function startsAWord(name: string, term: string): boolean {
  let i = name.indexOf(term)
  while (i > 0) {
    if (!/[a-z0-9]/.test(name[i - 1])) return true
    i = name.indexOf(term, i + 1)
  }
  return false
}

export default function Search({ points, onPick }: {
  points: Pt[]
  onPick: (uid: string) => void
}) {
  const [q, setQ] = useState('')
  const [open, setOpen] = useState(false)
  const [cursor, setCursor] = useState(0)
  const box = useRef<HTMLDivElement>(null)

  const hits = useMemo(() => {
    const term = q.trim().toLowerCase()
    if (term.length < 2) return []
    const scored: { p: Pt; rank: number }[] = []
    for (const p of points) {
      const name = p.name.toLowerCase()
      // The ticker is the part after the exchange prefix, which is what
      // somebody types when they type "NVDA" rather than "XNAS:NVDA".
      const ticker = (p.uid.split(':')[1] ?? '').toLowerCase()
      let rank = -1
      if (ticker === term || name === term) rank = 0
      else if (name.startsWith(term)) rank = 1
      else if (ticker.startsWith(term)) rank = 2
      // A later word in the name, so "digital" finds "Gen Digital". Matching
      // anywhere at all instead meant "nvi" returned Aeris Environmental,
      // because "environmental" contains those three letters in the middle of
      // a word - true, and useless.
      else if (startsAWord(name, term)) rank = 3
      if (rank >= 0) scored.push({ p, rank })
      if (scored.length > 400) break
    }
    scored.sort((a, b) => a.rank - b.rank || a.p.name.localeCompare(b.p.name))
    return scored.slice(0, MAX).map(s => s.p)
  }, [q, points])

  useEffect(() => { setCursor(0) }, [q])
  useEffect(() => {
    const away = (e: MouseEvent) => {
      if (box.current && !box.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', away)
    return () => document.removeEventListener('mousedown', away)
  }, [])

  const choose = (p: Pt) => { onPick(p.uid); setQ(''); setOpen(false) }

  return (
    <div className="search" ref={box}>
      <input
        value={q} placeholder="Search company or ticker"
        onChange={e => { setQ(e.target.value); setOpen(true) }}
        onFocus={() => setOpen(true)}
        onKeyDown={e => {
          if (e.key === 'ArrowDown') { e.preventDefault(); setCursor(c => Math.min(c + 1, hits.length - 1)) }
          else if (e.key === 'ArrowUp') { e.preventDefault(); setCursor(c => Math.max(c - 1, 0)) }
          else if (e.key === 'Enter' && hits[cursor]) choose(hits[cursor])
          else if (e.key === 'Escape') { setOpen(false); setQ('') }
        }}
      />
      {open && q.trim().length >= 2 && (
        <div className="search-drop">
          {hits.length === 0 ? (
            <div className="search-none">No company matches “{q.trim()}”</div>
          ) : hits.map((p, i) => (
            <button key={p.uid} aria-selected={i === cursor}
                    onMouseEnter={() => setCursor(i)} onClick={() => choose(p)}>
              <span className="s-name">{p.name}</span>
              <span className="s-uid num">{p.uid}</span>
              <span className="s-sec">{p.sector ?? ''}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
