import type { Edge } from '@xyflow/react'
import type { Device, TopoLink } from '../../../api'
import { shortenInterface } from '../../../components/ui/iface'
import { shortName } from '../services/friendly'

interface Props {
  edge: Edge | null
  deviceByIp: Map<string, Device>
  x: number
  y: number
}

function findInterface(device: Device | undefined, ifName: string) {
  if (!device || !ifName || !device.interfaces) return undefined
  return device.interfaces.find(
    (i) => i.ifName === ifName || i.ifDescr === ifName,
  )
}

function trimNum(n: number): string {
  return Number.isInteger(n) ? String(n) : n.toFixed(1).replace(/\.0$/, '')
}

function formatSpeed(ifSpeed?: string, ifHighSpeed?: string): string {
  const hs = ifHighSpeed ? Number(ifHighSpeed) : NaN
  const sp = ifSpeed ? Number(ifSpeed) : NaN
  let mbps = NaN
  if (!Number.isNaN(hs) && hs > 0) mbps = hs
  else if (!Number.isNaN(sp) && sp > 0) mbps = sp / 1_000_000
  if (Number.isNaN(mbps) || mbps <= 0) return ''
  if (mbps >= 1000) return `${trimNum(mbps / 1000)} Gbps`
  return `${trimNum(mbps)} Mbps`
}

type Status = 'up' | 'down' | 'testing' | 'unknown'

const STATUS_META: Record<Status, { label: string; dot: string }> = {
  up: { label: 'Up', dot: 'bg-emerald-400' },
  down: { label: 'Down', dot: 'bg-red-400' },
  testing: { label: 'Testing', dot: 'bg-amber-400' },
  unknown: { label: 'Unknown', dot: 'bg-gray-400' },
}

function linkStatus(srcIface: ReturnType<typeof findInterface>, tgtIface: ReturnType<typeof findInterface>): Status {
  const ops = [srcIface?.ifOperStatus, tgtIface?.ifOperStatus]
  if (ops.includes('down')) return 'down'
  if (ops.includes('testing')) return 'testing'
  if (ops.length && ops.every((o) => o === 'up')) return 'up'
  return 'unknown'
}

function combinedLatency(a?: number, b?: number): number | null {
  const vals = [a, b].filter((v): v is number => typeof v === 'number' && v > 0)
  if (!vals.length) return null
  return vals.reduce((s, v) => s + v, 0) / vals.length
}

export default function TopologyLinkTooltip({ edge, deviceByIp, x, y }: Props) {
  if (!edge) return null

  const data = edge.data as { link?: TopoLink; cluster?: { src: string; tgt: string; count: number } } | undefined

  // Grouped/cluster edge: summarize the aggregated connection.
  if (data?.cluster) {
    return (
      <div
        className="fixed z-50 pointer-events-none w-64 bg-surface-1/95 backdrop-blur-2xl border border-border rounded-xl shadow-2xl p-3"
        style={{ left: x + 14, top: y + 14 }}
      >
        <div className="text-xs font-semibold text-text-primary">
          {data.cluster.src} {'\u2194'} {data.cluster.tgt}
        </div>
        <div className="text-[11px] text-muted mt-1">
          {data.cluster.count} connection{data.cluster.count === 1 ? '' : 's'} between these device groups.
        </div>
      </div>
    )
  }

  if (!data?.link) return null
  const l = data.link

  const srcDev = deviceByIp.get(l.source)
  const tgtDev = deviceByIp.get(l.target)
  const srcIface = findInterface(srcDev, l.source_interface)
  const tgtIface = findInterface(tgtDev, l.target_interface)

  const status = linkStatus(srcIface, tgtIface)
  const statusMeta = STATUS_META[status]
  const bandwidth = formatSpeed(srcIface?.ifSpeed, srcIface?.ifHighSpeed)
    || formatSpeed(tgtIface?.ifSpeed, tgtIface?.ifHighSpeed)
  const latency = combinedLatency(srcDev?.latency_ms, tgtDev?.latency_ms)

  const srcName = shortName(l.source_hostname) || l.source
  const tgtName = shortName(l.target_hostname) || l.target

  return (
    <div
      className="fixed z-50 pointer-events-none w-72 bg-surface-1/95 backdrop-blur-2xl border border-border rounded-xl shadow-2xl p-3"
      style={{ left: x + 14, top: y + 14 }}
    >
      <div className="flex items-center justify-between gap-2">
        <span className="text-sm font-semibold text-text-primary truncate">
          {srcName} {'\u2192'} {tgtName}
        </span>
        <span className="flex items-center gap-1.5 shrink-0">
          <span className={`w-2 h-2 rounded-full ${statusMeta.dot}`} />
          <span className="text-[11px] text-text-secondary">{statusMeta.label}</span>
        </span>
      </div>

      <div className="mt-2.5 grid grid-cols-2 gap-x-3 gap-y-1.5 text-[11px]">
        <div className="text-muted">Bandwidth</div>
        <div className="text-right text-text-secondary font-medium">{bandwidth || '\u2014'}</div>

        <div className="text-muted">Latency</div>
        <div className="text-right text-text-secondary font-medium">
          {latency !== null ? `${latency.toFixed(1)} ms` : '\u2014'}
        </div>

        <div className="text-muted">Protocol</div>
        <div className="text-right text-text-secondary font-medium">
          {l.protocol === 'cdp-lldp' ? 'CDP/LLDP' : l.protocol ? l.protocol.toUpperCase() : '\u2014'}
        </div>
      </div>

      <div className="mt-2.5 pt-2 border-t border-border/40">
        <div className="flex items-center justify-between gap-2 text-[11px]">
          <span className="text-muted truncate">
            {shortenInterface(l.source_interface) || '?'}
            {' \u2192 '}
            {shortenInterface(l.target_interface) || '?'}
          </span>
        </div>
      </div>
    </div>
  )
}
