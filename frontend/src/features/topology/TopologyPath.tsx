import { useEffect, useMemo, useRef, useState, type ComponentType } from 'react'
import {
  ReactFlow,
  Background, BackgroundVariant, Handle, Position, Controls, useReactFlow, useStore,
  type Edge,
  type Node as FlowNode,
  type NodeChange,
  type NodeProps,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import {
  Camera,
  Circuitry,
  Cpu,
  Desktop,
  DeviceMobile,
  DeviceTablet,
  GameController,
  HardDrives,
  Laptop,
  Printer,
  SpeakerHigh,
  Television,
  Broadcast,
  Globe,
  WifiHigh,
  Network,
  Gauge,
  Plug,
  Lightbulb,
  Thermometer,
  type IconProps,
} from '@phosphor-icons/react'
import type { TopologyEdge, TopologyNode } from '../../lib/api/topology'
import type { EntityFact } from '../../lib/api/tickets'
import { TopologyInspector } from './TopologyInspector'
import { PacketEdge } from './PacketEdge'
import type { IncidentStage } from '../work/IncidentTrace'
import { useReducedMotion } from 'framer-motion'
import { AGENT_PHASE_LABEL, type AgentActivity, type AgentPhase } from '../../lib/assistant/agent-activity'

type IconComponent = ComponentType<IconProps>

export function resolveDeviceType(node: TopologyNode): string {
  const normalize = (value: unknown) => typeof value === 'string' ? value.trim().toLowerCase().replace(/[_-]+/g, ' ') : ''
  const aliases: Record<string, string> = {
    root: 'router', satellite: 'mesh', 'access point': 'ap', 'wireless access point': 'ap',
    'smart phone': 'phone', smartphone: 'phone', 'mobile phone': 'phone',
    'smart tv': 'tv', 'smart television': 'tv', 'ip camera': 'camera',
    'gaming console': 'console', 'game console': 'console', 'set top box': 'iptv',
    notebook: 'laptop', 'desktop computer': 'desktop', 'personal computer': 'pc',
    'smart speaker': 'speaker', 'wifi extender': 'extender', repeater: 'extender',
    'energy meter': 'meter', 'smart plug': 'plug', 'smart switch': 'plug',
    'smart bulb': 'light', 'light bulb': 'light', 'temperature sensor': 'sensor',
  }
  const primary = normalize(node.device_type)
  if (!['sta', 'station', 'client', 'device', 'unknown', 'other', ''].includes(primary)) return aliases[primary] ?? primary
  const name = [node.name, node.device_data?.friendly_name, node.device_data?.model].map(normalize).join(' ')
  const nameHints: [RegExp, string][] = [
    [/\b(nest wifi|google wifi|deco|eero|orbi)\b/, 'mesh'],
    [/\b(shelly (?:pro )?(?:3em|em|em50)|sonoff (?:pow|powr\w*))\b/, 'meter'],
    [/\b(shelly (?:h&t|ht)|sonoff th\d*|thermostat|temperature sensor)\b/, 'sensor'],
    [/\b(shelly|sonoff|smart plug|tapo p\d+|kasa (?:hs|kp)\d+)\b/, 'plug'],
    [/\b(hue|yeelight|smart bulb|tapo l\d+)\b/, 'light'],
    [/\b(ipad|tablet|galaxy tab)\b/, 'tablet'],
    [/\b(iphone|oppo|realme|redmi|oneplus|pixel|galaxy|smartphone|vivo|v\d{4}|cph\d{4}|rmx\d{4}|sm [agsmf]\w+)\b/, 'phone'],
    [/\b(macbook|laptop|notebook|thinkpad|chromebook)\b/, 'laptop'],
    [/\b(fire tv|apple tv|chromecast|roku|television|tv)\b/, 'tv'],
    [/\b(playstation|ps[345]|xbox|nintendo)\b/, 'console'],
    [/\b(camera|cam|webcam|tapo c\d+|cctv)\b/, 'camera'],
    [/\b(printer|laserjet|deskjet|officejet|epson)\b/, 'printer'],
    [/\b(echo|homepod|sonos|speaker)\b/, 'speaker'],
    [/\b(desktop|imac|workstation)\b/, 'desktop'],
  ]
  for (const [pattern, kind] of nameHints) if (pattern.test(name)) return kind
  const brand = normalize(node.device_data?.brand)
  if (['oppo', 'vivo', 'realme', 'oneplus'].includes(brand)) return 'phone'
  if (['shelly', 'sonoff'].includes(brand)) return 'iot'
  const cloud = normalize(node.device_data?.cloud_device_type)
  const kind = aliases[cloud] ?? cloud
  // Imported station rows also call phones "Gateway" or "Repeater"; those are not hardware evidence.
  if (['sta', 'station', 'client', 'device', 'unknown', 'other', '', 'gateway', 'extender', 'ap'].includes(kind)) return 'client'
  return kind
}

function deviceIcon(deviceType: string): IconComponent {
  switch (deviceType.trim().toLowerCase()) {
    case 'internet':
      return Globe
    case 'router':
    case 'gateway':
      return Broadcast
    case 'ap':
    case 'access point':
    case 'mesh':
    case 'extender':
      return WifiHigh
    case 'olt':
      return HardDrives
    case 'switch':
      return Network
    case 'onu':
    case 'ont':
      return Cpu
    case 'phone':
    case 'mobile':
    case 'smartphone':
      return DeviceMobile
    case 'laptop':
      return Laptop
    case 'desktop':
    case 'computer':
    case 'pc':
      return Desktop
    case 'tablet':
      return DeviceTablet
    case 'tv':
    case 'television':
    case 'iptv':
    case 'streaming':
      return Television
    case 'camera':
    case 'cam':
      return Camera
    case 'speaker':
    case 'smart speaker':
      return SpeakerHigh
    case 'printer':
      return Printer
    case 'console':
    case 'gaming':
    case 'game console':
      return GameController
    case 'meter':
      return Gauge
    case 'plug':
      return Plug
    case 'light':
      return Lightbulb
    case 'sensor':
      return Thermometer
    case 'iot':
      return Cpu
    default:
      return Circuitry
  }
}

function deviceKindLabel(deviceType: string): string {
  const labels: Record<string, string> = {
    router: 'Router',
    ap: 'Access point',
    'access point': 'Access point',
    mesh: 'Mesh node',
    extender: 'Extender',
    gateway: 'Gateway',
    olt: 'OLT',
    internet: 'Internet',
    onu: 'Optical unit',
    ont: 'Optical terminal',
    switch: 'Switch',
    phone: 'Phone',
    mobile: 'Phone',
    smartphone: 'Phone',
    laptop: 'Laptop',
    desktop: 'Desktop',
    computer: 'Computer',
    pc: 'Computer',
    tablet: 'Tablet',
    tv: 'TV',
    television: 'TV',
    iptv: 'IPTV box',
    camera: 'Camera',
    speaker: 'Speaker',
    printer: 'Printer',
    console: 'Console',
    gaming: 'Console',
    meter: 'Energy meter',
    plug: 'Smart relay / plug',
    light: 'Smart light',
    sensor: 'Sensor',
    iot: 'IoT device',
    client: 'Network client',
  }
  return labels[deviceType.trim().toLowerCase()] ?? deviceType.replace(/_/g, ' ')
}

function deviceStatusLabel(status: string): string {
  switch (status.toLowerCase()) {
    case 'online':
      return 'Online'
    case 'offline':
      return 'Offline'
    case 'unreachable':
      return 'Unreachable'
    case 'degraded':
      return 'Degraded'
    case 'unknown':
      return 'Unknown'
    default:
      return status.replace(/_/g, ' ')
  }
}

function statusTone(status: string): 'ok' | 'warn' | 'down' {
  const normalized = status.trim().toLowerCase()
  if (normalized === 'offline' || normalized === 'unreachable') return 'down'
  if (normalized === 'online') return 'ok'
  return 'warn'
}

function isBrokenStatus(status: string): boolean {
  return statusTone(status) === 'down'
}

// BFS preserves upstream depth; small groups stack in columns and wide fans arc around their parent.
function layoutPositions(nodes: TopologyNode[], edges: TopologyEdge[]) {
  const adjacency = new Map<string, string[]>(nodes.map((node) => [node.device_id, []]))
  for (const edge of edges) {
    adjacency.get(edge.source_device_id)?.push(edge.target_device_id)
    adjacency.get(edge.target_device_id)?.push(edge.source_device_id)
  }
  const incoming = new Set(edges.map((edge) => edge.target_device_id))
  const seeds = [...nodes.filter((node) => !incoming.has(node.device_id)), ...nodes]
  const depth = new Map<string, number>()
  let offset = 0
  for (const seed of seeds) {
    if (depth.has(seed.device_id)) continue
    depth.set(seed.device_id, offset)
    const queue = [seed.device_id]
    let furthest = offset
    for (let head = 0; head < queue.length; head += 1) {
      const current = queue[head]
      const currentDepth = depth.get(current) ?? offset
      furthest = Math.max(furthest, currentDepth)
      for (const next of adjacency.get(current) ?? []) {
        if (depth.has(next)) continue
        depth.set(next, currentDepth + 1)
        queue.push(next)
      }
    }
    offset = furthest + 1
  }

  const columns = new Map<number, string[]>()
  for (const node of nodes) {
    const column = depth.get(node.device_id) ?? 0
    columns.set(column, [...(columns.get(column) ?? []), node.device_id])
  }
  const positions = new Map<string, { x: number; y: number }>()
  let columnX = 0
  let previous: { x: number; y: number }[] = []
  for (const [column, ids] of [...columns].sort(([a], [b]) => a - b)) {
    if (column > 0 && ids.length >= 4 && previous.length > 0) {
      // A wide fan sits on an arc around its parent, so every link radiates
      // straight out and never crosses another device or its label.
      const cx = previous.reduce((sum, point) => sum + point.x, 0) / previous.length
      const cy = previous.reduce((sum, point) => sum + point.y, 0) / previous.length
      // An ellipse wider than tall suits the landscape canvas, so fitView keeps icons large.
      const radius = Math.max(380, ids.length * 74)
      const spread = Math.min(150, 30 * (ids.length - 1)) * (Math.PI / 180)
      const placed = ids.map((id, index) => {
        const angle = ids.length === 1 ? 0 : -spread / 2 + (spread * index) / (ids.length - 1)
        const point = { x: cx + radius * 1.1 * Math.cos(angle), y: cy + radius * 0.7 * Math.sin(angle) }
        positions.set(id, point)
        return point
      })
      previous = placed
      columnX = Math.max(...placed.map((point) => point.x)) + 240
      continue
    }
    const rows = Math.min(3, ids.length)
    const placed = ids.map((id, index) => {
      const row = index % rows
      const group = Math.floor(index / rows)
      const point = { x: columnX + group * 220, y: (row - (rows - 1) / 2) * 165 }
      positions.set(id, point)
      return point
    })
    previous = placed
    columnX += Math.ceil(ids.length / rows) * 220 + (column === 0 ? 60 : 0)
  }
  return positions
}

type DeviceData = {
  name: string
  deviceRef: string
  deviceType: string
  status: string
  selected: boolean
  active: boolean
  outcome?: 'complete' | 'blocked'
  /** Agent phase when this device is the tool target. */
  agentPhase?: AgentPhase
  agentTool?: string
  /** Sweep order while the agent reads the network. */
  scanIndex?: number
  /** Downstream of a device the agent is changing. */
  affected?: 'dropped' | 'reconnecting'
  /** Touched by the current tool step (hop being probed, client surveyed or steered). */
  focused?: boolean
  /** Live reading pinned by the agent, e.g. "-82 dBm". */
  metric?: { text: string; tone: 'ok' | 'warn' | 'bad' }
  /** Wireless clients: signal bars (1-4) and band. */
  signal?: number
  band?: string
  /** Scan tools sweep a radar around the target. */
  sweep?: boolean
  /** 0-1 progress ring while the agent replays a tool trace on this device. */
  progress?: number
}
type DeviceFlowNode = FlowNode<DeviceData, 'device'>

function agentStateLabel(data: DeviceData): string | undefined {
  if (data.affected === 'dropped') return 'Link down'
  if (data.affected === 'reconnecting') return 'Reconnecting'
  if (data.agentPhase === 'executing' && data.agentTool?.startsWith('reboot')) return 'Rebooting'
  if (data.agentPhase === 'executing' && data.agentTool && /scan|survey|trace|status|list|speed|optical_diag/.test(data.agentTool)) return 'Reading'
  if (data.agentPhase === 'executing') return 'Applying change'
  if (data.agentPhase === 'verifying') return 'Verifying'
  return undefined
}

const RING = 2 * Math.PI * 35

function DeviceNode({ data }: NodeProps<DeviceFlowNode>) {
  const Icon = deviceIcon(data.deviceType)
  const tone = data.agentPhase === 'executing' && data.agentTool?.startsWith('reboot') ? 'down' : statusTone(data.status)
  const agentState = agentStateLabel(data)
  return (
    <div data-device-kind={data.deviceType}
      style={data.scanIndex !== undefined ? { animationDelay: `${(data.scanIndex % 12) * 110}ms` } : undefined}
      className={`network-device network-device--${tone}${data.selected ? ' is-selected' : ''}${data.active ? ' is-active' : ''}${data.outcome ? ` outcome-${data.outcome}` : ''}${data.agentPhase ? ` agent-target agent-${data.agentPhase}` : ''}${data.scanIndex !== undefined ? ' agent-scan' : ''}${data.affected ? ` agent-affected agent-affected--${data.affected}` : ''}${data.focused ? ' agent-focus' : ''}`}>
      {/* Both handles sit on the circle centre so links meet the device icon, not the label. */}
      <Handle type="target" position={Position.Left} className="network-device__handle" />
      {data.agentPhase && data.agentTool && <span className="network-device__agent-badge" aria-hidden="true">
        <span className="network-device__agent-dot" />{data.agentTool.replace(/_/g, ' ')}
      </span>}
      <div className="network-device__equipment" aria-hidden="true">
        <span className="network-device__pulse" />
        {data.sweep && <span className="network-device__radar" />}
        {data.agentPhase && <><span className="network-device__orbit" /><span className="network-device__ripple" /><span className="network-device__ripple network-device__ripple--late" /></>}
        {data.progress !== undefined && <svg className="network-device__progress" viewBox="0 0 76 76" aria-hidden="true">
          <circle cx="38" cy="38" r="35" />
          <circle cx="38" cy="38" r="35" className="is-value" strokeDasharray={RING} strokeDashoffset={RING * (1 - data.progress)} />
        </svg>}
        <Icon className="network-device__icon" size={44} weight="fill" aria-hidden="true" />
        <span className={`network-device__status-dot is-${tone}`} />
        {data.signal !== undefined && <span className="network-device__signal" title={`${data.signal} of 4 bars`}>
          {[1, 2, 3, 4].map((bar) => <i key={bar} className={bar <= (data.signal ?? 0) ? 'is-on' : undefined} />)}
        </span>}
        {data.band && <span className="network-device__band">{data.band}</span>}
      </div>
      <span className="network-device__kind">{deviceKindLabel(data.deviceType)}</span>
      <strong>{data.name}</strong>
      <span className="network-device__state">{agentState ?? deviceStatusLabel(data.status)}</span>
      {data.metric && <span className={`network-device__metric is-${data.metric.tone}`}>{data.metric.text}</span>}
      <Handle type="source" position={Position.Right} className="network-device__handle" />
    </div>
  )
}

function signalBars(rssi: unknown): number | undefined {
  if (typeof rssi !== 'number') return undefined
  return rssi >= -55 ? 4 : rssi >= -67 ? 3 : rssi >= -75 ? 2 : 1
}

function bandLabel(link: unknown): string | undefined {
  if (typeof link !== 'string') return undefined
  if (link.startsWith('5')) return '5G'
  if (link.startsWith('2')) return '2.4G'
  if (/ethernet|lan|wired/i.test(link)) return 'LAN'
  return undefined
}

const SCAN_TOOLS = /spectrum|survey|optimi[sz]e|list_connected|trace_service/

function FitCanvas() {
  const { fitView } = useReactFlow()
  const width = useStore((state) => state.width)
  const height = useStore((state) => state.height)
  useEffect(() => {
    if (width && height) void fitView({ padding: 0.18, minZoom: width < 600 ? 0.65 : 0.4, maxZoom: 1, duration: 0 })
  }, [width, height, fitView])
  return null
}

const nodeTypes = { device: DeviceNode }
const edgeTypes = { packet: PacketEdge }

type TopologyPathProps = {
  nodes: TopologyNode[]
  edges: TopologyEdge[]
  serviceRef: string | null
  facts?: EntityFact[]
  selectedDeviceId?: string
  onSelectDevice?: (id: string) => void
  onClearSelection?: () => void
  actionStage?: IncidentStage
  actionDeviceId?: string
  agentActivity?: AgentActivity | null
}

/** Devices fed by the target, following the recorded link direction. */
function downstreamOf(target: string | undefined, edges: TopologyEdge[]): Set<string> {
  const reached = new Set<string>()
  if (!target) return reached
  const queue = [target]
  for (let head = 0; head < queue.length; head += 1) {
    for (const edge of edges) {
      if (edge.source_device_id === queue[head] && !reached.has(edge.target_device_id) && edge.target_device_id !== target) {
        reached.add(edge.target_device_id)
        queue.push(edge.target_device_id)
      }
    }
  }
  return reached
}

export function TopologyPath({ nodes, edges, serviceRef, facts = [], selectedDeviceId, onSelectDevice, onClearSelection, actionStage, actionDeviceId, agentActivity }: TopologyPathProps) {
  const reducedMotion = Boolean(useReducedMotion())
  const [hoveredDeviceId, setHoveredDeviceId] = useState<string>()
  const [paused, setPaused] = useState(false)
  const hoverTimer = useRef<ReturnType<typeof setTimeout>>()
  useEffect(() => () => clearTimeout(hoverTimer.current), [])
  const inspect = (id: string) => { clearTimeout(hoverTimer.current); setHoveredDeviceId(id) }
  const leave = () => { clearTimeout(hoverTimer.current); hoverTimer.current = setTimeout(() => setHoveredDeviceId(undefined), 500) }
  // The HTTP execution contract has no start acknowledgement; request latency is not running telemetry.
  const actionRunning = false
  const inspectedId = hoveredDeviceId ?? selectedDeviceId
  const nodeById = useMemo(() => new Map(nodes.map((node) => [node.device_id, node])), [nodes])
  const drawableEdges = useMemo(
    () => edges.filter((edge) => nodeById.has(edge.source_device_id) && nodeById.has(edge.target_device_id)),
    [edges, nodeById],
  )

  // React Flow resets a node's measured size whenever a new node object arrives
  // and hides it until re-measured. Carry the last measurement over so a
  // topology refresh (for example after a reboot) never blanks the canvas.
  const measured = useRef(new Map<string, { width: number; height: number }>())
  const onNodesChange = (changes: NodeChange<DeviceFlowNode>[]) => {
    for (const change of changes) {
      if (change.type === 'dimensions' && change.dimensions) measured.current.set(change.id, change.dimensions)
    }
  }
  const focusIds = useMemo(() => new Set(agentActivity?.focusIds ?? []), [agentActivity?.focusIds])
  const metrics = agentActivity?.metrics
  const agentTarget = agentActivity?.deviceId && nodeById.has(agentActivity.deviceId) ? agentActivity.deviceId : undefined
  const agentPhase = agentActivity?.phase
  const agentTool = agentActivity?.toolName
  const isReboot = Boolean(agentTool?.startsWith('reboot'))
  const readOnlyTool = agentActivity?.toolKind === 'read_only'
  const isWifiChange = !readOnlyTool && Boolean(agentTool && /wifi|update_config|optimi[sz]e|steer/.test(agentTool))
  const downstream = useMemo(() => downstreamOf(agentTarget, drawableEdges), [agentTarget, drawableEdges])
  const affectedState = (id: string): DeviceData['affected'] => {
    if (!downstream.has(id) || reducedMotion) return undefined
    if (isReboot && agentPhase === 'executing') return 'dropped'
    if ((isReboot && agentPhase === 'verifying') || (isWifiChange && (agentPhase === 'executing' || agentPhase === 'verifying'))) return 'reconnecting'
    return undefined
  }

  const flowNodes = useMemo<DeviceFlowNode[]>(() => {
    const positions = layoutPositions(nodes, drawableEdges)
    return nodes.map((node, index) => ({
      id: node.device_id,
      type: 'device',
      position: positions.get(node.device_id) ?? { x: 0, y: 0 },
      ...(measured.current.has(node.device_id) ? { measured: measured.current.get(node.device_id) } : {}),
      data: {
        name: node.name,
        deviceRef: node.device_ref,
        deviceType: resolveDeviceType(node),
        status: node.status,
        selected: node.device_id === inspectedId,
        active: Boolean(!paused && !reducedMotion && actionRunning && node.device_id === actionDeviceId),
        outcome: node.device_id === actionDeviceId && (actionStage?.state === 'complete' || actionStage?.state === 'blocked') ? actionStage.state : undefined,
        agentPhase: node.device_id === agentTarget ? agentPhase : undefined,
        agentTool: node.device_id === agentTarget ? agentTool : undefined,
        scanIndex: agentPhase === 'thinking' || (agentPhase === 'planning' && !agentTarget) ? index : undefined,
        affected: affectedState(node.device_id),
        focused: focusIds.has(node.device_id),
        metric: metrics?.[node.device_id],
        signal: signalBars(node.device_data?.rssi),
        band: bandLabel(node.device_data?.link_type),
        sweep: node.device_id === agentTarget && agentPhase === 'executing' && Boolean(agentTool && SCAN_TOOLS.test(agentTool)) && !reducedMotion,
        progress: node.device_id === agentTarget && (agentPhase === 'executing' || agentPhase === 'verifying') ? agentActivity?.progress : undefined,
      },
      draggable: false,
      selectable: false,
      focusable: false,
    }))
    // affectedState only reads values listed here.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nodes, drawableEdges, inspectedId, actionRunning, actionDeviceId, actionStage?.state, paused, reducedMotion, agentTarget, agentPhase, agentTool, downstream, isReboot, isWifiChange, focusIds, metrics, agentActivity?.progress])

  const flowEdges = useMemo<Edge[]>(() => drawableEdges.map((edge, index) => {
    const source = nodeById.get(edge.source_device_id)
    const target = nodeById.get(edge.target_device_id)
    const touchesTarget = Boolean(agentTarget) && (edge.source_device_id === agentTarget || edge.target_device_id === agentTarget)
    const inBlastRadius = touchesTarget || downstream.has(edge.target_device_id)
    const rebootDrop = isReboot && agentPhase === 'executing' && inBlastRadius && !reducedMotion
    const broken = rebootDrop || isBrokenStatus(source?.status ?? '') || isBrokenStatus(target?.status ?? '')
    const highlighted = inspectedId === edge.source_device_id || inspectedId === edge.target_device_id
    // Commands travel toward the target; configuration then propagates outward to its clients.
    const focusEdge = agentPhase === 'executing' && (focusIds.has(edge.source_device_id) || focusIds.has(edge.target_device_id))
      && (edge.source_device_id === agentTarget || edge.target_device_id === agentTarget || (focusIds.has(edge.source_device_id) && focusIds.has(edge.target_device_id)))
    const command: 'in' | 'out' | undefined = focusEdge ? (focusIds.has(edge.target_device_id) ? 'out' : 'in')
      : !agentTarget || !agentPhase || agentPhase === 'thinking' || agentPhase === 'awaiting'
      ? undefined
      : edge.target_device_id === agentTarget ? 'in'
        : (edge.source_device_id === agentTarget || downstream.has(edge.target_device_id)) && (agentPhase === 'executing' || agentPhase === 'verifying') && !isReboot ? 'out'
          : edge.source_device_id === agentTarget && agentPhase === 'planning' ? 'in' : undefined
    const tone = agentPhase === 'failed' ? 'fail' : agentPhase === 'succeeded' ? 'ok' : 'agent'
    return {
      id: `link-${index}`,
      source: edge.source_device_id,
      target: edge.target_device_id,
      type: 'packet',
      data: { broken, paused: paused || reducedMotion, active: highlighted, command, tone },
      animated: false,
      focusable: false,
      style: {
        stroke: broken ? '#9b2828' : command ? (tone === 'fail' ? '#c0584d' : tone === 'ok' ? '#3fbf8f' : '#8b7cf6') : highlighted ? '#80531d' : '#798f83',
        strokeWidth: command ? 3 : highlighted ? 2.5 : 2,
        strokeDasharray: broken ? '6 6' : undefined,
      },
    }
  }), [drawableEdges, nodeById, inspectedId, reducedMotion, paused, agentTarget, agentPhase, isReboot, downstream, focusIds])

  if (nodes.length === 0) {
    return (
      <div className="state-panel">
        <p>No topology is recorded for this service path.</p>
      </div>
    )
  }

  const selectedNode = nodeById.get(inspectedId ?? '')
  const selectedDeviceIsInPath = nodeById.has(selectedDeviceId ?? '')
  const linkSummary = drawableEdges.map((edge) => {
    const source = nodeById.get(edge.source_device_id)?.name ?? edge.source_device_id
    const target = nodeById.get(edge.target_device_id)?.name ?? edge.target_device_id
    return `${source} → ${target}${edge.service_ref ? ` via ${edge.service_ref}` : ''}`
  })

  return (
    <figure className="topology" onKeyDown={(event) => { if (event.key === 'Escape') { clearTimeout(hoverTimer.current); setHoveredDeviceId(undefined); onClearSelection?.() } }}>
      {selectedDeviceId && !selectedDeviceIsInPath && (
        <div className="topology-selection-notice" role="status">
          <p>The selected device is not present in this service path.</p>
          {onClearSelection && <button type="button" className="inline-link" onClick={onClearSelection}>Clear device selection</button>}
        </div>
      )}

      <div className="topology-layout">
        <div className="topology-graph">
          <div className="network-canvas-heading"><span>Network stream</span><span>{nodes.length} devices · {drawableEdges.length} links</span></div>
          <div className="network-canvas-hint">Hover to inspect · Select to pin · Drag to pan</div>
          {agentActivity && <div className={`agent-hud agent-hud--${agentActivity.phase}`} role="status" aria-live="polite">
            <span className="agent-hud__orb" aria-hidden="true"><span /><span /><span /></span>
            <div>
              <strong>Agent · {AGENT_PHASE_LABEL[agentActivity.phase]}</strong>
              <p>{agentActivity.label}</p>
              {agentActivity.step && <p className="agent-hud__step">› {agentActivity.step}</p>}
              {agentActivity.progress !== undefined && (agentActivity.phase === 'executing' || agentActivity.phase === 'verifying') &&
                <span className="agent-hud__progress" aria-hidden="true"><span style={{ width: `${Math.round(agentActivity.progress * 100)}%` }} /></span>}
            </div>
          </div>}
          <ReactFlow
            nodes={flowNodes}
            edges={flowEdges}
            nodeTypes={nodeTypes}
            edgeTypes={edgeTypes}
            onNodesChange={onNodesChange}
            onNodeMouseEnter={(_, node) => inspect(node.id)}
            onNodeMouseLeave={leave}
            onPaneClick={() => { setHoveredDeviceId(undefined); onClearSelection?.() }}
            onNodeClick={(_, node) => onSelectDevice?.(node.id)}
            fitView
            fitViewOptions={{ padding: 0.18, minZoom: 0.65, maxZoom: 1 }}
            minZoom={0.2}
            maxZoom={1.5}
            nodesDraggable={false}
            nodesConnectable={false}
            nodesFocusable={false}
            edgesFocusable={false}
            zoomOnScroll={false}
            proOptions={{ hideAttribution: true }}
           ><FitCanvas /><Background variant={BackgroundVariant.Dots} gap={20} size={1.4} color="#cbd5e1" /><Controls showInteractive={false} /></ReactFlow>
          {selectedNode && <TopologyInspector node={selectedNode} edges={drawableEdges} facts={facts}
            nodeNames={new Map(nodes.map((item) => [item.device_id, item.name]))}
            icon={deviceIcon(resolveDeviceType(selectedNode))}
            kindLabel={deviceKindLabel(resolveDeviceType(selectedNode))}
            liveMetric={metrics?.[selectedNode.device_id]}
            onPointerEnter={() => clearTimeout(hoverTimer.current)}
            onPointerLeave={leave}
            onClose={() => { setHoveredDeviceId(undefined); onClearSelection?.() }} />}
          <div className="network-canvas-footer">
            <span><i /> Packet flow <i className="is-interrupted" /> Interrupted</span>
            <button type="button" onClick={() => setPaused((value) => !value)} disabled={reducedMotion} aria-pressed={paused || reducedMotion}>{reducedMotion ? 'Reduced motion' : paused ? 'Resume packets' : 'Pause packets'}</button>
          </div>
          <p className="network-simulation-label">Packet animation illustrates recorded links, not live traffic.</p>
        </div>
      </div>
      {actionStage && actionStage.state !== 'upcoming' && <div className={`network-operation network-operation--${actionStage.state}`} role="status">
        <span className="network-operation__indicator" />
        <div><strong>{actionStage.state === 'current' ? 'Device action' : actionStage.state === 'complete' ? 'Action completed' : 'Action needs attention'}</strong><p>{actionStage.detail}</p></div>
        {actionDeviceId && <span>{nodeById.get(actionDeviceId)?.name ?? 'Target outside this path'}</span>}
      </div>}

      <div className="topology-devices">
        <p className="section-label">Devices</p>
        <ol className="topology-device-list" aria-label="Devices">
          {nodes.map((node) => {
            const selected = selectedDeviceId === node.device_id
            const kind = resolveDeviceType(node)
            const Icon = deviceIcon(kind)
            return (
              <li key={node.device_id} className={`topology-device is-${statusTone(node.status)}`}>
                {(() => {
                  const content = <>
                    <span className="topology-device__icon" aria-hidden="true"><Icon size={20} weight="duotone" /></span>
                    <span className="topology-device__text">
                      <span className="topology-device__name">{node.name}</span>
                      <span className="topology-device__meta">{deviceKindLabel(kind)} · <span className="tabular">{node.device_ref}</span></span>
                    </span>
                    <span className="topology-device__status">{deviceStatusLabel(node.status)}</span>
                  </>
                  return onSelectDevice ? (
                    <button type="button" className="topology-device__button" aria-pressed={selected}
                      onMouseEnter={() => inspect(node.device_id)} onMouseLeave={leave}
                      onFocus={() => inspect(node.device_id)} onBlur={leave} onClick={() => onSelectDevice(node.device_id)}>{content}</button>
                  ) : <div className="topology-device__button">{content}</div>
                })()}
              </li>
            )
          })}
        </ol>
      </div>

      {drawableEdges.length > 0 ? (
        <>
          <ul aria-label="Connections" className="sr-only topology-connections">
            {linkSummary.map((summary) => <li key={summary}>{summary}</li>)}
          </ul>

        </>
      ) : (
        <p className="muted-note">No connections are recorded.</p>
      )}
      <figcaption className="sr-only">
        {`Topology: ${nodes.length} devices, ${drawableEdges.length} connections.${serviceRef ? ` Carried over ${serviceRef}.` : ''}`}
      </figcaption>
    </figure>
  )
}
