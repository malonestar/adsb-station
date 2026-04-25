import { memo } from 'react'
import type { WebMercatorViewport } from '@deck.gl/core'
import { clsx } from 'clsx'

import type { AircraftState } from '@/types/api'
import { pickIcon, iconSizeForCategory } from './getAircraftIcon'
import { altitudeColor, fmtCallsign } from '@/lib/format'

interface Props {
  aircraft: AircraftState[]
  viewport: WebMercatorViewport | null
  selectedHex: string | null
  /** When true, transitions are disabled (during map pan/zoom) so markers stay glued to the map. */
  interacting: boolean
}

/**
 * Renders aircraft icons + callsign labels as HTML elements positioned via the deck.gl
 * WebMercatorViewport. Keyed by hex so React reconciles each aircraft to a stable DOM
 * node; CSS transitions on transform give smooth per-aircraft animation with correct
 * identity (no index-based interpolation bugs).
 *
 * This container is `pointer-events: none` so map pan/zoom passes through untouched;
 * clicks on aircraft are handled by the invisible, pickable deck.gl IconLayer instead.
 */
export const AircraftMarkers = memo(function AircraftMarkers({
  aircraft,
  viewport,
  selectedHex,
  interacting,
}: Props): React.ReactElement | null {
  if (!viewport) return null

  return (
    <div
      className={clsx(
        'absolute inset-0 pointer-events-none z-[5]',
        interacting && 'aircraft-interacting',
      )}
    >
      {aircraft.map((a) => {
        if (a.lat == null || a.lon == null) return null
        const [x, y] = viewport.project([a.lon, a.lat])
        const angle = a.track ?? 0
        const size = iconSizeForCategory(a.category)
        const isSelected = a.hex === selectedHex
        const [r, g, b] = a.is_emergency
          ? [255, 59, 47]
          : isSelected
            ? [255, 255, 255]
            : altitudeColor(a.alt_baro)
        const color = `rgb(${r}, ${g}, ${b})`
        return (
          <div
            key={a.hex}
            className={clsx(
              'aircraft-marker absolute top-0 left-0',
              isSelected && 'aircraft-marker-selected',
              a.is_emergency && 'aircraft-marker-emergency',
            )}
            style={{
              transform: `translate3d(${x}px, ${y}px, 0)`,
              color,
            }}
          >
            <span
              className="aircraft-marker-icon"
              style={{
                width: `${size}px`,
                height: `${size}px`,
                marginLeft: `${-size / 2}px`,
                marginTop: `${-size / 2}px`,
                transform: `rotate(${angle}deg)`,
                WebkitMaskImage: `url("${pickIcon(a)}")`,
                maskImage: `url("${pickIcon(a)}")`,
                backgroundColor: color,
              }}
            />
            <span
              className="aircraft-marker-label"
              style={{ top: `${-size / 2 + 2}px`, left: `${size / 2 + 4}px` }}
            >
              {fmtCallsign(a)}
            </span>
          </div>
        )
      })}
    </div>
  )
})
