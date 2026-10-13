import { useEffect, useMemo, useState } from 'react'
import { CheckCircle, EnvelopeSimple, Lightning, ShoppingCart, WarningCircle, WifiHigh, ArrowsClockwise, Check, Broadcast } from '@phosphor-icons/react'
import { Button } from '../../components/ui/button'
import { Select, SelectItem } from '../../components/ui/select'
import { TicketsApiError } from '../../lib/api/tickets'
import { fetchOrders, submitOrder, type OrderProduct, type ServiceOrder, type TicketSummary } from '../../lib/api/ticketSummary'

const ACTION_ICON = { mesh: WifiHigh, speed: Lightning, reboot: ArrowsClockwise, replace: Broadcast } as const

/** Vendor product photos in public/products, matched on the product.csv name. */
function productImage(name: string): string | undefined {
  const key = name.toLowerCase()
  if (key.includes('be65')) return '/products/deco-be65.jpg'
  if (key.includes('xe75')) return '/products/deco-xe75.png'
  if (key.includes('ax3000')) return '/products/combo-ax3000.jpg'
  return undefined
}

function priceParts(product: OrderProduct): { amount: string; unit: string } {
  if (product.monthly_price_myr != null) return { amount: `RM ${product.monthly_price_myr.toFixed(0)}`, unit: '/ month' }
  if (product.one_time_price_myr) return { amount: `RM ${product.one_time_price_myr.toFixed(0)}`, unit: 'one-time' }
  return { amount: 'Free', unit: 'no charge' }
}

function emailNote(order: ServiceOrder) {
  if (order.email_status === 'sent') return `Confirmation e-mailed to ${order.email_recipient}`
  if (order.email_status === 'failed') return `E-mail failed: ${order.email_error ?? 'SMTP error'}`
  return `E-mail not sent: ${order.email_error ?? 'SMTP is not configured'}`
}

function speedLabel(mbps: number) {
  return mbps >= 1000 ? `${mbps / 1000} Gbps` : `${mbps} Mbps`
}

type Props = { ticketId: string; token: string; summary: TicketSummary; layout?: 'wide' | 'inline' }

