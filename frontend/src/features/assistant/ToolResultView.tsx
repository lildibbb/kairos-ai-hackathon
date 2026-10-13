import type { ToolResult } from '../../lib/api/tools'

type Row = Record<string, unknown>
const rows = (value: unknown): Row[] => (Array.isArray(value) ? (value as Row[]) : [])
const text = (value: unknown) => (value === null || value === undefined ? '—' : String(value))

function Spectrum({ bands }: { bands: Row }) {
  return <div className="result-spectrum">
    {(['2.4', '5'] as const).map((band) => {
      const info = bands[band] as Row | undefined
      if (!info) return null
      return <figure key={band} className="result-spectrum__band" aria-label={`${band} GHz channel utilisation`}>
        <figcaption><strong>{band} GHz</strong><span>now ch {text(info.current)} · best ch {text(info.recommended)}</span></figcaption>
        <div className="result-spectrum__bars">
          {rows(info.channels).map((row, index) => {
            const utilization = Number(row.utilization) || 0
            const state = row.channel === info.current ? 'current' : row.channel === info.recommended ? 'best' : 'other'
            return <div key={String(row.channel)} className={`result-spectrum__bar is-${state}`} title={`Channel ${row.channel}: ${utilization}% busy, ${row.networks} networks`}>
              <span style={{ height: `${Math.max(4, utilization)}%`, animationDelay: `${index * 35}ms` }} />
              <small>{text(row.channel)}</small>
            </div>
          })}
        </div>
      </figure>
    })}
    <p className="result-legend"><i className="is-current" /> Current <i className="is-best" /> Recommended</p>
  </div>
}

function PathHops({ data }: { data: Row }) {
  const hops = rows(data.hops)
  const max = Math.max(...hops.map((hop) => Number(hop.latency_ms) || 0), 1)
  return <div className="result-path">
    <ol>
      {hops.map((hop, index) => <li key={`${hop.name}-${index}`} className={`result-path__hop is-${text(hop.status)}`} style={{ animationDelay: `${index * 90}ms` }}>
        <span className="result-path__dot" aria-hidden="true" />
        <div className="result-path__text"><strong>{text(hop.name)}</strong><small>{text(hop.note)}</small></div>
        <div className="result-path__latency">
          <span className="result-path__meter"><span style={{ width: `${((Number(hop.latency_ms) || 0) / max) * 100}%` }} /></span>
          <b>{text(hop.latency_ms)} ms</b>{Number(hop.loss_pct) > 0 && <em>{text(hop.loss_pct)}% loss</em>}
        </div>
      </li>)}
    </ol>
    <p className="result-summary-line">Total <b>{text(data.total_ms)} ms</b> · bottleneck <b>{text(data.bottleneck)}</b></p>
  </div>
}

function signalBars(rssi: number | null) {
  if (rssi === null) return 4
  return rssi >= -55 ? 4 : rssi >= -67 ? 3 : rssi >= -75 ? 2 : 1
}

function Survey({ clients }: { clients: Row[] }) {
  if (clients.length === 0) return <p className="muted-note">No wireless clients.</p>
  return <ul className="result-survey">
    {clients.map((client, index) => {
      const rssi = typeof client.rssi === 'number' ? client.rssi : null
      const bars = signalBars(rssi)
      return <li key={text(client.device_id)} className={`result-survey__row is-${text(client.quality)}`} style={{ animationDelay: `${index * 60}ms` }}>
        <span className="signal-bars" aria-label={`${bars} of 4 bars`}>{[1, 2, 3, 4].map((bar) => <i key={bar} className={bar <= bars ? 'is-on' : undefined} />)}</span>
        <div><strong>{text(client.name)}</strong><small>{client.band ? `${client.band} GHz` : 'wired'} · {rssi ?? '—'} dBm{client.rate_mbps ? ` · ${client.rate_mbps} Mbps` : ''}</small>
          {typeof client.advice === 'string' && <small className="result-survey__advice">{client.advice}</small>}</div>
        <span className="result-survey__grade">{text(client.quality)}</span>
      </li>
    })}
  </ul>
}

function Diff({ changes }: { changes: Row[] }) {
  if (changes.length === 0) return null
  return <table className="result-diff">
    <thead><tr><th scope="col">Setting</th><th scope="col">Before</th><th scope="col">After</th></tr></thead>
    <tbody>{changes.map((change, index) => <tr key={`${change.field}-${index}`} style={{ animationDelay: `${index * 80}ms` }}>
      <th scope="row">{text(change.field)}</th><td className="is-before">{text(change.before)}</td><td className="is-after">{text(change.after)}</td>
    </tr>)}</tbody>
  </table>
}

function Metrics({ items }: { items: Row[] }) {
  return <div className="result-metrics">
    {items.map((item) => <div key={text(item.label)} className={item.warn ? 'is-warn' : undefined}>
      <small>{text(item.label)}</small><strong>{text(item.value)}{item.value !== null && item.value !== undefined ? text(item.unit) : ''}</strong>
    </div>)}
  </div>
}

/** Structured tool output: spectrum, hop path, signal survey, before/after diff or counters. */
export function ToolResultView({ result }: { result?: ToolResult | null }) {
  const data = (result?.data ?? {}) as Row
  switch (data.kind) {
    case 'spectrum': return <Spectrum bands={(data.bands ?? {}) as Row} />
    case 'path': return <PathHops data={data} />
    case 'survey': return <Survey clients={rows(data.clients)} />
    case 'clients': return <Survey clients={rows(data.clients).map((client) => ({ ...client, band: client.band === 'wired' ? null : client.band }))} />
    case 'status': return <Metrics items={rows(data.metrics)} />
    case 'speed': return <Metrics items={[
      { label: 'Download', value: Math.round(Number(data.download_mbps)), unit: ' Mbps' },
      { label: 'Upload', value: Math.round(Number(data.upload_mbps)), unit: ' Mbps' },
      { label: 'Latency', value: data.latency_ms, unit: ' ms' },
    ]} />
    case 'diff': return <>
      <Diff changes={rows(data.changes)} />
      {Boolean(data.bands) && <Spectrum bands={data.bands as Row} />}
    </>
    default: return null
  }
}
