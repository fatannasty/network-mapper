import type { ReactNode } from 'react'

export type SortDir = 'asc' | 'desc'

export interface Column<T> {
  key: string
  label: string
  sortable?: boolean
  headerClassName?: string
  cellClassName?: string
  render?: (item: T) => ReactNode
}

interface Props<T> {
  columns: readonly Column<T>[]
  data: readonly T[]
  rowKey?: (item: T) => string
  sortKey?: string | null
  sortDir?: SortDir
  onSort?: (key: string, dir: SortDir) => void
  onRowClick?: (item: T) => void
  selectedId?: string | null
  emptyMessage?: string
}

function SortArrow({ active, dir }: { active: boolean; dir?: SortDir }) {
  if (!active) return <span className="text-muted ml-1 text-[11px]">\u25B4\u25BE</span>
  return (
    <span className="text-accent ml-1 text-[11px]">
      {dir === 'asc' ? '\u25B4' : '\u25BE'}
    </span>
  )
}

export default function DataTable<T>({
  columns,
  data,
  rowKey,
  sortKey,
  sortDir = 'asc',
  onSort,
  onRowClick,
  selectedId,
  emptyMessage = 'No data',
}: Props<T>) {
  const resolveKey = rowKey ?? ((item: T) => String((item as Record<string, unknown>).id ?? ''))

  const handleSort = (key: string) => {
    if (!onSort) return
    const newDir = sortKey === key && sortDir === 'asc' ? 'desc' : 'asc'
    onSort(key, newDir)
  }

  return (
    <div className="overflow-auto">
      <table className="w-full text-sm">
        <thead className="sticky top-0 bg-surface-1 border-b border-border z-10">
          <tr className="text-left text-muted text-[11px] uppercase tracking-wider">
            {columns.map((col) => (
              <th
                key={col.key}
                className={`px-4 py-2.5 font-medium whitespace-nowrap
                  ${col.sortable !== false && onSort ? 'cursor-pointer hover:text-text-secondary select-none' : ''}
                  ${col.headerClassName ?? ''}`}
                onClick={() => col.sortable !== false && handleSort(col.key)}
              >
                {col.label}
                {col.sortable !== false && onSort && (
                  <SortArrow active={sortKey === col.key} dir={sortDir} />
                )}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.length === 0 ? (
            <tr>
              <td colSpan={columns.length} className="px-4 py-8 text-center text-muted text-xs">
                {emptyMessage}
              </td>
            </tr>
          ) : (
            data.map((item, idx) => {
              const id = resolveKey(item)
              const isSelected = selectedId === id
              return (
                <tr
                  key={id ?? idx}
                  tabIndex={onRowClick ? 0 : undefined}
                  role={onRowClick ? 'button' : undefined}
                  onClick={() => onRowClick?.(item)}
                  onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onRowClick?.(item) } }}
                  className={`border-b border-border/50 transition-colors
                    focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-accent
                    ${onRowClick ? 'cursor-pointer hover:bg-surface-3/50' : ''}
                    ${isSelected ? 'bg-surface-3' : ''}`}
                >
                  {columns.map((col) => (
                    <td
                      key={col.key}
                      className={`px-4 py-2 ${col.cellClassName ?? ''}`}
                    >
                      {col.render
                        ? col.render(item)
                        : <span className="text-text-primary text-xs">{String((item as Record<string, unknown>)[col.key] ?? '\u2014')}</span>}
                    </td>
                  ))}
                </tr>
              )
            })
          )}
        </tbody>
      </table>
    </div>
  )
}
