import { useEffect, useMemo, useRef, useState } from 'react'
import Globe, { type GlobeMethods } from 'react-globe.gl'
import { feature } from 'topojson-client'

/* A vector globe, not a textured one. Countries are drawn as polygons from the same
   world-atlas data the 2D view uses, so there is no photographic earth texture to
   license and the whole thing stays on the nautical-chart palette.

   Nothing here is derived from the captured third-party site in ../reference - see
   reference/DO-NOT-SHIP.md. The idea that a globe is the right primary view is theirs;
   the implementation, palette and interaction model are ours. */

export type Pt = { uid: string; name: string; sector: string; country: string; lat: number; lon: number }
export type ArcSpec = { startLat: number; startLng: number; endLat: number; endLng: number; surprising: boolean }
export type RingSpec = { lat: number; lng: number }

type Poly = { properties: { name?: string }; id?: string | number }

const NUM_TO_ISO2: Record<number, string> = {
  840:'US',158:'TW',356:'IN',826:'GB',276:'DE',36:'AU',124:'CA',392:'JP',410:'KR',
  156:'CN',702:'SG',458:'MY',528:'NL',764:'TH',704:'VN',372:'IE',756:'CH',376:'IL',
  76:'BR',484:'MX',250:'FR',752:'SE',344:'HK',710:'ZA',554:'NZ',620:'PT',724:'ES',
  380:'IT',616:'PL',578:'NO',208:'DK',246:'FI',40:'AT',56:'BE',792:'TR',682:'SA',784:'AE',
}