/** summarize.py order actions as product cards from product.csv, with ordering and e-mail confirmation. */
export function ProductRecommendations({ ticketId, token, summary, layout = 'wide' }: Props) {
  const [action, setAction] = useState(summary.order_options[0]?.action ?? '')
  const option = useMemo(() => summary.order_options.find((item) => item.action === action), [action, summary.order_options])
  const [productCode, setProductCode] = useState(option?.products[0]?.code ?? '')
  const product = option?.products.find((item) => item.code === productCode)
  const [notes, setNotes] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')
  const [orders, setOrders] = useState<ServiceOrder[]>([])
  const [latest, setLatest] = useState<ServiceOrder>()
  const currentPrice = summary.plan_price_myr ?? null
  const currentSpeed = useMemo(() => {
    const match = summary.plan_name?.match(/(\d+(?:\.\d+)?)\s*(G|M)bps/i)
    return match ? Number(match[1]) * (match[2].toUpperCase() === 'G' ? 1000 : 1) : null
  }, [summary.plan_name])

  useEffect(() => {
    let active = true
    void fetchOrders(ticketId, token).then((loaded) => { if (active) setOrders(loaded) }).catch(() => undefined)
    return () => { active = false }
  }, [ticketId, token])

  const chooseAction = (value: string) => {
    setAction(value)
    setProductCode(summary.order_options.find((item) => item.action === value)?.products[0]?.code ?? '')
    setLatest(undefined)
  }

  const submit = async () => {
    if (!product || submitting) return
    setSubmitting(true)
    setError('')
    setLatest(undefined)
    try {
      const order = await submitOrder(ticketId, { action, productCode: product.code, notes }, token)
      setLatest(order)
      setOrders((current) => [order, ...current])
      setNotes('')
    } catch (caught) {
      setError(caught instanceof TicketsApiError ? caught.message : 'The order could not be submitted.')
    } finally {
      setSubmitting(false)
    }
  }

  if (summary.order_options.length === 0) return null
  const maxSpeed = Math.max(...(option?.products ?? []).map((item) => item.speed_mbps ?? 0), currentSpeed ?? 0, 1)
  const selectedPrice = product ? priceParts(product) : null
  const delta = product?.monthly_price_myr != null && action === 'speed' && currentPrice != null ? product.monthly_price_myr - currentPrice : null

  return <section className={`product-reco product-reco--${layout}`} aria-label="Product recommendation">
    <header className="product-reco__header">
      <div>
        <p className="section-label">Product recommendation · summarize.py</p>
        <h3>Recommended for this customer</h3>
        {summary.product_recommendation && <p className="product-reco__why">{summary.product_recommendation}</p>}
      </div>
      {summary.plan_name && <div className="product-reco__current">
        <small>Current plan</small>
        <strong>{summary.plan_name}</strong>
        {currentPrice != null && <span>RM {currentPrice.toFixed(0)} / month</span>}
      </div>}
    </header>

    <form className="product-reco__body" onSubmit={(event) => { event.preventDefault(); void submit() }} aria-label="Submit an order">
      <div className="product-reco__catalog">
        <label className="product-reco__action"><span>Action</span>
          <Select value={action} onValueChange={chooseAction} aria-label="Order action" disabled={submitting}>
            {summary.order_options.map((item) => <SelectItem key={item.action} value={item.action}>{item.label}</SelectItem>)}
          </Select>
        </label>
        <div className="product-reco__grid" role="radiogroup" aria-label="Order product">
          {(option?.products ?? []).map((item, index) => {
            const selected = item.code === productCode
            const price = priceParts(item)
            const Icon = ACTION_ICON[action as keyof typeof ACTION_ICON] ?? ShoppingCart
            const image = productImage(item.name)
            return <button type="button" role="radio" aria-checked={selected} key={item.code} disabled={submitting}
              className={`product-card${selected ? ' is-selected' : ''}`} style={{ animationDelay: `${index * 60}ms` }}
              onClick={() => { setProductCode(item.code); setLatest(undefined) }}>
              <span className="product-card__top">
                <span className="product-card__icon" aria-hidden="true"><Icon size={20} weight="duotone" /></span>
                {item.badge && <span className={`product-card__badge is-${item.badge.toLowerCase().replace(/\s+/g, '-')}`}>{item.badge}</span>}
                <span className="product-card__check" aria-hidden="true">{selected && <Check size={12} weight="bold" />}</span>
              </span>
              {image && <span className="product-card__media"><img src={image} alt="" loading="lazy" /></span>}
              <strong className="product-card__name">{item.name}</strong>
              {item.speed_mbps != null && <span className="product-card__speed">
                <span className="product-card__speed-bar"><span style={{ width: `${(item.speed_mbps / maxSpeed) * 100}%` }} />
                  {currentSpeed != null && <i style={{ left: `${(currentSpeed / maxSpeed) * 100}%` }} title="Current plan" />}</span>
                <small>{speedLabel(item.speed_mbps)}{currentSpeed ? ` · ${(item.speed_mbps / currentSpeed).toFixed(1)}× today` : ''}</small>
              </span>}
              {item.features.length > 0 && <ul className="product-card__features">{item.features.map((feature) => <li key={feature}><CheckCircle size={12} weight="fill" aria-hidden="true" />{feature}</li>)}</ul>}
              <span className="product-card__price"><b>{price.amount}</b><small>{price.unit}</small></span>
            </button>
          })}
        </div>
      </div>

      <aside className="product-reco__checkout" aria-label="Order summary">
        <p className="section-label">Order summary</p>
        {product ? <>
          {productImage(product.name) && <img className="product-reco__photo" src={productImage(product.name)} alt={product.name} />}
          <strong className="product-reco__selected">{product.name}</strong>
          <p className="product-reco__desc">{product.description}</p>
          <div className="product-reco__total"><b>{selectedPrice?.amount}</b><span>{selectedPrice?.unit}</span></div>
          {delta != null && <p className={`product-reco__delta ${delta > 0 ? 'is-up' : 'is-down'}`}>{delta > 0 ? '+' : '−'}RM {Math.abs(delta).toFixed(0)} / month vs current plan</p>}
        </> : <p className="muted-note">Pick a product.</p>}
        <label className="order-form__field"><span>Notes for the customer (optional)</span>
          <input value={notes} onChange={(event) => setNotes(event.target.value)} maxLength={500} placeholder="e.g. Install the node in the upstairs hallway" disabled={submitting} />
        </label>
        <Button type="submit" className="process-button order-form__submit" disabled={!product || submitting}>
          <ShoppingCart size={16} aria-hidden="true" />{submitting ? 'Submitting order and sending e-mail…' : 'Submit order'}
        </Button>
        {error && <p className="form-error" role="alert">{error}</p>}
        {latest && <div className={`order-result order-result--${latest.email_status}`} role="status">
          {latest.email_status === 'sent' ? <CheckCircle size={18} weight="fill" aria-hidden="true" /> : <WarningCircle size={18} weight="fill" aria-hidden="true" />}
          <div><strong>Order submitted: {latest.product_name}</strong><p><EnvelopeSimple size={13} aria-hidden="true" /> {emailNote(latest)}</p></div>
        </div>}
        {orders.length > 0 && <details className="order-history"><summary>Orders on this ticket ({orders.length})</summary><ul>
          {orders.map((order) => <li key={order.id}><span>{order.product_name}</span><span className={`order-email order-email--${order.email_status}`}>{order.email_status === 'sent' ? 'E-mailed' : order.email_status === 'failed' ? 'E-mail failed' : 'Recorded'}</span></li>)}
        </ul></details>}
      </aside>
    </form>
  </section>
}
