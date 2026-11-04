import { useEffect, useMemo, useRef, useState } from 'react'
import { geoOrthographic, geoPath, geoGraticule10 } from 'd3-geo'
import { feature } from 'topojson-client'
import type { CountryTile } from '@shared/api'

/* Orthographic SVG rather than WebGL. DESIGN.md asks for an admiralty chart - fine
   hairlines, restrained, no glow - and SVG renders that honestly with no three.js.
   The globe's job is to answer "where is my exposure", so it plots the actual
   companies rather than being a decorative sphere. */

const NUM_TO_ISO2: Record<number, string> = {
  840:'US', 158:'TW', 356:'IN', 826:'GB', 276:'DE', 36:'AU', 124:'CA',
  392:'JP', 410:'KR', 156:'CN', 702:'SG', 458:'MY', 528:'NL', 764:'TH', 704:'VN',
  372:'IE', 756:'CH', 376:'IL', 76:'BR', 484:'MX', 250:'FR', 752:'SE', 344:'HK',
}
const RAD = Math.PI / 180

export type Point = { uid: string; name: string; sector: string; country: string; lat: number; lon: number }
export type Marker = { lat: number; lon: number; label: string }
export type Arc = { from: { lat: number; lon: number }; to: { lat: number; lon: number }; surprising: boolean }

type Geo = { type: 'Feature'; id?: string | number; properties: { name?: string }; geometry: unknown }

