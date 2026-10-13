import type { ComponentType } from 'react'
import type { IconProps } from '@phosphor-icons/react'
import type { TopologyNode, TopologyEdge } from '../../lib/api/topology'
import type { EntityFact } from '../../lib/api/tickets'
import { EntityFactsPanel } from '../work/EntityFactsPanel'

const fieldGroups = [
  { title: 'Identity', keys: ['id', 'customer_id', 'device_ref', 'device_type', 'name', 'friendly_name', 'status', 'manufacturer', 'brand', 'cloud_device_type', 'platform', 'login_id'] },
  { title: 'Connection', keys: ['mac_address', 'ip_address', 'parent_mac', 'link_type', 'last_seen', 'rssi', 'rx_rate', 'tx_rate'] },
  { title: '2.4 GHz radio', keys: ['ssid_2_4ghz', 'channel_2_4ghz', 'antenna_2_4ghz', 'protocol_2_4ghz', 'bandwidth_2_4ghz'] },
  { title: '5 GHz radio', keys: ['ssid_5ghz', 'channel_5ghz', 'antenna_5ghz', 'protocol_5ghz', 'bandwidth_5ghz'] },
]
const groupedKeys = new Set(fieldGroups.flatMap((group) => group.keys))
const fieldLabel = (key: string) => key.replace(/_/g, ' ').replace(/\b(id|ip|mac|ssid|rssi|rx|tx)\b/gi, (word) => word.toUpperCase()).replace(/^\w/, (letter) => letter.toUpperCase())

function fieldValue(value: unknown): string {
  if (value === null || value === undefined || value === '') return 'Not recorded'
  if (typeof value === 'object') return JSON.stringify(value, null, 2)
  return String(value)
}

const present = (value: unknown) => value !== null && value !== undefined && value !== ''

function signalGrade(rssi: number) {
  if (rssi >= -55) return { bars: 4, label: 'Excellent', tone: 'ok' }
  if (rssi >= -67) return { bars: 3, label: 'Good', tone: 'ok' }
  if (rssi >= -75) return { bars: 2, label: 'Fair', tone: 'warn' }
  return { bars: 1, label: 'Weak', tone: 'bad' }
}

function relativeTime(value: unknown): string | undefined {
  if (typeof value !== 'string') return undefined
  const time = Date.parse(value)
  if (Number.isNaN(time)) return value
  const minutes = Math.round((Date.now() - time) / 60000)
  if (Math.abs(minutes) < 60) return `${Math.abs(minutes)} min ago`
  const hours = Math.round(minutes / 60)
  if (Math.abs(hours) < 48) return `${Math.abs(hours)} h ago`
  return new Date(time).toLocaleDateString()
}

type InspectorProps = {
  node: TopologyNode
  edges: TopologyEdge[]
  facts: EntityFact[]
  nodeNames?: Map<string, string>
  icon?: ComponentType<IconProps>
  kindLabel?: string
  liveMetric?: { text: string; tone: string }
  onClose?: () => void
  onPointerEnter?: () => void
  onPointerLeave?: () => void
}

