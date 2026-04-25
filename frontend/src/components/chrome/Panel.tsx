import { clsx } from 'clsx'
import { SectionHeader } from './SectionHeader'

export interface PanelProps {
  title?: string
  action?: React.ReactNode
  active?: boolean
  padded?: boolean
  className?: string
  children: React.ReactNode
}

export function Panel({ title, action, active, padded = true, className, children }: PanelProps): React.ReactElement {
  return (
    <section
      className={clsx(
        'bg-bg-1 border border-stroke-hair rounded-[2px] relative',
        active && 'shadow-[inset_0_0_0_1px_var(--efis-cyan)]',
        className,
      )}
    >
      {title && (
        <div className="flex items-center justify-between px-3 py-2 border-b border-stroke-hair">
          <SectionHeader>{title}</SectionHeader>
          {action && <div className="flex items-center gap-1">{action}</div>}
        </div>
      )}
      <div className={clsx(padded && 'p-3')}>{children}</div>
    </section>
  )
}
