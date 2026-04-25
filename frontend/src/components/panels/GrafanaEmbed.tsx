import { useEffect, useState } from 'react'

const MOBILE_BREAKPOINT_PX = 768

export function GrafanaEmbed(): React.ReactElement {
  const [isMobile, setIsMobile] = useState(
    () => typeof window !== 'undefined' && window.innerWidth < MOBILE_BREAKPOINT_PX,
  )

  useEffect(() => {
    const mq = window.matchMedia(`(max-width: ${MOBILE_BREAKPOINT_PX - 1}px)`)
    const onChange = (e: MediaQueryListEvent): void => setIsMobile(e.matches)
    mq.addEventListener('change', onChange)
    return () => mq.removeEventListener('change', onChange)
  }, [])

  const uid = isMobile ? 'adsb-receiver-health-mobile' : 'adsb-receiver-health'
  const src = `/grafana/d/${uid}/?kiosk&theme=dark&refresh=30s`

  return (
    <div className="h-full w-full flex flex-col bg-bg-0">
      <div className="flex items-center justify-between px-3 py-2 border-b border-stroke-hair">
        <div className="section-header text-text-low">
          RECEIVER HEALTH · GRAFANA {isMobile ? '(MOBILE)' : ''}
        </div>
        <a
          href={`/grafana/d/${uid}/`}
          target="_blank"
          rel="noreferrer"
          className="font-mono text-[11px] text-efis-cyan hover:underline"
        >
          Open in Grafana ↗
        </a>
      </div>
      <iframe
        key={uid}
        src={src}
        title="ADS-B Receiver Health"
        className="flex-1 w-full border-0 bg-bg-0"
        allow="fullscreen"
      />
    </div>
  )
}