export function TopologyInspector({ node, edges, facts, nodeNames, icon: Icon, kindLabel, liveMetric, onClose, onPointerEnter, onPointerLeave }: InspectorProps) {
  const status = node.status.charAt(0).toUpperCase() + node.status.slice(1).replace(/_/g, ' ')
  const deviceFacts = facts.filter((fact) => fact.entity_type === 'device' && fact.entity_id === node.device_id && !fact.is_sensitive)
  const services = [...new Set([node.service_ref, ...edges.filter((edge) => edge.source_device_id === node.device_id || edge.target_device_id === node.device_id).map((edge) => edge.service_ref)].filter(Boolean))]
  const deviceData: Record<string, unknown> = {
    id: node.device_id, device_ref: node.device_ref, device_type: node.device_type,
    name: node.name, status: node.status, ...node.device_data,
  }
  const groups = [...fieldGroups, { title: 'Additional data', keys: Object.keys(deviceData).filter((key) => !groupedKeys.has(key)) }]
  const rssi = typeof deviceData.rssi === 'number' ? deviceData.rssi : null
  const grade = rssi !== null ? signalGrade(rssi) : null
  const upstream = edges.filter((edge) => edge.target_device_id === node.device_id).map((edge) => nodeNames?.get(edge.source_device_id) ?? edge.source_device_id)
  const downstream = edges.filter((edge) => edge.source_device_id === node.device_id).length
  const tone = /offline|unreachable/i.test(node.status) ? 'bad' : /online/i.test(node.status) ? 'ok' : 'warn'
  const tiles: { label: string; value: string; tone?: string }[] = []
  if (present(deviceData.link_type)) tiles.push({ label: 'Link', value: String(deviceData.link_type) })
  if (present(deviceData.tx_rate) || present(deviceData.rx_rate)) tiles.push({ label: 'Link rate', value: `${deviceData.tx_rate ?? '—'} / ${deviceData.rx_rate ?? '—'} Mbps` })
  if (present(deviceData.channel_2_4ghz)) tiles.push({ label: '2.4 GHz ch', value: String(deviceData.channel_2_4ghz) })
  if (present(deviceData.channel_5ghz)) tiles.push({ label: '5 GHz ch', value: String(deviceData.channel_5ghz) })
  if (present(deviceData.ip_address)) tiles.push({ label: 'IP', value: String(deviceData.ip_address) })
  if (present(deviceData.mac_address)) tiles.push({ label: 'MAC', value: String(deviceData.mac_address) })
  if (downstream > 0) tiles.push({ label: 'Clients', value: String(downstream) })
  const seen = relativeTime(deviceData.last_seen)
  if (seen) tiles.push({ label: 'Last seen', value: seen })
  const vendor = [deviceData.manufacturer, deviceData.brand, deviceData.platform].filter(present).map(String)

  return <aside className="topology-inspector" aria-label="Device details" tabIndex={0} onPointerEnter={onPointerEnter} onPointerLeave={onPointerLeave} onFocus={onPointerEnter} onBlur={(event) => { if (!event.currentTarget.contains(event.relatedTarget)) onPointerLeave?.() }}>
    {onClose && <button type="button" className="network-inspector-close" aria-label="Close device details" onClick={onClose}>×</button>}
    <header className="inspector-head">
      {Icon && <span className={`inspector-head__icon is-${tone}`} aria-hidden="true"><Icon size={30} weight="fill" /></span>}
      <div>
        <p className="section-label">{kindLabel ?? 'Device details'}</p>
        <h4>{node.name}</h4>
        <p className="inspector-head__sub"><span className={`inspector-status is-${tone}`}>{status}</span>{vendor.length > 0 && <span>{vendor.join(' · ')}</span>}</p>
      </div>
    </header>
    {liveMetric && <p className={`inspector-live is-${liveMetric.tone}`}><span aria-hidden="true" />Agent reading: <b>{liveMetric.text}</b></p>}
    {grade && rssi !== null && <div className={`inspector-signal is-${grade.tone}`}>
      <span className="signal-bars" aria-hidden="true">{[1, 2, 3, 4].map((bar) => <i key={bar} className={bar <= grade.bars ? 'is-on' : undefined} />)}</span>
      <div><strong>{rssi} dBm</strong><small>{grade.label} signal</small></div>
      <span className="inspector-signal__meter" aria-hidden="true"><span style={{ width: `${Math.min(100, Math.max(4, (rssi + 95) * 2))}%` }} /></span>
    </div>}
    {tiles.length > 0 && <dl className="inspector-tiles">{tiles.map((tile) => <div key={tile.label}><dt>{tile.label}</dt><dd>{tile.value}</dd></div>)}</dl>}
    <dl className="data-list">
      <div className="data-row"><dt>Reference</dt><dd>{node.device_ref}</dd></div>
      <div className="data-row"><dt>Type</dt><dd>{node.device_type}</dd></div>
      <div className="data-row"><dt>Status</dt><dd>{status}</dd></div>
      {upstream.length > 0 && <div className="data-row"><dt>Connected to</dt><dd>{upstream.join(', ')}</dd></div>}
      <div className="data-row"><dt>Connected services</dt><dd>{services.join(', ') || 'Not recorded'}</dd></div>
    </dl>
    <details className="inspector-all">
      <summary>All recorded fields</summary>
      {groups.filter((group) => group.keys.length > 0).map((group) => <div className="facts-group" key={group.title}>
        <h5 className="facts-heading">{group.title}</h5>
        <dl className="data-list">{group.keys.map((key) => <div className="data-row" key={key}>
          <dt title={key}>{fieldLabel(key)}</dt>
          <dd className={typeof deviceData[key] === 'object' && deviceData[key] !== null ? 'topology-inspector__json' : undefined}>{fieldValue(deviceData[key])}</dd>
        </div>)}</dl>
      </div>)}
    </details>
    {[...new Set(deviceFacts.map((fact) => fact.group_key))].map((group) => <EntityFactsPanel key={group} facts={deviceFacts} groupKey={group} />)}
  </aside>
}
