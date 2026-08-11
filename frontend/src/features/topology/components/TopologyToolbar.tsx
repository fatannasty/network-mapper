import type { TopologyData, PathResult } from '../../../api'
import type { ProtocolFilter, LayoutMode } from '../hooks/useTopology'

interface Props {
  topology: TopologyData
  linkCounts: { lldp: number; cdp: number }
  protocolFilter: ProtocolFilter
  onProtocolFilterChange: (v: ProtocolFilter) => void
  layoutMode: LayoutMode
  onLayoutModeChange: (v: LayoutMode) => void
  pathSource: string
  onPathSourceChange: (v: string) => void
  pathTarget: string
  onPathTargetChange: (v: string) => void
  pathResult: PathResult | null
  onRunPath: () => void
  onClearPath: () => void
}

export default function TopologyToolbar({
  topology,
  linkCounts,
  protocolFilter,
  onProtocolFilterChange,
  layoutMode,
  onLayoutModeChange,
  pathSource,
  onPathSourceChange,
  pathTarget,
  onPathTargetChange,
  pathResult,
  onRunPath,
  onClearPath,
}: Props) {
  return (
    <div className="flex items-center gap-3 px-4 py-2 bg-surface-1 border-b border-border shrink-0 text-sm">
      <span className="text-muted">
        {topology.nodes.length} devices
        {topology.links.length > 0 && (
          <span className="ml-2">
            &middot; {topology.links.length} links
            {linkCounts.lldp > 0 && <span className="text-blue-400 ml-1">{linkCounts.lldp} LLDP</span>}
            {linkCounts.cdp > 0 && <span className="text-amber-400 ml-1">{linkCounts.cdp} CDP</span>}
          </span>
        )}
        {topology.scan_meta && (
          <span className="ml-3 text-[11px] text-muted/70">
            &middot; Scan: <span className="text-text-secondary">{topology.scan_meta.subnet}</span>
            {topology.scan_meta.scan_kind && (
              <span className="ml-1">({topology.scan_meta.scan_kind})</span>
            )}
          </span>
        )}
      </span>

      <div className="flex-1" />

      <div className="flex items-center gap-1 bg-surface-2 rounded p-0.5">
        <button
          onClick={() => onLayoutModeChange('tree')}
          className={`px-3 py-1 rounded text-xs font-medium transition-colors ${
            layoutMode === 'tree' ? 'bg-blue-600 text-white' : 'text-muted hover:text-text-primary'
          }`}
        >
          Tree
        </button>
        <button
          onClick={() => onLayoutModeChange('free')}
          className={`px-3 py-1 rounded text-xs font-medium transition-colors ${
            layoutMode === 'free' ? 'bg-blue-600 text-white' : 'text-muted hover:text-text-primary'
          }`}
        >
          Free
        </button>
      </div>

      {topology.links.length > 0 && (
        <select
          value={protocolFilter}
          onChange={(e) => onProtocolFilterChange(e.target.value as ProtocolFilter)}
          className="px-3 py-1 bg-surface-2 border border-border rounded text-text-secondary text-xs focus:outline-none focus:border-accent"
        >
          <option value="all">All Links</option>
          <option value="lldp">LLDP Only</option>
          <option value="cdp">CDP Only</option>
        </select>
      )}

      <span className="text-muted text-xs mx-1">|</span>

      <input
        value={pathSource}
        onChange={(e) => onPathSourceChange(e.target.value)}
        placeholder="Source IP"
        className="w-32 px-2 py-1 bg-surface-2 border border-border rounded text-text-secondary text-xs focus:outline-none focus:border-accent"
      />
      <span className="text-muted text-xs">&rarr;</span>
      <input
        value={pathTarget}
        onChange={(e) => onPathTargetChange(e.target.value)}
        placeholder="Target IP"
        className="w-32 px-2 py-1 bg-surface-2 border border-border rounded text-text-secondary text-xs focus:outline-none focus:border-accent"
      />
      <button
        onClick={onRunPath}
        disabled={!pathSource || !pathTarget}
        className="px-3 py-1 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white rounded text-xs transition-colors"
      >
        Find Path
      </button>
      {pathResult && (
        <button
          onClick={onClearPath}
          className="px-3 py-1 bg-surface-3 hover:bg-gray-600 text-text-secondary rounded text-xs transition-colors"
        >
          Clear Path
        </button>
      )}

      {topology.links.length === 0 && (
        <span className="text-muted text-xs">
          No auto-discovered links &mdash; run SNMP discovery on switches with LLDP/CDP enabled
        </span>
      )}
    </div>
  )
}
