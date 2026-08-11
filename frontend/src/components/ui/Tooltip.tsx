import type { ReactNode } from 'react'

interface Props {
  content: string
  children: ReactNode
  /** top | bottom | left | right */
  position?: 'top' | 'bottom' | 'left' | 'right'
}

const positionClasses: Record<string, string> = {
  top: 'bottom-full left-1/2 -translate-x-1/2 mb-2',
  bottom: 'top-full left-1/2 -translate-x-1/2 mt-2',
  left: 'right-full top-1/2 -translate-y-1/2 mr-2',
  right: 'left-full top-1/2 -translate-y-1/2 ml-2',
}

export default function Tooltip({ content, children, position = 'top' }: Props) {
  return (
    <div className="relative inline-flex group">
      {children}
      <div
        role="tooltip"
        className={`pointer-events-none absolute z-50 opacity-0 group-hover:opacity-100
          transition-opacity duration-150 ${positionClasses[position]}
          px-2.5 py-1.5 rounded-lg text-xs font-medium
          bg-gray-800 text-white shadow-lg whitespace-nowrap
          dark:bg-gray-200 dark:text-gray-900`}
      >
        {content}
      </div>
    </div>
  )
}
