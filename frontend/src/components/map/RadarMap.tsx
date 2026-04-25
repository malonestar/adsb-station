import { DeckGL } from '@deck.gl/react'
import { WebMercatorViewport } from '@deck.gl/core'
import { TileLayer } from '@deck.gl/geo-layers'
import { BitmapLayer, PathLayer, ScatterplotLayer, TextLayer } from '@deck.gl/layers'
import { HeatmapLayer } from '@deck.gl/aggregation-layers'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useShallow } from 'zustand/react/shallow'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { clsx } from 'clsx'

import { useAircraft, selectAircraftWithPosition } from '@/store/aircraft'
import { useSelection } from '@/store/selection'
import { useSettings } from '@/store/settings'
import { useHistory, windowToHours, type HeatmapWindow } from '@/store/history'
import { altitudeColor } from '@/lib/format'
import { ringPolygon } from '@/lib/geo'
import { api } from '@/lib/api'
import { iconSizeForCategory } from './getAircraftIcon'
import { AircraftMarkers } from './AircraftMarkers'
import type { AircraftState } from '@/types/api'

const MIN_ZOOM = 4
const MAX_ZOOM = 14
const INITIAL_ZOOM = 7.5

interface ViewState {
  longitude: number
  latitude: number
  zoom: number
  pitch: number
  bearing: number
  maxZoom: number
  minZoom: number
}

interface Props {
  station: { lat: number; lon: number }
  /** Pixels to push the top-right zoom controls to the left.
   *  Use this when an overlay drawer (e.g., kiosk detail panel) covers the right edge. */
  rightControlsOffset?: number
  /** When true, hide the right-side map controls (zoom, etc) off-screen. */
  hideRightControls?: boolean
}

