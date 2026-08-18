import { useEffect, useState } from 'react'
import Modal from '../../../components/ui/Modal'
import Button from '../../../components/ui/Button'
import Input from '../../../components/ui/Input'
import {
  exportTopologyDiagram,
  getDiagramPrefs,
  saveDiagramPrefs,
  apiErrorMessage,
  type TopologyData,
  type DiagramFormat,
  type DiagramLegendEntry,
} from '../../../api'

const DEFAULT_LEGEND: DiagramLegendEntry[] = [
  { key: 'wan', label: 'WAN / Internet', color: '#1E88E5' },
  { key: 'core', label: 'Core Backbone', color: '#2E7D32' },
  { key: 'lan', label: 'LAN', color: '#7CB342' },
  { key: 'fiber', label: 'Fiber', color: '#E6C200' },
  { key: 'management', label: 'Management', color: '#8E24AA' },
]

const TOPOLOGIES: { id: 'auto' | 'tree' | 'star' | 'ring' | 'bus'; label: string; hint: string }[] = [
  { id: 'auto', label: 'Auto', hint: 'Detect best layout' },
  { id: 'tree', label: 'Tree', hint: 'Hierarchical tiers' },
  { id: 'star', label: 'Star', hint: 'Core in the centre' },
  { id: 'ring', label: 'Ring', hint: 'Devices in a circle' },
  { id: 'bus', label: 'Bus', hint: 'Single backbone row' },
]

const LINK_DETAILS: { id: 'full' | 'backbone' | 'core'; label: string; hint: string }[] = [
  { id: 'full', label: 'Full', hint: 'Every link' },
  { id: 'backbone', label: 'Backbone', hint: 'Hide redundancy' },
  { id: 'core', label: 'Core only', hint: 'Spine only' },
]

const FORMATS: { id: DiagramFormat; label: string; hint: string }[] = [
  { id: 'vsdx', label: 'Visio (.vsdx)', hint: 'Editable devices & connectors' },
  { id: 'pdf', label: 'PDF (.pdf)', hint: 'Static drawing sheet' },
  { id: 'docx', label: 'Word (.docx)', hint: 'Drawing image on a sized page' },
]

interface Props {
  open: boolean
  onClose: () => void
  topology: TopologyData
  defaultTitle: string
  scanId?: string
}

