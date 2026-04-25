interface Props {
  points: { ts: number; v: number }[]
  height?: number
  stroke?: string
  fill?: string
  strokeWidth?: number
  min?: number
  max?: number
  className?: string
}

/**
 * Tiny dependency-free SVG sparkline. Scales to container width via
 * `preserveAspectRatio="none"` + viewBox, so it fills whatever parent it's in.
 */
export function Sparkline({
  points,
  height = 48,
  stroke = 'var(--phos-mid)',
  fill = 'rgba(21, 194, 77, 0.12)',
  strokeWidth = 1.2,
  min,
  max,
  className,
}: Props): React.ReactElement {
  if (points.length < 2) {
    return (
      <div
        className={className}
        style={{ height }}
        aria-label="sparkline empty"
      />
    )
  }

  const vmin = min ?? Math.min(...points.map((p) => p.v), 0)
  const vmax = max ?? Math.max(...points.map((p) => p.v), 1)
  const range = Math.max(1, vmax - vmin)
  const W = 100
  const H = height
  const ts0 = points[0].ts
  const tsN = points[points.length - 1].ts
  const tspan = Math.max(1, tsN - ts0)

  const coords = points.map((p) => {
    const x = ((p.ts - ts0) / tspan) * W
    const y = H - ((p.v - vmin) / range) * H
    return [x, y] as const
  })

  const path = coords.map(([x, y], i) => (i === 0 ? `M${x} ${y}` : `L${x} ${y}`)).join(' ')
  const fillPath = `${path} L${W} ${H} L0 ${H} Z`

  return (
    <svg
      className={className}
      viewBox={`0 0 ${W} ${H}`}
      preserveAspectRatio="none"
      width="100%"
      height={H}
    >
      <path d={fillPath} fill={fill} />
      <path d={path} fill="none" stroke={stroke} strokeWidth={strokeWidth} vectorEffect="non-scaling-stroke" />
    </svg>
  )
}
