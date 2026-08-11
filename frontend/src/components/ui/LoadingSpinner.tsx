interface Props {
  size?: 'sm' | 'md'
}

export default function LoadingSpinner({ size = 'md' }: Props) {
  const dims = size === 'sm' ? 'h-5 w-5 border-2' : 'h-8 w-8 border-[3px]'
  return (
    <div className="flex items-center justify-center py-12">
      <div className={`${dims} border-accent/30 border-t-accent rounded-full animate-spin`} />
    </div>
  )
}
