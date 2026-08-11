import type { ReactNode } from 'react'

interface Props {
  type: 'loading' | 'empty' | 'error'
  title?: string
  message?: string
  action?: ReactNode
  className?: string
}

export default function PageState({ type, title, message, action, className = '' }: Props) {
  const isError = type === 'error'
  return (
    <div className={`flex items-center justify-center ${className}`}>
      <div className="text-center">
        {type === 'loading' && (
          <div className="h-8 w-8 border-[3px] border-accent/30 border-t-accent rounded-full animate-spin mx-auto mb-3" />
        )}
        {isError && (
          <div className="flex items-center justify-center w-12 h-12 mx-auto mb-3 rounded-full bg-danger/15 text-danger">
            <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z" />
            </svg>
          </div>
        )}
        {type === 'empty' && (
          <div className="flex items-center justify-center w-12 h-12 mx-auto mb-3 rounded-full bg-surface-2 text-muted">
            <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="M20.25 7.5l-.625 10.632a2.25 2.25 0 01-2.247 2.118H6.622a2.25 2.25 0 01-2.247-2.118L3.75 7.5m8.25 3v6.75m0 0l-3-3m3 3l3-3M3.375 7.5h17.25c.621 0 1.125-.504 1.125-1.125v-1.5c0-.621-.504-1.125-1.125-1.125H3.375c-.621 0-1.125.504-1.125 1.125v1.5c0 .621.504 1.125 1.125 1.125z" />
            </svg>
          </div>
        )}
        {title && (
          <p className={`text-sm font-medium mb-1 ${isError ? 'text-danger' : 'text-text-secondary'}`}>{title}</p>
        )}
        {message && <p className="text-xs text-muted max-w-sm mx-auto">{message}</p>}
        {action && <div className="mt-4 flex items-center justify-center gap-2">{action}</div>}
      </div>
    </div>
  )
}
