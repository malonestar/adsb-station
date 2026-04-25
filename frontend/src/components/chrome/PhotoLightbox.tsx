import { useEffect } from 'react'

interface Props {
  imageUrl: string
  caption?: string
  sourceUrl?: string | null
  onClose: () => void
}

/**
 * Fullscreen photo viewer. Click anywhere outside the image to close;
 * Esc also closes. Optional caption shows below the image; optional
 * sourceUrl renders as a "view source" link (e.g., the planespotters page).
 */
export function PhotoLightbox({
  imageUrl,
  caption,
  sourceUrl,
  onClose,
}: Props): React.ReactElement {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  return (
    <div
      className="fixed inset-0 bg-black/90 flex items-center justify-center z-50 p-4 cursor-zoom-out"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
    >
      <div
        className="max-w-5xl w-full flex flex-col items-center"
        onClick={(e) => e.stopPropagation()}
      >
        <img
          src={imageUrl}
          alt={caption ?? ''}
          className="max-w-full max-h-[85vh] object-contain"
        />
        <div className="font-mono text-xs text-text-mid mt-2 flex items-center gap-3 justify-between w-full">
          {caption ? <span className="truncate">{caption}</span> : <span />}
          <div className="flex items-center gap-3 shrink-0">
            {sourceUrl && (
              <a
                href={sourceUrl}
                target="_blank"
                rel="noreferrer"
                className="hover:text-efis-cyan"
                onClick={(e) => e.stopPropagation()}
              >
                view source ↗
              </a>
            )}
            <button
              type="button"
              onClick={onClose}
              className="text-text-mid hover:text-efis-cyan"
              aria-label="Close"
            >
              ✕ CLOSE
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