export default function ExportDiagramDialog({ open, onClose, topology, defaultTitle, scanId }: Props) {
  const [format, setFormat] = useState<DiagramFormat>('vsdx')
  const [title, setTitle] = useState(defaultTitle)
  const [drawnBy, setDrawnBy] = useState('')
  const [documentName, setDocumentName] = useState('')
  const [revision, setRevision] = useState('')
  const [colorLinks, setColorLinks] = useState(true)
  const [excludeEndpoints, setExcludeEndpoints] = useState(false)
  const [topoMode, setTopoMode] = useState<'auto' | 'tree' | 'star' | 'ring' | 'bus'>('auto')
  const [linkDetail, setLinkDetail] = useState<'full' | 'backbone' | 'core'>('full')
  const [legend, setLegend] = useState<DiagramLegendEntry[]>(DEFAULT_LEGEND)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!open || !scanId) return
    getDiagramPrefs(scanId)
      .then((p) => {
        setTopoMode(p.topology ?? 'auto')
        setLinkDetail(p.link_detail ?? 'full')
      })
      .catch(() => {})
  }, [open, scanId])

  const updateLegend = (i: number, patch: Partial<DiagramLegendEntry>) => {
    setLegend((prev) => prev.map((e, j) => (j === i ? { ...e, ...patch } : e)))
  }

  const onExport = async () => {
    setBusy(true)
    setError('')
    try {
      if (scanId) {
        await saveDiagramPrefs(scanId, { topology: topoMode, link_detail: linkDetail })
      }
      await exportTopologyDiagram({
        format,
        nodes: topology.nodes,
        links: topology.links,
        title: title.trim() || 'AMTRAK NETWORK DIAGRAM',
        drawn_by: drawnBy.trim(),
        document_name: documentName.trim(),
        revision: revision.trim(),
        color_links: colorLinks,
        exclude_endpoints: excludeEndpoints,
        topology: topoMode,
        link_detail: linkDetail,
        legend: legend.filter((e) => e.label.trim()),
      })
      onClose()
    } catch (err) {
      setError(apiErrorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Modal open={open} onClose={onClose} title="Export Diagram" size="max-w-lg">
      <div className="space-y-4 text-sm">
        <div>
          <label className="block text-xs text-muted mb-1.5">Format</label>
          <div className="grid grid-cols-3 gap-2">
            {FORMATS.map((f) => (
              <button
                key={f.id}
                type="button"
                onClick={() => setFormat(f.id)}
                className={`px-3 py-2 rounded-xl border text-left transition-all ${
                  format === f.id
                    ? 'border-accent bg-accent-subtle/50 text-text-primary'
                    : 'border-border/40 bg-surface-2/50 text-muted hover:text-text-primary'
                }`}
              >
                <div className="text-xs font-semibold">{f.label}</div>
                <div className="text-[10px] text-muted mt-0.5">{f.hint}</div>
              </button>
            ))}
          </div>
        </div>

        <div>
          <label className="block text-xs text-muted mb-1.5">Layout topology</label>
          <div className="grid grid-cols-5 gap-2">
            {TOPOLOGIES.map((t) => (
              <button
                key={t.id}
                type="button"
                onClick={() => setTopoMode(t.id)}
                className={`px-2 py-1.5 rounded-lg border text-center transition-all ${
                  topoMode === t.id
                    ? 'border-accent bg-accent-subtle/50 text-text-primary'
                    : 'border-border/40 bg-surface-2/50 text-muted hover:text-text-primary'
                }`}
              >
                <div className="text-xs font-semibold">{t.label}</div>
                <div className="text-[9px] text-muted mt-0.5">{t.hint}</div>
              </button>
            ))}
          </div>
        </div>

        <div>
          <label className="block text-xs text-muted mb-1.5">Link detail</label>
          <div className="grid grid-cols-3 gap-2">
            {LINK_DETAILS.map((d) => (
              <button
                key={d.id}
                type="button"
                onClick={() => setLinkDetail(d.id)}
                className={`px-2 py-1.5 rounded-lg border text-center transition-all ${
                  linkDetail === d.id
                    ? 'border-accent bg-accent-subtle/50 text-text-primary'
                    : 'border-border/40 bg-surface-2/50 text-muted hover:text-text-primary'
                }`}
              >
                <div className="text-xs font-semibold">{d.label}</div>
                <div className="text-[9px] text-muted mt-0.5">{d.hint}</div>
              </button>
            ))}
          </div>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div className="col-span-2">
            <label className="block text-xs text-muted mb-1">Drawing title</label>
            <Input value={title} onChange={(e) => setTitle(e.target.value)} />
          </div>
          <div>
            <label className="block text-xs text-muted mb-1">Drawn by</label>
            <Input value={drawnBy} onChange={(e) => setDrawnBy(e.target.value)} placeholder="Name" />
          </div>
          <div>
            <label className="block text-xs text-muted mb-1">Document name</label>
            <Input value={documentName} onChange={(e) => setDocumentName(e.target.value)} />
          </div>
          <div>
            <label className="block text-xs text-muted mb-1">Revision</label>
            <Input value={revision} onChange={(e) => setRevision(e.target.value)} placeholder="e.g. A" />
          </div>
          <div className="flex items-end pb-1">
            <label className="flex items-center gap-2 text-xs text-muted cursor-pointer">
              <input
                type="checkbox"
                checked={colorLinks}
                onChange={(e) => setColorLinks(e.target.checked)}
                className="accent-blue-500"
              />
              Color-code links by role
            </label>
          </div>
          <div className="flex items-end pb-1">
            <label className="flex items-center gap-2 text-xs text-muted cursor-pointer">
              <input
                type="checkbox"
                checked={excludeEndpoints}
                onChange={(e) => setExcludeEndpoints(e.target.checked)}
                className="accent-blue-500"
              />
              Exclude access points (separate page)
            </label>
          </div>
        </div>

        <div>
          <div className="flex items-center justify-between mb-1.5">
            <label className="text-xs text-muted">Legend</label>
            <button
              type="button"
              onClick={() => setLegend((prev) => [...prev, { label: '', color: '#333333' }])}
              className="text-[11px] text-accent hover:underline"
            >
              + Add entry
            </button>
          </div>
          <div className="space-y-1.5">
            {legend.map((entry, i) => (
              <div key={i} className="flex items-center gap-2">
                <input
                  type="color"
                  value={entry.color}
                  onChange={(e) => updateLegend(i, { color: e.target.value })}
                  className="w-7 h-7 rounded border border-border/40 bg-transparent cursor-pointer"
                  aria-label={`Legend color ${i + 1}`}
                />
                <Input
                  value={entry.label}
                  onChange={(e) => updateLegend(i, { label: e.target.value })}
                  placeholder="Label"
                  className="flex-1"
                />
                <button
                  type="button"
                  onClick={() => setLegend((prev) => prev.filter((_, j) => j !== i))}
                  className="text-muted hover:text-red-400 px-1"
                  aria-label={`Remove legend entry ${i + 1}`}
                >
                  ×
                </button>
              </div>
            ))}
          </div>
        </div>

        <p className="text-[11px] text-muted">
          The drawing sheet includes the Amtrak logo (top left) and the legend/title block at the
          bottom. Visio output stays fully editable — move devices, re-route links, restyle shapes.
        </p>

        {error && (
          <p className="text-xs text-red-400 bg-red-900/20 border border-red-800/40 rounded-lg px-3 py-2">
            {error}
          </p>
        )}

        <div className="flex justify-end gap-2 pt-1">
          <Button variant="secondary" size="sm" onClick={onClose} disabled={busy}>
            Cancel
          </Button>
          <Button size="sm" onClick={onExport} disabled={busy}>
            {busy ? 'Generating…' : 'Export'}
          </Button>
        </div>
      </div>
    </Modal>
  )
}
