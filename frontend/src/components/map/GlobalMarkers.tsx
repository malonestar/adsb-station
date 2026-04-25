import { memo } from 'react'
import type { WebMercatorViewport } from '@deck.gl/core'
import { clsx } from 'clsx'

import type { GlobalAircraft } from '@/types/api'
import { altitudeColor } from '@/lib/format'

const ICON_SIZE = 16 // px — smaller than primary markers so they read as ambient

interface Props {
  aircraft: GlobalAircraft[]
  viewport: WebMercatorViewport | null
  /** When true, transitions are disabled (during map pan/zoom). */
  interacting: boolean
}

/**
 * Faded HTML overlay of adsb.lol "global context" aircraft — traffic outside
 * our antenna range. Rendered at reduced opacity, no labels, smaller than
 * primary markers so they read as ambient context, not as our own catches.
 *
 * Uses the existing aircraft-marker CSS so it picks up the same transition
 * behavior as the primary layer (no transitions during pan/zoom).
 */
export const GlobalMarkers = memo(function GlobalMarkers({
  aircraft,
  viewport,
  interacting,
}: Props): React.ReactElement | null {
  if (!viewport) return null
  return (
    <div
      className={clsx(
        'absolute inset-0 pointer-events-none z-[4]',
        interacting && 'aircraft-interacting',
      )}
      style={{ opacity: 0.45 }}
    >
      {aircraft.map((a) => {
        const [x, y] = viewport.project([a.lon, a.lat])
        const angle = a.track ?? 0
        const [r, g, b] = altitudeColor(a.alt_baro)
        const color = `rgb(${r}, ${g}, ${b})`
        return (
          <div
            key={a.hex}
            className="aircraft-marker absolute top-0 left-0"
            style={{
              transform: `translate3d(${x}px, ${y}px, 0)`,
              color,
            }}
          >
            <span
              className="aircraft-marker-icon"
              style={{
                width: `${ICON_SIZE}px`,
                height: `${ICON_SIZE}px`,
                marginLeft: `${-ICON_SIZE / 2}px`,
                marginTop: `${-ICON_SIZE / 2}px`,
                transform: `rotate(${angle}deg)`,
                WebkitMaskImage: 'url("/icons/narrow.svg")',
                maskImage: 'url("/icons/narrow.svg")',
                backgroundColor: color,
              }}
            />
          </div>
        )
      })}
    </div>
  )
})
