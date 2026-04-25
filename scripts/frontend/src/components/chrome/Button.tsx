import { clsx } from 'clsx'
import { forwardRef } from 'react'

type Variant = 'primary' | 'ghost' | 'danger'

interface Props extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant
  size?: 'sm' | 'md'
}

export const Button = forwardRef<HTMLButtonElement, Props>(function Button(
  { variant = 'ghost', size = 'md', className, children, ...rest },
  ref,
) {
  const base =
    'inline-flex items-center gap-2 font-mono uppercase tracking-wider border transition-[background,color,box-shadow] duration-[var(--dur-fast)] ease-[var(--ease-efis)] disabled:opacity-40 disabled:cursor-not-allowed'
  const sizes = size === 'sm' ? 'px-2 py-1 text-[10px]' : 'px-3 py-1.5 text-xs'
  const variants: Record<Variant, string> = {
    primary:
      'bg-transparent border-efis-cyan text-efis-cyan hover:bg-efis-cyan/10 active:bg-efis-cyan/20 shadow-[0_0_0_1px_transparent] hover:shadow-[0_0_0_1px_var(--efis-cyan)]',
    ghost:
      'bg-transparent border-stroke-hair text-text-mid hover:text-text-hi hover:border-efis-cyan',
    danger:
      'bg-transparent border-efis-red text-efis-red hover:bg-efis-red/10',
  }
  return (
    <button ref={ref} className={clsx(base, sizes, variants[variant], className)} {...rest}>
      {children}
    </button>
  )
})
