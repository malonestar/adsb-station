import { clsx } from 'clsx'

interface DataCellProps {
  label: string
  value: React.ReactNode
  unit?: string
  accent?: 'cyan' | 'amber' | 'red' | 'phos' | 'white'
  align?: 'left' | 'right'
  className?: string
}

export function DataCell({
  label,
  value,
  unit,
  accent,
  align = 'left',
  className,
}: DataCellProps): React.ReactElement {
  const accentClass = accent
    ? {
        cyan: 'text-efis-cyan',
        amber: 'text-efis-amber',
        red: 'text-efis-red',
        phos: 'text-phos-hi',
        white: 'text-efis-white',
      }[accent]
    : 'text-text-hi'

  return (
    <div className={clsx('flex flex-col gap-0.5', align === 'right' && 'items-end', className)}>
      <span className="section-header text-[10px] leading-none">{label}</span>
      <div className={clsx('flex items-baseline gap-1 font-mono tabular-nums', accentClass)}>
        <span className="text-sm leading-tight">{value}</span>
        {unit && <span className="text-[10px] text-text-low uppercase">{unit}</span>}
      </div>
    </div>
  )
}
