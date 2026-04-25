import { clsx } from 'clsx'

type State = 'ok' | 'warn' | 'down' | 'absent' | 'unknown'

const STYLES: Record<State, { bg: string; glow: string; label: string }> = {
  ok:      { bg: 'bg-phos-hi',    glow: 'shadow-[0_0_6px_var(--phos-hi)]',    label: 'OK' },
  warn:    { bg: 'bg-efis-amber', glow: 'shadow-[0_0_6px_var(--efis-amber)]', label: 'WARN' },
  down:    { bg: 'bg-efis-red',   glow: 'shadow-[0_0_6px_var(--efis-red)]',   label: 'DOWN' },
  absent:  { bg: 'bg-text-low',   glow: '',                                    label: '—' },
  unknown: { bg: 'bg-text-low',   glow: '',                                    label: '?' },
}

export function StatusLED({
  state,
  showLabel = false,
  size = 8,
}: {
  state: State
  showLabel?: boolean
  size?: number
}): React.ReactElement {
  const s = STYLES[state]
  return (
    <span className="inline-flex items-center gap-2">
      <span
        aria-hidden
        className={clsx('inline-block rounded-full', s.bg, s.glow)}
        style={{ width: size, height: size }}
      />
      {showLabel && <span className="section-header text-[10px]">{s.label}</span>}
    </span>
  )
}