export function RadarMap({
  station,
  rightControlsOffset = 0,
  hideRightControls = false,
}: Props): React.ReactElement {
  const aircraft = useAircraft(useShallow(selectAircraftWithPosition))
  const selectedHex = useSelection((s) => s.selectedHex)
  const select = useSelection((s) => s.select)
  const pendingFocusHex = useSelection((s) => s.pendingFocusHex)
  const consumeFocus = useSelection((s) => s.consumeFocus)
  const followSelection = useSelection((s) => s.followSelection)
  const focusTarget = useAircraft((s) =>
    pendingFocusHex ? s.byHex[pendingFocusHex] : null,
  )
  // The currently-selected aircraft's live position — drives the TRACK
  // follow loop. Subscribed via lat/lon scalars (not the whole record) so
  // we re-render only when the position actually moves.
  const followLat = useAircraft((s) =>
    followSelection && selectedHex ? s.byHex[selectedHex]?.lat : null,
  )
  const followLon = useAircraft((s) =>
    followSelection && selectedHex ? s.byHex[selectedHex]?.lon : null,
  )
  const rangeRingsOn = useSettings((s) => s.rangeRingsOn)
  const sweepOn = useSettings((s) => s.sweepOn)
  const scanlinesOn = useSettings((s) => s.scanlinesOn)

  // History-UI layer state (heatmap / all-trails / per-aircraft full history)
  const heatmapOn = useHistory((s) => s.heatmapOn)
  const heatmapWindow = useHistory((s) => s.heatmapWindow)
  const setHeatmapOn = useHistory((s) => s.setHeatmapOn)
  const setHeatmapWindow = useHistory((s) => s.setHeatmapWindow)
  const allTrailsOn = useHistory((s) => s.allTrailsOn)
  const setAllTrailsOn = useHistory((s) => s.setAllTrailsOn)
  const historyHex = useHistory((s) => s.historyHex)

  // Selected aircraft's 5-min trail — shares TanStack Query cache with AircraftDetail
  // (same queryKey), so no duplicate fetch.
  const { data: selectedDetail } = useQuery({
    queryKey: ['aircraft', selectedHex],
    queryFn: () =>
      selectedHex ? api.aircraftDetail(selectedHex) : Promise.resolve(null),
    enabled: Boolean(selectedHex),
    staleTime: 30_000,
  })

  // Heatmap query + prefetching. Backend aggregations over the positions table
  // can take 15-20s for 7d/ALL windows on cold fetch; the backend has a 5-min
  // TTL cache for repeat requests. Match staleTime to that TTL so TanStack
  // Query doesn't refetch inside the cache window, and bump gcTime so switching
  // away from the heatmap chip (or toggling off) keeps the data warm.
  const queryClient = useQueryClient()
  const { data: heatmapData } = useQuery({
    queryKey: ['heatmap', heatmapWindow],
    queryFn: () => api.heatmap(windowToHours(heatmapWindow)),
    enabled: heatmapOn,
    staleTime: 5 * 60_000,
    gcTime: 30 * 60_000,
    retry: 1,
    refetchOnWindowFocus: false,
  })

  // When the heatmap toggles on, warm the cache for all 4 windows in the
  // background. The user's current window fetches foreground through useQuery;
  // the other 3 prefetch in parallel so later chip clicks are instant. They
  // share a single SQLite-backed endpoint (sequentialized at the backend), but
  // they fire off before the user can even click another chip.
  useEffect(() => {
    if (!heatmapOn) return
    const windows: HeatmapWindow[] = ['1h', '24h', '7d', 'all']
    for (const w of windows) {
      void queryClient.prefetchQuery({
        queryKey: ['heatmap', w],
        queryFn: () => api.heatmap(windowToHours(w)),
        staleTime: 5 * 60_000,
      })
    }
  }, [heatmapOn, queryClient])

  const { data: allTrails } = useQuery({
    queryKey: ['all-trails'],
    queryFn: () => api.aircraftTrails(300),
    enabled: allTrailsOn,
    refetchInterval: allTrailsOn ? 15_000 : false,
    staleTime: 10_000,
  })

  const { data: historyReplay } = useQuery({
    queryKey: ['history-trail', historyHex],
    queryFn: async () => {
      if (!historyHex) return null
      const end = new Date()
      const start = new Date(end.getTime() - 30 * 24 * 60 * 60 * 1000)
      return api.replay(start.toISOString(), end.toISOString(), historyHex)
    },
    enabled: Boolean(historyHex),
    staleTime: 30_000,
  })

  // Auto-trail: last 5 min of positions for the selected aircraft.
  // Backend /api/aircraft/:hex already returns `trail` as [{ts, lat, lon, ...}] so
  // we just project to deck.gl's [lon, lat] pair format.
  const selectedTrail = useMemo<[number, number][]>(() => {
    const d = selectedDetail as { trail?: Array<{ lat: number; lon: number }> } | null
    if (!d?.trail || d.trail.length < 2) return []
    return d.trail.map((p) => [p.lon, p.lat])
  }, [selectedDetail])

  // Break a single aircraft's full history into visual segments — any gap > 10 min
  // between consecutive points becomes a segment break, so separate passes don't
  // stitch into a bogus straight line through the station.
  const historySegments = useMemo<[number, number][][]>(() => {
    const pts = historyReplay?.rows ?? []
    if (pts.length < 2) return []
    const GAP_MS = 10 * 60 * 1000
    const segs: [number, number][][] = []
    let cur: [number, number][] = [[pts[0].lon, pts[0].lat]]
    for (let i = 1; i < pts.length; i++) {
      const dt = new Date(pts[i].ts).getTime() - new Date(pts[i - 1].ts).getTime()
      if (dt > GAP_MS) {
        if (cur.length >= 2) segs.push(cur)
        cur = [[pts[i].lon, pts[i].lat]]
      } else {
        cur.push([pts[i].lon, pts[i].lat])
      }
    }
    if (cur.length >= 2) segs.push(cur)
    return segs
  }, [historyReplay])

  const [viewState, setViewState] = useState<ViewState>({
    longitude: station.lon,
    latitude: station.lat,
    zoom: INITIAL_ZOOM,
    pitch: 0,
    bearing: 0,
    maxZoom: MAX_ZOOM,
    minZoom: MIN_ZOOM,
  })

  const zoomIn = useCallback(
    () =>
      setViewState((v) => ({
        ...v,
        zoom: Math.min(MAX_ZOOM, Math.round((v.zoom + 1) * 10) / 10),
      })),
    [],
  )
  const zoomOut = useCallback(
    () =>
      setViewState((v) => ({
        ...v,
        zoom: Math.max(MIN_ZOOM, Math.round((v.zoom - 1) * 10) / 10),
      })),
    [],
  )
  // Catalog / Watchlist routes set pendingFocusHex when navigating into the
  // dashboard so the radar can pan to the aircraft. Only fires once the
  // aircraft is actually present in the live registry — if it never shows
  // up (offline), the flag stays pending until something else clears it.
  useEffect(() => {
    if (!pendingFocusHex || focusTarget?.lat == null || focusTarget?.lon == null) return
    setViewState((v) => ({
      ...v,
      latitude: focusTarget.lat as number,
      longitude: focusTarget.lon as number,
      zoom: Math.max(v.zoom, 9),
    }))
    consumeFocus()
  }, [pendingFocusHex, focusTarget, consumeFocus])

  // TRACK button: keep the map centered on the selected aircraft as it moves.
  // Pans (no zoom override) on every lat/lon change. Manual pan/zoom while
  // following will snap back next tick — that's the documented contract;
  // turn off TRACK to inspect freely.
  useEffect(() => {
    if (!followSelection || followLat == null || followLon == null) return
    setViewState((v) => ({
      ...v,
      latitude: followLat,
      longitude: followLon,
    }))
  }, [followSelection, followLat, followLon])

  const recenter = useCallback(
    () =>
      setViewState({
        longitude: station.lon,
        latitude: station.lat,
        zoom: INITIAL_ZOOM,
        pitch: 0,
        bearing: 0,
        maxZoom: MAX_ZOOM,
        minZoom: MIN_ZOOM,
      }),
    [station.lat, station.lon],
  )

  // Track container pixel dimensions so we can project the station to screen coords
  const containerRef = useRef<HTMLDivElement | null>(null)
  const [containerSize, setContainerSize] = useState<{ w: number; h: number }>({ w: 0, h: 0 })
  useEffect(() => {
    if (!containerRef.current) return
    const el = containerRef.current
    const update = () => setContainerSize({ w: el.clientWidth, h: el.clientHeight })
    update()
    const ro = new ResizeObserver(update)
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  // Shared viewport — reused by the station pixel projection and the HTML aircraft overlay.
  const viewport = useMemo(() => {
    if (!containerSize.w || !containerSize.h) return null
    try {
      return new WebMercatorViewport({
        ...viewState,
        width: containerSize.w,
        height: containerSize.h,
      })
    } catch {
      return null
    }
  }, [viewState, containerSize])

  // Project the station's lat/lon to pixel coords in the container. Used to
  // anchor the radar sweep + scanlines to the antenna instead of the viewport center.
  const stationPixel = useMemo(() => {
    if (!viewport) return null
    const [x, y] = viewport.project([station.lon, station.lat])
    return { x, y }
  }, [viewport, station.lat, station.lon])

  // Whether the user is actively panning/zooming the map. Used to disable CSS transitions
  // on the HTML aircraft markers so they stay glued to the map during interaction instead
  // of lagging behind the basemap.
  const [interacting, setInteracting] = useState(false)

  const layers = useMemo(() => {
    const out: unknown[] = []

    // ─── Basemap ────────────────────────────────────────────────────
    // Raster tile basemap. Swap BASEMAP_VARIANT below to taste:
    //   "dark_all"      — dark muted, default
    //   "dark_nolabels" — dark muted, no city/road labels (cleaner radar)
    //   "voyager"       — mid-tone neutral, good contrast, readable
    //   "positron"      — bright white/light (not recommended for radar feel)
    // Whitelist `basemaps.cartocdn.com` in Pi-hole if tiles fail to load.
    const BASEMAP_VARIANT = 'dark_all'
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    out.push(
      new TileLayer({
        id: 'basemap',
        data: [
          `https://a.basemaps.cartocdn.com/${BASEMAP_VARIANT}/{z}/{x}/{y}@2x.png`,
          `https://b.basemaps.cartocdn.com/${BASEMAP_VARIANT}/{z}/{x}/{y}@2x.png`,
          `https://c.basemaps.cartocdn.com/${BASEMAP_VARIANT}/{z}/{x}/{y}@2x.png`,
          `https://d.basemaps.cartocdn.com/${BASEMAP_VARIANT}/{z}/{x}/{y}@2x.png`,
        ],
        minZoom: 0,
        maxZoom: 19,
        tileSize: 256,
        // deck.gl's TileLayer sublayer types are tricky; use any and cast.
        renderSubLayers: (props: any) => {
          const [[west, south], [east, north]] = props.tile.boundingBox
          return new BitmapLayer(props, {
            data: undefined,
            image: props.data,
            bounds: [west, south, east, north],
            opacity: 1.0,
          })
        },
      }),
    )

    // ─── Coverage heatmap (below range rings + station markers) ─────────
    if (heatmapOn && heatmapData?.bins?.length) {
      out.push(
        new HeatmapLayer({
          id: 'coverage-heatmap',
          data: heatmapData.bins,
          getPosition: (d: { lat: number; lon: number }) => [d.lon, d.lat],
          // Log-scale compresses the ~400x dynamic range between DEN/DIA approach
          // corridors (~20k positions/cell) and typical overflight cells (~50).
          // Linear weighting blows out the color scale and hides ~90% of cells.
          getWeight: (d: { count: number }) => Math.log(d.count + 1),
          radiusPixels: 50,
          intensity: 1.5,
          threshold: 0.02,
          // Phosphor → cyan → violet ramp matching the design tokens
          colorRange: [
            [10, 61, 30, 0],
            [21, 194, 77, 80],
            [21, 194, 77, 140],
            [110, 255, 154, 180],
            [0, 212, 255, 200],
            [181, 140, 255, 220],
          ],
        }),
      )
    }

    if (rangeRingsOn) {
      const rings = [50, 100, 150, 200].map((nm) => ({
        range: nm,
        path: ringPolygon(station.lat, station.lon, nm),
      }))
      out.push(
        new PathLayer({
          id: 'range-rings',
          data: rings,
          getPath: (d: { path: [number, number][] }) => d.path,
          getColor: [21, 194, 77, 85],
          widthUnits: 'pixels',
          getWidth: 1,
        }),
      )
      out.push(
        new TextLayer({
          id: 'range-labels',
          data: rings.map((r) => ({ range: r.range, position: r.path[0] })),
          getPosition: (d: { position: [number, number] }) => d.position,
          getText: (d: { range: number }) => `${d.range}nm`,
          getSize: 10,
          getColor: [21, 194, 77, 180],
          fontFamily: 'JetBrains Mono, monospace',
          billboard: true,
          getPixelOffset: [0, -8],
        }),
      )
    }

    // Station marker
    out.push(
      new ScatterplotLayer({
        id: 'station-outer',
        data: [station],
        getPosition: (d: { lat: number; lon: number }) => [d.lon, d.lat],
        getRadius: 14,
        radiusUnits: 'pixels',
        getFillColor: [0, 212, 255, 40],
        getLineColor: [0, 212, 255, 220],
        lineWidthUnits: 'pixels',
        getLineWidth: 1.5,
        stroked: true,
      }),
    )
    out.push(
      new ScatterplotLayer({
        id: 'station-core',
        data: [station],
        getPosition: (d: { lat: number; lon: number }) => [d.lon, d.lat],
        getRadius: 4,
        radiusUnits: 'pixels',
        getFillColor: [0, 212, 255, 255],
      }),
    )

    // ─── Trails ─────────────────────────────────────────────────────────
    // Rendered above station markers but below aircraft so the markers sit on top
    // of their own trail. Order within this block: all-trails (faded), selected
    // auto-trail (cyan, prominent), full history (violet, most prominent).

    if (allTrailsOn && allTrails?.aircraft?.length) {
      const trailRows = allTrails.aircraft
        .filter((a) => a.points.length >= 2)
        .map((a) => ({
          hex: a.hex,
          path: a.points.map((p) => [p.lon, p.lat] as [number, number]),
          lastAlt: a.points[a.points.length - 1].alt_baro,
        }))
      out.push(
        new PathLayer({
          id: 'all-trails',
          data: trailRows,
          getPath: (d: { path: [number, number][] }) => d.path,
          getColor: (d: { lastAlt: number | null }) => {
            const [r, g, b] = altitudeColor(d.lastAlt)
            return [r, g, b, 120]
          },
          widthUnits: 'pixels',
          getWidth: 1.5,
          capRounded: true,
          jointRounded: true,
        }),
      )
    }

    if (selectedTrail.length >= 2) {
      out.push(
        new PathLayer({
          id: 'selected-trail',
          data: [{ path: selectedTrail }],
          getPath: (d: { path: [number, number][] }) => d.path,
          getColor: [0, 212, 255, 200],
          widthUnits: 'pixels',
          getWidth: 2,
          capRounded: true,
          jointRounded: true,
        }),
      )
    }

    if (historySegments.length) {
      out.push(
        new PathLayer({
          id: 'history-trail',
          data: historySegments.map((path) => ({ path })),
          getPath: (d: { path: [number, number][] }) => d.path,
          getColor: [181, 140, 255, 220],
          widthUnits: 'pixels',
          getWidth: 2,
          capRounded: true,
          jointRounded: true,
        }),
      )
    }

    // Aircraft click-target — a nearly-transparent ScatterplotLayer sized to match the
    // HTML marker footprint. Picking works reliably here because the circle fragment
    // shader doesn't discard based on texture alpha (unlike IconLayer with mask=true,
    // which drops picking pixels when getColor alpha is 0). Visuals are rendered by the
    // HTML <AircraftMarkers> overlay below for stable per-aircraft identity.
    out.push(
      new ScatterplotLayer({
        id: 'aircraft-pick',
        data: aircraft,
        pickable: true,
        getPosition: (a: AircraftState) => [a.lon as number, a.lat as number],
        getRadius: (a: AircraftState) => iconSizeForCategory(a.category) / 2 + 4,
        radiusUnits: 'pixels',
        radiusMinPixels: 12,
        // Alpha=1/255 is imperceptible visually but keeps the pixel above deck.gl's
        // picking alpha cutoff so click/hover registers.
        getFillColor: [0, 0, 0, 1],
        stroked: false,
        onClick: (info: { object?: AircraftState | null }) => {
          if (info.object) select(info.object.hex)
          return true
        },
      }),
    )

    return out
  }, [
    aircraft,
    rangeRingsOn,
    station.lat,
    station.lon,
    select,
    heatmapOn,
    heatmapData,
    allTrailsOn,
    allTrails,
    selectedTrail,
    historySegments,
  ])

  return (
    <div ref={containerRef} className="relative w-full h-full overflow-hidden">
      <DeckGL
        viewState={viewState}
        onViewStateChange={(e: { viewState: unknown }) => setViewState(e.viewState as ViewState)}
        onInteractionStateChange={(s: {
          isDragging?: boolean
          isPanning?: boolean
          isZooming?: boolean
          inTransition?: boolean
        }) => {
          setInteracting(
            Boolean(s.isDragging || s.isPanning || s.isZooming || s.inTransition),
          )
        }}
        controller={{ dragRotate: false }}
        layers={layers as never[]}
        style={{ background: '#05080A', filter: 'brightness(1.6) contrast(1.05)' }}
      />
      <AircraftMarkers
        aircraft={aircraft}
        viewport={viewport}
        selectedHex={selectedHex}
        interacting={interacting}
      />
      {sweepOn && stationPixel && (
        <div
          className="radar-sweep"
          style={{
            left: `${stationPixel.x}px`,
            top: `${stationPixel.y}px`,
            width: '200vmax',
            height: '200vmax',
          }}
        />
      )}
      {scanlinesOn && <div className="scanlines" />}

      {/* Zoom + home controls — touch-friendly (44px min target).
       *  When a drawer is open on the right, rightControlsOffset pushes the
       *  buttons to the left so they stay visible.
       *  When hideRightControls is true (e.g., mobile drawer expanded), slide
       *  them off-screen to the right and fade them out. */}
      <div
        className="absolute top-3 flex flex-col gap-2 z-20"
        style={{
          right: `${12 + rightControlsOffset}px`,
          transform: hideRightControls ? 'translateX(calc(100% + 24px))' : 'translateX(0)',
          opacity: hideRightControls ? 0 : 1,
          pointerEvents: hideRightControls ? 'none' : 'auto',
          transition:
            'transform var(--dur-mid) var(--ease-efis), opacity var(--dur-mid) var(--ease-efis), right var(--dur-mid) var(--ease-efis)',
        }}
      >
        <MapButton onClick={zoomIn} title="Zoom in" disabled={viewState.zoom >= MAX_ZOOM}>
          +
        </MapButton>
        <MapButton onClick={zoomOut} title="Zoom out" disabled={viewState.zoom <= MIN_ZOOM}>
          −
        </MapButton>
        <MapButton onClick={recenter} title="Recenter on station">
          ⌂
        </MapButton>
        <MapButton
          onClick={() => setHeatmapOn(!heatmapOn)}
          title="Toggle coverage heatmap"
          active={heatmapOn}
        >
          ≈
        </MapButton>
        <MapButton
          onClick={() => setAllTrailsOn(!allTrailsOn)}
          title="Toggle all aircraft trails"
          active={allTrailsOn}
        >
          ≡
        </MapButton>
      </div>

      {/* Heatmap window chip row — visible only when heatmap is on.
          Positioned left of the control stack so it doesn't clash with the buttons. */}
      {heatmapOn && (
        <div
          className="absolute top-3 z-20 flex flex-col gap-1 bg-bg-1/80 border border-stroke-hair backdrop-blur"
          style={{
            right: `${12 + rightControlsOffset + 56}px`,
            transform: hideRightControls ? 'translateX(calc(100% + 24px))' : 'translateX(0)',
            opacity: hideRightControls ? 0 : 1,
            pointerEvents: hideRightControls ? 'none' : 'auto',
            transition:
              'transform var(--dur-mid) var(--ease-efis), opacity var(--dur-mid) var(--ease-efis), right var(--dur-mid) var(--ease-efis)',
          }}
        >
          {(['1h', '24h', '7d', 'all'] as const satisfies readonly HeatmapWindow[]).map((w) => (
            <button
              key={w}
              type="button"
              onClick={() => setHeatmapWindow(w)}
              className={clsx(
                'px-2 py-1 font-mono text-[10px] uppercase tracking-wider border-l-2',
                heatmapWindow === w
                  ? 'border-efis-cyan text-efis-cyan bg-efis-cyan/10'
                  : 'border-transparent text-text-mid hover:text-text-hi',
              )}
            >
              {w.toUpperCase()}
            </button>
          ))}
        </div>
      )}

      {/* Zoom indicator */}
      <div className="absolute top-3 left-3 z-20 font-mono text-[10px] tracking-wider px-2 py-1 bg-bg-1/70 border border-stroke-hair text-text-mid">
        Z {viewState.zoom.toFixed(1)}
      </div>
    </div>
  )
}

function MapButton({
  onClick,
  title,
  disabled,
  active,
  children,
}: {
  onClick: () => void
  title: string
  disabled?: boolean
  active?: boolean
  children: React.ReactNode
}): React.ReactElement {
  return (
    <button
      type="button"
      onClick={onClick}
      onTouchEnd={(e) => {
        e.preventDefault()
        onClick()
      }}
      title={title}
      disabled={disabled}
      className={clsx(
        'w-11 h-11 flex items-center justify-center border font-mono text-xl leading-none select-none backdrop-blur',
        'disabled:opacity-40 disabled:cursor-not-allowed',
        active
          ? 'bg-efis-cyan/20 border-efis-cyan text-efis-cyan'
          : 'bg-bg-1/80 border-stroke-hair text-text-mid hover:text-efis-cyan hover:border-efis-cyan active:bg-efis-cyan/20',
      )}
    >
      {children}
    </button>
  )
}
