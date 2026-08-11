interface Props {
  /** Pixels width; "auto" fills parent */
  width?: string | number
  /** Height in pixels */
  height?: number
  className?: string
  /** Rounded variant */
  rounded?: 'sm' | 'md' | 'lg' | 'full'
}

const radii: Record<string, string> = {
  sm: 'rounded-sm',
  md: 'rounded',
  lg: 'rounded-lg',
  full: 'rounded-full',
}

export default function Skeleton({ width = 'auto', height = 16, className = '', rounded = 'md' }: Props) {
  return (
    <div
      className={`animate-pulse bg-surface-3 ${radii[rounded]} ${className}`}
      style={{ width, height }}
      aria-hidden="true"
    />
  )
}
