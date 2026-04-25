import { clsx } from 'clsx'

export function SectionHeader({
  children,
  className,
}: {
  children: React.ReactNode
  className?: string
}): React.ReactElement {
  return (
    <h3 className={clsx('section-header flex items-center gap-2', className)}>
      {children}
    </h3>
  )
}
