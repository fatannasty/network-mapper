interface Props {
  title: string
  message?: string
}

export default function EmptyState({ title, message }: Props) {
  return (
    <div className="flex flex-col items-center justify-center py-16 text-center">
      <div className="text-4xl mb-4 opacity-30">⚡</div>
      <h3 className="text-sm font-medium text-text-secondary mb-1">{title}</h3>
      {message && <p className="text-xs text-muted max-w-xs">{message}</p>}
    </div>
  )
}
