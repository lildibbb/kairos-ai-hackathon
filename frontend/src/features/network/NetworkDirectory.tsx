import { useCallback, useEffect, useMemo, useState } from 'react'
import { Scene3D } from '../../components/illustration/Scene3D'
import { Button } from '../../components/ui/button'
import { useAuth } from '../auth/AuthProvider'
import { TicketsApiError } from '../../lib/api/tickets'
import { fetchNetworkCustomers, type NetworkCustomer } from '../../lib/api/customers'

type LoadState = 'loading' | 'ready' | 'error'

function formatDateTime(value?: string | null): string {
  return value ? new Date(value).toLocaleString() : 'Not recorded'
}

function formatContract(customer: NetworkCustomer['customer']): string {
  if (!customer.commitment_start) return 'Not recorded'
  return `${formatDateTime(customer.commitment_start)} to ${formatDateTime(customer.commitment_end)}`
}

export function NetworkDirectory() {
  const { session } = useAuth()
  const token = session?.accessToken ?? ''
  const [records, setRecords] = useState<NetworkCustomer[]>([])
  const [loadState, setLoadState] = useState<LoadState>('loading')
  const [loadError, setLoadError] = useState('')
  const [query, setQuery] = useState('')

  const load = useCallback(async (signal?: AbortSignal) => {
    setLoadState('loading')
    setLoadError('')
    try {
      setRecords(await fetchNetworkCustomers(token, signal))
      setLoadState('ready')
    } catch (error) {
      if (error instanceof DOMException && error.name === 'AbortError') return
      setLoadState('error')
      setLoadError(error instanceof TicketsApiError ? error.message : 'The customer network directory could not be loaded.')
    }
  }, [token])

  useEffect(() => {
    const controller = new AbortController()
    void load(controller.signal)
    return () => controller.abort()
  }, [load])

  const visible = useMemo(() => {
    const normalized = query.trim().toLowerCase()
    if (!normalized) return records
    return records.filter((record) =>
      [
        record.customer.name,
        record.customer.customer_ref,
        record.customer.account_no ?? '',
        record.customer.address,
        ...record.devices.map((device) => device.device_ref),
      ].some((value) => value.toLowerCase().includes(normalized)),
    )
  }, [query, records])

  return (
    <section className="work-section" aria-labelledby="network-directory-heading">
      <div className="work-dashboard-heading">
        <div>
          <p className="section-label">NETWORK DIRECTORY</p>
          <h2 id="network-directory-heading">Customer network</h2>
          <p className="work-intro">
            UniFi account records with the client devices and router health captured for each customer.
          </p>
        </div>
        <Scene3D className="directory-illustration" variant="network" size={190} />
      </div>

      <label className="field network-search">
        <span>Search customers</span>
        <input
          type="search"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Name, account, MAC address"
        />
      </label>

      {loadState === 'loading' && (
        <p className="state-panel" role="status">Loading the customer network directory.</p>
      )}

      {loadState === 'error' && (
        <div className="state-panel">
          <p className="form-error" role="alert">{loadError}</p>
          <Button className="process-button" type="button" onClick={() => void load()}>
            Retry loading directory
          </Button>
        </div>
      )}

      {loadState === 'ready' && records.length === 0 && (
        <p className="state-panel" role="status">
          No UniFi customer records have been imported yet. Load a UniFi dump to populate this directory.
        </p>
      )}

      {loadState === 'ready' && records.length > 0 && visible.length === 0 && (
        <p className="state-panel" role="status">
          No customer matches “{query}”. Clear the search to see all {records.length} records.
        </p>
      )}

      {loadState === 'ready' && visible.length > 0 && (
        <ul className="network-directory-list">
          {visible.map((record) => (
            <li key={record.customer.id}>
              <details className="network-customer">
                <summary>
                  <span className="network-customer-name">{record.customer.name}</span>
                  <span className="network-customer-ref tabular">{record.customer.customer_ref}</span>
                  <span className="network-customer-counts">
                    {record.devices.length} {record.devices.length === 1 ? 'device' : 'devices'} / {record.routers.length} {record.routers.length === 1 ? 'router' : 'routers'}
                  </span>
                </summary>
                <div className="network-customer-body">
                  <dl className="data-list">
                    <div className="data-row"><dt>Service address</dt><dd>{record.customer.address || 'Not recorded'}</dd></div>
                    <div className="data-row"><dt>Account number</dt><dd className="tabular">{record.customer.account_no || 'Not recorded'}</dd></div>
                    <div className="data-row"><dt>Contact number</dt><dd className="tabular">{record.customer.contact_no || 'Not recorded'}</dd></div>
                    <div className="data-row"><dt>Email address</dt><dd>{record.customer.email_address || 'Not recorded'}</dd></div>
                    <div className="data-row"><dt>Contract term</dt><dd>{record.customer.contract_term ? `${record.customer.contract_term} years` : 'Not recorded'}</dd></div>
                    <div className="data-row"><dt>Commitment window</dt><dd>{formatContract(record.customer)}</dd></div>
                  </dl>

                  {record.summary && (
                    <div className="network-customer-summary">
                      <h4>Customer summary</h4>
                      <p>{record.summary.summary}</p>
                      {record.summary.recommendation && <p className="muted-note">{record.summary.recommendation}</p>}
                    </div>
                  )}

                  <h4>Client devices</h4>
                  {record.devices.length === 0 ? (
                    <p className="muted-note">No client devices are recorded for this account.</p>
                  ) : (
                    <ul className="device-list">
                      {record.devices.map((device) => (
                        <li className="device-item" key={device.id}>
                          <span className="device-name">{device.friendly_name || device.name}</span>
                          <span className="device-ref tabular">{device.device_ref}</span>
                          <span className="device-type">{device.device_type || 'unknown'}</span>
                          <span className="device-meta">
                            {device.manufacturer || 'Unknown manufacturer'} / IP {device.ip_address || 'not recorded'} / RSSI {device.rssi ?? 'not recorded'}
                          </span>
                        </li>
                      ))}
                    </ul>
                  )}

                  <h4>Router health</h4>
                  {record.routers.length === 0 ? (
                    <p className="muted-note">No router telemetry is recorded for this account.</p>
                  ) : (
                    <ul className="device-list">
                      {record.routers.map((router) => (
                        <li className="device-item" key={router.serial_number}>
                          <span className="device-name">{router.model || 'Router'}</span>
                          <span className="device-ref tabular">{router.serial_number}</span>
                          <span className="device-type">{router.manufacturer || 'Unknown manufacturer'}</span>
                          <span className="device-meta">
                            CPU {router.cpu_usage_pct ?? 'not recorded'}% / Memory {router.memory_usage_pct ?? 'not recorded'}% / Rx {router.rx_power_dbm ?? 'not recorded'} dBm
                          </span>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              </details>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