export default function Globe({
  tiles, points, selected, onSelect, focus, highlight, marker, arcs,
}: {
  tiles: CountryTile[]
  points: Point[]
  selected: string | null
  onSelect: (iso2: string | null) => void
  focus?: { lat: number; lon: number } | null
  highlight?: Set<string>
  marker?: Marker | null
  arcs?: Arc[]
}) {
  const [land, setLand] = useState<Geo[]>([])
  const [rot, setRot] = useState<[number, number]>([100, -12])
  const [size, setSize] = useState(620)
  const wrap = useRef<HTMLDivElement>(null)
  const drag = useRef<{ x: number; y: number; r: [number, number] } | null>(null)
  const anim = useRef<number | null>(null)

  useEffect(() => {
    let alive = true
    import('world-atlas/countries-110m.json').then(m => {
      const topo = (m as { default: unknown }).default ?? m
      const fc = feature(topo as never, (topo as never as { objects: { countries: never } }).objects.countries)
      if (alive) setLand((fc as unknown as { features: Geo[] }).features)
    }).catch(() => {})
    return () => { alive = false }
  }, [])

  useEffect(() => {
    const ro = new ResizeObserver(es => {
      const r = es[0].contentRect
      setSize(Math.max(260, Math.min(r.width, r.height) - 40))
    })
    if (wrap.current) ro.observe(wrap.current)
    return () => ro.disconnect()
  }, [])

  /* Rotate the globe to whatever the panel is talking about. Motion shows causality
     here - the map follows the question - rather than decorating. */
  useEffect(() => {
    if (!focus) return
    const target: [number, number] = [-focus.lon, -focus.lat]
    const from = rot
    let d = target[0] - from[0]
    while (d > 180) d -= 360
    while (d < -180) d += 360
    const t0 = performance.now(); const dur = 900
    const step = (t: number) => {
      const k = Math.min(1, (t - t0) / dur)
      const e = k < 0.5 ? 2 * k * k : 1 - Math.pow(-2 * k + 2, 2) / 2
      setRot([from[0] + d * e, from[1] + (target[1] - from[1]) * e])
      if (k < 1) anim.current = requestAnimationFrame(step)
    }
    anim.current = requestAnimationFrame(step)
    return () => { if (anim.current) cancelAnimationFrame(anim.current) }
  }, [focus?.lat, focus?.lon])

  const byIso = useMemo(() => new Map(tiles.map(t => [t.country, t])), [tiles])
  const projection = useMemo(
    () => geoOrthographic().rotate([rot[0], rot[1]]).fitExtent(
      [[10, 10], [size - 10, size - 10]], { type: 'Sphere' } as never),
    [rot, size])
  const path = useMemo(() => geoPath(projection), [projection])

  // Spherical cosine test: is this point on the hemisphere facing us?
  const centre = useMemo(() => ({ lon: -rot[0], lat: -rot[1] }), [rot])
  const visible = (lon: number, lat: number) =>
    Math.sin(centre.lat * RAD) * Math.sin(lat * RAD) +
    Math.cos(centre.lat * RAD) * Math.cos(lat * RAD) * Math.cos((lon - centre.lon) * RAD) > 0.02

  const plotted = useMemo(() => {
    const out: { p: Point; x: number; y: number; hot: boolean }[] = []
    for (const p of points) {
      if (!visible(p.lon, p.lat)) continue
      const xy = projection([p.lon, p.lat])
      if (!xy) continue
      out.push({ p, x: xy[0], y: xy[1], hot: !!highlight?.has(p.uid) })
    }
    return out
  }, [points, projection, highlight, rot])

  const markerXY = marker && visible(marker.lon, marker.lat) ? projection([marker.lon, marker.lat]) : null

  /* Great-circle arcs from the event to each company it reaches. geoPath interpolates
     a LineString along the sphere, so these curve correctly and clip at the horizon -
     which is the honest picture: some of what an event touches is over the edge. */
  const arcPaths = useMemo(() => (arcs ?? []).map((a, i) => ({
    i, surprising: a.surprising,
    d: path({ type: 'LineString',
              coordinates: [[a.from.lon, a.from.lat], [a.to.lon, a.to.lat]] } as never) ?? '',
  })).filter(a => a.d), [arcs, path])

  function fill(iso2: string | undefined) {
    const t = iso2 ? byIso.get(iso2) : undefined
    if (iso2 && iso2 === selected) return 'var(--land-sel)'
    if (t && t.companyCount > 0) return 'var(--land-has)'
    return 'var(--land)'
  }

  const onDown = (e: React.PointerEvent) => {
    drag.current = { x: e.clientX, y: e.clientY, r: rot }
    ;(e.target as Element).setPointerCapture?.(e.pointerId)
  }
  const onMove = (e: React.PointerEvent) => {
    const d = drag.current
    if (!d) return
    const k = 0.32
    setRot([d.r[0] + (e.clientX - d.x) * k,
            Math.max(-80, Math.min(80, d.r[1] - (e.clientY - d.y) * k))])
  }
  const onUp = () => { drag.current = null }

  return (
    <div className="globewrap" ref={wrap}>
      <svg width={size} height={size} role="img" aria-label="World map of coverage"
           onPointerDown={onDown} onPointerMove={onMove} onPointerUp={onUp} onPointerLeave={onUp}>
        <path className="sphere" d={path({ type: 'Sphere' } as never) ?? ''} />
        <path className="graticule" d={path(geoGraticule10()) ?? ''} />
        {land.map((f, i) => {
          const iso2 = NUM_TO_ISO2[Number(f.id)]
          const d = path(f as never)
          if (!d) return null
          return (
            <path key={i} d={d} className={`country${iso2 && iso2 === selected ? ' sel' : ''}`}
                  style={{ fill: fill(iso2) }}
                  onClick={() => iso2 && onSelect(iso2 === selected ? null : iso2)}>
              <title>{f.properties?.name ?? ''}{iso2 && byIso.get(iso2)
                ? ` — ${byIso.get(iso2)!.companyCount} companies`
                : ''}</title>
            </path>
          )
        })}

        {/* 1,958 company headquarters, straight from the database. */}
        <g className="pts">
          {plotted.map(({ p, x, y, hot }) => (
            <circle key={p.uid} cx={x} cy={y} r={hot ? 4 : 1.5}
                    className={hot ? 'pt hot' : 'pt'}>
              {hot && <title>{p.name}</title>}
            </circle>
          ))}
        </g>

        <g className="arcs">
          {arcPaths.map(a => (
            <path key={a.i} d={a.d} className={a.surprising ? 'arc surprising' : 'arc'} />
          ))}
        </g>

        {markerXY && (
          <g className="evt" transform={`translate(${markerXY[0]},${markerXY[1]})`}>
            <circle r="5" />
            <circle r="13" className="ring" />
            <circle r="21" className="ring r2" />
            <line x1="22" y1="-16" x2="46" y2="-34" />
            <text x="50" y="-34">{marker!.label}</text>
          </g>
        )}
      </svg>

      <div className="legend">
        <div><span className="dot" /> {points.length.toLocaleString()} company headquarters</div>
        <div><span className="dot hot" /> {highlight?.size ? `${highlight.size} in the panel` : 'selected'}</div>
        <div className="muted" style={{ marginTop: 4 }}>drag to rotate · click a country</div>
      </div>
    </div>
  )
}
