interface Props {
  className?: string
  lines?: number
}

export default function Skeleton({ className = 'h-4 w-full', lines = 1 }: Props) {
  if (lines === 1) {
    return <div className={`animate-pulse rounded-lg bg-surface-3/60 ${className}`} />
  }
  return (
    <div className="space-y-2">
      {Array.from({ length: lines }).map((_, i) => (
        <div key={i} className={`animate-pulse rounded-lg bg-surface-3/60 ${className}`} />
      ))}
    </div>
  )
}
