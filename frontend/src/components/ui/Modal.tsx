import { useEffect, useRef, type ReactNode, type MouseEvent } from 'react'
import { createPortal } from 'react-dom'

interface Props {
  open: boolean
  onClose: () => void
  title?: string
  children: ReactNode
  /** Max-width class, e.g. "max-w-md" */
  size?: string
}

export default function Modal({ open, onClose, title, children, size = 'max-w-md' }: Props) {
  const overlayRef = useRef<HTMLDivElement>(null)
  const previousFocus = useRef<HTMLElement | null>(null)

  useEffect(() => {
    if (open) {
      previousFocus.current = document.activeElement as HTMLElement
      document.body.style.overflow = 'hidden'
    }
    return () => {
      document.body.style.overflow = ''
      previousFocus.current?.focus()
    }
  }, [open])

  useEffect(() => {
    if (!open) return
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [open, onClose])

  if (!open) return null

  const handleOverlayClick = (e: MouseEvent) => {
    if (e.target === overlayRef.current) onClose()
  }

  return createPortal(
    <div
      ref={overlayRef}
      onClick={handleOverlayClick}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4"
      role="dialog"
      aria-modal="true"
      aria-label={title}
    >
      <div className={`bg-surface-1/90 backdrop-blur-2xl border border-border/40 rounded-2xl shadow-xl w-full ${size} max-h-[90vh] overflow-auto`}>
        {title && (
          <div className="flex items-center justify-between px-5 py-4 border-b border-border/30">
            <h2 className="text-sm font-semibold text-text-primary">{title}</h2>
            <button
              onClick={onClose}
              className="text-muted hover:text-text-primary text-lg leading-none transition-colors"
              aria-label="Close"
            >
              &times;
            </button>
          </div>
        )}
        <div className="p-5">{children}</div>
      </div>
    </div>,
    document.body,
  )
}