export default function Globe3D({
  points, selected, onSelectCountry, focus, highlight, arcs, rings, mode,
}: {
  points: Pt[]
  selected: string | null
  onSelectCountry: (iso2: string | null) => void
  focus?: { lat: number; lon: number; altitude?: number } | null
  highlight?: Set<string>
  arcs?: ArcSpec[]
  rings?: RingSpec[]
  mode: 'coverage' | 'detail'
}) {
  const ref = useRef<GlobeMethods | undefined>(undefined)
  const wrap = useRef<HTMLDivElement>(null)
  const [polys, setPolys] = useState<Poly[]>([])
  const [dim, setDim] = useState({ w: 900, h: 900 })
  const [ready, setReady] = useState(false)

  useEffect(() => {
    import('world-atlas/countries-110m.json').then(m => {
      const topo = (m as { default: unknown }).default ?? m
      const fc = feature(topo as never, (topo as never as { objects: { countries: never } }).objects.countries)
      setPolys((fc as unknown as { features: Poly[] }).features)
    }).catch(() => {})
  }, [])

  useEffect(() => {
    const ro = new ResizeObserver(es => {
      const r = es[0].contentRect
      setDim({ w: Math.max(320, r.width), h: Math.max(320, r.height) })
    })
    if (wrap.current) ro.observe(wrap.current)
    return () => ro.disconnect()
  }, [])

  useEffect(() => {
    const g = ref.current
    if (!g) return
    const c = g.controls() as { autoRotate: boolean; autoRotateSpeed: number; enableZoom: boolean }
    c.autoRotate = true
    c.autoRotateSpeed = 0.18     // slow enough to read, fast enough to look alive
    c.enableZoom = true
    g.pointOfView({ lat: 24, lng: -20, altitude: 2.05 }, 0)
    setReady(true)
  }, [])

  useEffect(() => {
    const g = ref.current
    if (!g || !focus) return
    const c = g.controls() as { autoRotate: boolean }
    c.autoRotate = false
    g.pointOfView({ lat: focus.lat, lng: focus.lon, altitude: focus.altitude ?? 1.9 }, 1400)
  }, [focus?.lat, focus?.lon, focus?.altitude])

  const hexPoints = useMemo(
    () => points.map(p => ({ lat: p.lat, lng: p.lon, uid: p.uid })), [points])

  const litPoints = useMemo(() => {
    if (!highlight?.size) return []
    return points.filter(p => highlight.has(p.uid))
      .map(p => ({ lat: p.lat, lng: p.lon, name: p.name, uid: p.uid }))
  }, [points, highlight])

  function ramp(n: number) {
    const t = Math.min(1, Math.log1p(n) / Math.log1p(90))
    const a = Math.round(90 + t * 150).toString(16).padStart(2, '0')
    return `${getComputedStyle(document.documentElement)
      .getPropertyValue(t > 0.55 ? '--hex-hot' : '--hex-top').trim() || '#3f8fa6'}${a}`
  }

  const css = (v: string) =>
    getComputedStyle(document.documentElement).getPropertyValue(v).trim() || '#888'


  /* Stop the idle spin the moment someone touches the globe. A target that drifts
     out from under the cursor is not a feature. */
  const stopSpin = () => {
    const g = ref.current
    if (g) (g.controls() as { autoRotate: boolean }).autoRotate = false
  }

  return (
    <div className="globe3d" ref={wrap} onPointerDown={stopSpin} onWheel={stopSpin}>
      <Globe
        ref={ref as never}
        width={dim.w}
        height={dim.h}
        /* NASA night-earth + topology bump + starfield, the standard three-globe
           example assets (MIT package, public-domain imagery). Copied from our own
           node_modules, never from ../reference - see public/textures/SOURCE.md. */
        globeImageUrl="/textures/earth-night.jpg"
        bumpImageUrl="/textures/earth-topology.png"
        backgroundImageUrl="/textures/night-sky.png"
        showGlobe
        showAtmosphere
        atmosphereColor={css('--atmo')}
        atmosphereAltitude={0.16}

        polygonsData={polys}
        polygonAltitude={(d: object) =>
          NUM_TO_ISO2[Number((d as Poly).id)] === selected ? 0.012 : 0.004}
        polygonCapColor={(d: object) =>
          NUM_TO_ISO2[Number((d as Poly).id)] === selected
            ? 'rgba(201,139,58,0.34)' : 'rgba(0,0,0,0)'}
        polygonSideColor={() => 'rgba(201,139,58,0.14)'}
        polygonStrokeColor={() => css('--coast')}
        onPolygonClick={(d: object) => {
          const iso = NUM_TO_ISO2[Number((d as Poly).id)]
          if (iso) onSelectCountry(iso === selected ? null : iso)
        }}
        polygonLabel={(d: object) => `<div class="g-tip">${(d as Poly).properties?.name ?? ''}</div>`}

        /* 23,000 headquarters. Binned, because 23,000 individual meshes is a slideshow
           and because density is the thing worth seeing at this zoom. */
        hexBinPointsData={mode === 'coverage' ? hexPoints : []}
        hexBinPointLat={(d: object) => (d as { lat: number }).lat}
        hexBinPointLng={(d: object) => (d as { lng: number }).lng}
        hexBinResolution={4}
        hexMargin={0.18}
        hexAltitude={(d: object) =>
          Math.min(0.085, Math.sqrt((d as { points: unknown[] }).points.length) * 0.0045)}
        /* Colour carries the density; height only hints at it. Tall spikes read as
           decoration and hide the map underneath. */
        hexTopColor={(d: object) => ramp((d as { points: unknown[] }).points.length)}
        hexSideColor={(d: object) => ramp((d as { points: unknown[] }).points.length)}
        hexLabel={(d: object) =>
          `<div class="g-tip"><b>${(d as { points: unknown[] }).points.length}</b> companies</div>`}

        pointsData={litPoints}
        pointLat="lat" pointLng="lng"
        pointColor={() => css('--pt-hot')}
        pointAltitude={0.014}
        pointRadius={0.5}
        pointLabel={(d: object) => `<div class="g-tip">${(d as { name: string }).name}</div>`}

        arcsData={arcs ?? []}
        arcStartLat="startLat" arcStartLng="startLng" arcEndLat="endLat" arcEndLng="endLng"
        arcColor={(d: object) => {
          const c = (d as ArcSpec).surprising ? css('--arc-hot') : css('--arc-dim')
          return [`${c}00`, c, `${c}00`]
        }}
        arcAltitudeAutoScale={0.26}
        arcStroke={(d: object) => ((d as ArcSpec).surprising ? 0.8 : 0.45)}
        arcDashLength={0.45}
        arcDashGap={0.18}
        arcDashAnimateTime={2600}

        ringsData={rings ?? []}
        ringLat="lat" ringLng="lng"
        ringColor={() => (t: number) => {
          const c = css('--ring')
          const a = Math.round((1 - t) * 235).toString(16).padStart(2, '0')
          return `${c}${a}`
        }}
        ringMaxRadius={9}
        ringPropagationSpeed={2.8}
        ringRepeatPeriod={900}
      />
      {!ready && <div className="globe-loading">drawing the world…</div>}
    </div>
  )
}
