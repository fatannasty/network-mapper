import type { TopologyData, PathResult, ScanInfo } from '../../../api'
import type { ProtocolFilter, LayoutMode } from '../hooks/useTopology'
import Select from '../../../components/ui/Select'

interface Props {
  topology: TopologyData | null
  scans: ScanInfo[]
  scanId?: string
  onScanChange: (id: string) => void
  simplified: boolean
  onSimplifiedChange: (v: boolean) => void
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

function formatScanLabel(s: ScanInfo): string {
  const date = s.started_at ? s.started_at.slice(0, 16).replace('T', ' ') : ''
  const label = s.subnet || s.id.slice(0, 8)
  return `${label} — ${s.device_count} devices${date ? ` — ${date}` : ''}`
}

export default function TopologyToolbar({
  topology,
  scans,
  scanId,
  onScanChange,
  simplified,
  onSimplifiedChange,
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
      <div className="flex items-center gap-0.5 bg-surface-2 rounded-lg p-0.5">
        <button
          onClick={() => onSimplifiedChange(true)}
          className={`px-3 py-1 rounded-md text-xs font-semibold transition-colors ${
            simplified ? 'bg-blue-600 text-white' : 'text-muted hover:text-text-primary'
          }`}
        >
          Simple
        </button>
        <button
          onClick={() => onSimplifiedChange(false)}
          className={`px-3 py-1 rounded-md text-xs font-semibold transition-colors ${
            !simplified ? 'bg-blue-600 text-white' : 'text-muted hover:text-text-primary'
          }`}
        >
          Technical
        </button>
      </div>

      <Select
        value={scanId || ''}
        onChange={(e) => onScanChange(e.target.value)}
        className="max-w-72 text-xs"
        aria-label="Select scan"
      >
        <option value="">Latest scan</option>
        {scans.map((s) => (
          <option key={s.id} value={s.id}>
            {formatScanLabel(s)}
          </option>
        ))}
      </Select>

      <span className="text-muted">
        {topology?.nodes.length ?? 0} devices
        {(topology?.links.length ?? 0) > 0 && (
          <span className="ml-2">
            &middot; {topology?.links.length} links
          </span>
        )}
        {topology?.scan_meta && (
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
          className={`px-2.5 py-1 rounded text-xs font-medium transition-colors ${
            layoutMode === 'tree' ? 'bg-blue-600 text-white' : 'text-muted hover:text-text-primary'
          }`}
          title="Hierarchical tree layout"
        >
          Tree
        </button>
        <button
          onClick={() => onLayoutModeChange('radial')}
          className={`px-2.5 py-1 rounded text-xs font-medium transition-colors ${
            layoutMode === 'radial' ? 'bg-blue-600 text-white' : 'text-muted hover:text-text-primary'
          }`}
          title="Concentric rings by distance from core"
        >
          Radial
        </button>
        <button
          onClick={() => onLayoutModeChange('circle')}
          className={`px-2.5 py-1 rounded text-xs font-medium transition-colors ${
            layoutMode === 'circle' ? 'bg-blue-600 text-white' : 'text-muted hover:text-text-primary'
          }`}
          title="Single ring layout"
        >
          Circle
        </button>
        <button
          onClick={() => onLayoutModeChange('free')}
          className={`px-2.5 py-1 rounded text-xs font-medium transition-colors ${
            layoutMode === 'free' ? 'bg-blue-600 text-white' : 'text-muted hover:text-text-primary'
          }`}
          title="Free-form DFS layout"
        >
          Free
        </button>
      </div>

      {!simplified && (
        <>
          {(topology?.links.length ?? 0) > 0 && (
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
        </>
      )}

      {!simplified && (topology?.links.length ?? 0) === 0 && (
        <span className="text-muted text-xs">
          No auto-discovered links &mdash; run SNMP discovery on switches with LLDP/CDP enabled
        </span>
      )}
    </div>
  )
}
