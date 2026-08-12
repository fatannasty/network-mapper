export interface TabItem {
  id: string
  label: string
  icon?: string
  count?: number
}

interface Props {
  tabs: readonly TabItem[]
  active: string
  onChange: (id: string) => void
}

export default function Tabs({ tabs, active, onChange }: Props) {
  return (
    <div className="flex border-b border-border/40" role="tablist">
      {tabs.map((tab) => {
        const isActive = tab.id === active
        return (
          <button
            key={tab.id}
            role="tab"
            aria-selected={isActive}
            onClick={() => onChange(tab.id)}
            className={`relative flex items-center gap-2 px-4 py-2.5 text-sm font-medium
              transition-all duration-200 border-b-2 -mb-px focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-accent rounded-t-xl
              ${isActive
                ? 'text-accent border-accent'
                : 'text-muted hover:text-text-secondary border-transparent'
              }`}
          >
            {tab.icon && (
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={1.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d={tab.icon} />
              </svg>
            )}
            {tab.label}
            {tab.count !== undefined && (
              <span className={`ml-1 px-1.5 py-0.5 rounded-full text-[11px] font-medium
                ${isActive ? 'bg-accent-subtle text-accent' : 'bg-surface-3 text-muted'}`}>
                {tab.count}
              </span>
            )}
          </button>
        )
      })}
      <div className="flex-1 border-b border-border/40" />
    </div>
  )
}
