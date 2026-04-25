import { DeckGL } from '@deck.gl/react'
import { MapboxOverlay } from '@deck.gl/mapbox'
import { IconLayer, PathLayer, ScatterplotLayer, TextLayer } from '@deck.gl/layers'
import { useEffect, useMemo, useRef, useState } from 'react'
import maplibregl, { Map as MlMap } from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'

import { useAircraft, selectAircraftWithPosition } from '@/store/aircraft'
import { useSelection } from '@/store/selection'
import { useSettings } from '@/store/settings'
import { altitudeColor } from '@/lib/format'
import { ringPolygon } from '@/lib/geo'
import { pickIcon, iconSizeForCategory } from './getAircraftIcon'
import type { AircraftState } from '@/types/api'

const INITIAL_VIEW = {
  longitude: -104.8,
  latitude: 39.7,
  zoom: 8.5,
  pitch: 0,
  bearing: 0,
}

const BASEMAP_STYLE = 'https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json'

interface Props {
  station: { lat: number; lon: number }
}

export function RadarMap({ station }: Props): React.ReactElement {
  const mapRef = useRef<MlMap | null>(null)
  const containerRef = useRef<HTMLDivElement | null>(null)
  const [ready, setReady] = useState(false)
  const aircraft = useAircraft(selectAircraftWithPosition)
  const selectedHex = useSelection((s) => s.selectedHex)
  const select = useSelection((s) => s.select)
  const { rangeRingsOn, sweepOn, scanlinesOn } = useSettings()

  // Initialize MapLibre once
  useEffect(() => {
    if (!containerRef.current) return
    const m = new maplibregl.Map({
      container: containerRef.current,
      style: BASEMAP_STYLE,
      center: [INITIAL_VIEW.longitude, INITIAL_VIEW.latitude],
      zoom: INITIAL_VIEW.zoom,
      pitch: 0,
      bearing: 0,
      attributionControl: { compact: true },
    })
    m.on('load', () => setReady(true))
    mapRef.current = m
    return () => {
      m.remove()
      mapRef.current = null
    }
  }, [])

  const rangeRings = useMemo(() => {
    if (!rangeRingsOn) return []
    return [50, 100, 150, 200].map((nm) => ({
      range: nm,
      path: ringPolygon(station.lat, station.lon, nm),
    }))
  }, [station, rangeRingsOn])

  const rangeLabels = useMemo(() => {
    if (!rangeRingsOn) return []
    return rangeRings.map((r) => {
      const first = r.path[0]
      return { range: r.range, position: first }
    })
  }, [rangeRings, rangeRingsOn])

  const layers = useMemo(() => {
    const out: unknown[] = []

    // Range rings
    if (rangeRings.length) {
      out.push(
        new PathLayer({
          id: 'range-rings',
          data: rangeRings,
          getPath: (d: { path: [number, number][] }) => d.path,
          getColor: [21, 194, 77, 85],
          widthUnits: 'pixels',
          getWidth: 1,
          capRounded: false,
        }),
      )
      out.push(
        new TextLayer({
          id: 'range-labels',
          data: rangeLabels,
          getPosition: (d: { position: [number, number] }) => d.position,
          getText: (d: { range: number }) => `${d.range}nm`,
          getSize: 10,
          getColor: [21, 194, 77, 180],
          getAngle: 0,
          fontFamily: 'JetBrains Mono, monospace',
          billboard: true,
          getPixelOffset: [0, -8],
        }),
      )
    }

    // Station marker (pulsing cyan concentric)
    out.push(
      new ScatterplotLayer({
        id: 'station-outer',
        data: [station],
        getPosition: (d: { lat: number; lon: number }) => [d.lon, d.lat],
        getRadius: 10,
        radiusUnits: 'pixels',
        getFillColor: [0, 212, 255, 40],
        getLineColor: [0, 212, 255, 200],
        lineWidthUnits: 'pixels',
        getLineWidth: 1,
        stroked: true,
      }),
    )
    out.push(
      new ScatterplotLayer({
        id: 'station-core',
        data: [station],
        getPosition: (d: { lat: number; lon: number }) => [d.lon, d.lat],
        getRadius: 3,
        radiusUnits: 'pixels',
        getFillColor: [0, 212, 255, 255],
      }),
    )

    // Aircraft icons
    out.push(
      new IconLayer({
        id: 'aircraft',
        data: aircraft,
        pickable: true,
        getPosition: (a: AircraftState) => [a.lon as number, a.lat as number],
        getIcon: (a: AircraftState) => ({
          url: pickIcon(a),
          width: 128,
          height: 128,
          mask: true,
        }),
        getSize: (a: AircraftState) => iconSizeForCategory(a.category),
        getAngle: (a: AircraftState) => -(a.track ?? 0),
        getColor: (a: AircraftState) => {
          if (a.is_emergency) return [255, 59, 47, 255]
          if (a.hex === selectedHex) return [255, 255, 255, 255]
          return [...altitudeColor(a.alt_baro), 240] as [number, number, number, number]
        },
        sizeUnits: 'pixels',
        sizeMinPixels: 14,
        sizeMaxPixels: 40,
        onClick: ({ object }: { object: AircraftState }) => {
          if (object) select(object.hex)
        },
        updateTriggers: {
          getColor: [selectedHex],
        },
        transitions: {
          getPosition: { duration: 1000, easing: (t: number) => t },
          getAngle: { duration: 800 },
        },
      }),
    )

    // Callsign labels near the aircraft
    out.push(
      new TextLayer({
        id: 'aircraft-labels',
        data: aircraft,
        getPosition: (a: AircraftState) => [a.lon as number, a.lat as number],
        getText: (a: AircraftState) => (a.flight?.trim() || a.registration || a.hex.toUpperCase()),
        getSize: 10,
        getColor: (a: AircraftState) => {
          if (a.is_emergency) return [255, 59, 47, 255]
          if (a.hex === selectedHex) return [255, 255, 255, 255]
          return [...altitudeColor(a.alt_baro), 220] as [number, number, number, number]
        },
        fontFamily: 'JetBrains Mono, monospace',
        billboard: true,
        getPixelOffset: [14, 0],
        getAlignmentBaseline: 'center',
        updateTriggers: {
          getColor: [selectedHex],
        },
      }),
    )

    return out
  }, [aircraft, rangeRings, rangeLabels, selectedHex, station, select])

  // Apply deck.gl overlay once the map loads
  useEffect(() => {
    if (!ready || !mapRef.current) return
    const overlay = new MapboxOverlay({ layers: layers as never[] })
    mapRef.current.addControl(overlay)
    return () => {
      try {
        mapRef.current?.removeControl(overlay)
      } catch {
        // already removed
      }
    }
    // We intentionally only attach once; the layer list is updated via DeckGL below.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ready])

  return (
    <div className="relative w-full h-full overflow-hidden">
      <div ref={containerRef} className="absolute inset-0" />
      {/* deck.gl overlay using MapboxOverlay for sync with maplibre */}
      <DeckGL
        initialViewState={INITIAL_VIEW}
        controller={false}
        layers={layers as never[]}
        style={{ pointerEvents: 'none' }}
        parameters={{ depthCompare: 'always' }}
      />
      {sweepOn && <div className="radar-sweep" />}
      {scanlinesOn && <div className="scanlines" />}
    </div>
  )
}
