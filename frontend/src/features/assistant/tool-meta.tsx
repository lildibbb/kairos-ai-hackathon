import type { ComponentType } from 'react'
import {
  ArrowsClockwise, ArrowsLeftRight, Broom, Crown, DownloadSimple, Gauge, ListChecks, MagnifyingGlass,
  Path, Power, Prohibit, Pulse, Sliders, Sparkle, Tag, Waveform, WifiHigh, type IconProps,
} from '@phosphor-icons/react'
import type { AgentActivity } from '../../lib/assistant/agent-activity'
import type { ToolResult } from '../../lib/api/tools'

type ToolMeta = { icon: ComponentType<IconProps>; verb: string; tone: 'scan' | 'change' | 'power' | 'read' }

export const TOOL_META: Record<string, ToolMeta> = {
  get_device_status: { icon: Pulse, verb: 'Reading device health', tone: 'read' },
  list_connected_clients: { icon: ListChecks, verb: 'Listing clients', tone: 'read' },
  run_speed_test: { icon: Gauge, verb: 'Running throughput test', tone: 'read' },
  run_optical_diagnostics: { icon: Waveform, verb: 'Reading optical levels', tone: 'read' },
  wifi_spectrum_scan: { icon: MagnifyingGlass, verb: 'Scanning the spectrum', tone: 'scan' },
  trace_service_path: { icon: Path, verb: 'Tracing the service path', tone: 'scan' },
  client_signal_survey: { icon: WifiHigh, verb: 'Surveying client signal', tone: 'scan' },
  reboot_router: { icon: Power, verb: 'Rebooting', tone: 'power' },
  reboot_ont: { icon: Power, verb: 'Power-cycling', tone: 'power' },
  upgrade_firmware: { icon: DownloadSimple, verb: 'Upgrading firmware', tone: 'power' },
  refresh_ont_registration: { icon: ArrowsClockwise, verb: 'Re-registering', tone: 'change' },
  reset_optical_port: { icon: ArrowsClockwise, verb: 'Resetting optical port', tone: 'change' },
  optimize_wifi_radio: { icon: Sparkle, verb: 'Optimising Wi-Fi', tone: 'change' },
  set_wifi_channel: { icon: Sliders, verb: 'Retuning radio', tone: 'change' },
  set_wifi_ssid: { icon: Tag, verb: 'Renaming network', tone: 'change' },
  update_config: { icon: Sliders, verb: 'Applying configuration', tone: 'change' },
  steer_client_band: { icon: ArrowsLeftRight, verb: 'Steering client', tone: 'change' },
  set_qos_priority: { icon: Crown, verb: 'Prioritising traffic', tone: 'change' },
  flush_dns_cache: { icon: Broom, verb: 'Flushing DNS', tone: 'change' },
  restart_service: { icon: ArrowsClockwise, verb: 'Restarting service', tone: 'change' },
  block_client: { icon: Prohibit, verb: 'Quarantining client', tone: 'change' },
  set_dhcp_reservation: { icon: Tag, verb: 'Reserving address', tone: 'change' },
}

export function toolMeta(name: string): ToolMeta {
  return TOOL_META[name] ?? { icon: Sliders, verb: 'Running tool', tone: 'change' }
}

type Metrics = NonNullable<AgentActivity['metrics']>
type Row = Record<string, unknown>

const num = (value: unknown) => (typeof value === 'number' ? value : null)
const rows = (value: unknown): Row[] => (Array.isArray(value) ? (value as Row[]) : [])

/** Readings to pin on topology nodes once a tool has a result. */
export function resultMetrics(toolName: string, result: ToolResult | null | undefined, targetId: string): Metrics {
  const data = (result?.data ?? {}) as Row
  const metrics: Metrics = {}
  if (data.kind === 'survey') {
    for (const client of rows(data.clients)) {
      const rssi = num(client.rssi)
      if (typeof client.device_id !== 'string' || rssi === null) continue
      metrics[client.device_id] = { text: `${rssi} dBm`, tone: rssi >= -67 ? 'ok' : rssi >= -75 ? 'warn' : 'bad' }
    }
  } else if (data.kind === 'path') {
    for (const hop of rows(data.hops)) {
      if (typeof hop.device_id !== 'string' || hop.role === 'client') continue
      metrics[hop.device_id] = { text: `${num(hop.latency_ms) ?? '?'} ms`, tone: hop.status === 'warn' ? 'warn' : 'ok' }
    }
    metrics[targetId] = metrics[targetId] ?? { text: `${num(data.total_ms) ?? '?'} ms total`, tone: 'ok' }
  } else if (data.kind === 'spectrum') {
    const two = (data.bands as Row | undefined)?.['2.4'] as Row | undefined
    if (two) metrics[targetId] = { text: `ch ${two.current} → ${two.recommended}`, tone: num(two.current_utilization) !== null && (num(two.current_utilization) ?? 0) > 60 ? 'warn' : 'ok' }
  } else if (data.kind === 'status') {
    const cpu = rows(data.metrics).find((item) => item.label === 'CPU')
    if (cpu) metrics[targetId] = { text: `CPU ${cpu.value}%`, tone: cpu.warn ? 'bad' : 'ok' }
  } else if (data.kind === 'speed') {
    metrics[targetId] = { text: `${Math.round(num(data.download_mbps) ?? 0)}↓ ${Math.round(num(data.upload_mbps) ?? 0)}↑`, tone: 'ok' }
  } else if (data.kind === 'diff') {
    const first = rows(data.changes).find((change) => change.field !== 'Status') ?? rows(data.changes)[0]
    if (first) metrics[targetId] = { text: `${first.field}: ${first.after}`, tone: 'ok' }
    for (const id of (Array.isArray(data.affected_ids) ? data.affected_ids : []) as string[]) {
      if (id !== targetId) metrics[id] = { text: toolName === 'set_qos_priority' ? 'priority' : 'updated', tone: 'ok' }
    }
  }
  return metrics
}

/** Devices the n-th replayed trace step touches, so the canvas follows the stream. */
export function stepFocus(result: ToolResult | null | undefined, index: number, targetId: string): string[] {
  const data = (result?.data ?? {}) as Row
  if (data.kind === 'path') {
    const hop = rows(data.hops)[index]
    return typeof hop?.device_id === 'string' ? [hop.device_id] : []
  }
  if (data.kind === 'survey' || data.kind === 'clients') {
    return rows(data.clients).map((client) => client.device_id).filter((id): id is string => typeof id === 'string')
  }
  if (data.kind === 'diff' && Array.isArray(data.affected_ids) && index >= (result?.trace.length ?? 1) - 2) {
    return (data.affected_ids as string[]).filter((id) => id !== targetId)
  }
  return []
}
