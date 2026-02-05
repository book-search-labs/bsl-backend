import { createRequestContext, resolveApiMode, resolveBffBaseUrl, resolveCommerceBaseUrl, routeRequest } from './client'
import { fetchJson } from './http'

export type OrderSummary = {
  order_id: number
  order_no?: string
  status: string
  total_amount: number
  currency: string
  created_at: string
}

export type OrderDetail = {
  order: OrderSummary & {
    shipping_snapshot_json?: unknown
    payment_method?: string | null
  }
  items: Array<{
    order_item_id: number
    sku_id: number
    qty: number
    unit_price: number
    item_amount: number
    status?: string
  }>
  events: Array<{
    event_type?: string
    from_status?: string
    to_status?: string
    created_at?: string
  }>
}

function joinUrl(base: string, path: string) {
  return `${base.replace(/\/$/, '')}${path}`
}

async function callApi<T>(path: string, init?: RequestInit) {
  const requestContext = createRequestContext()
  return routeRequest<T>({
    route: path,
    mode: resolveApiMode(),
    requestContext,
    bff: (context) => fetchJson<T>(joinUrl(resolveBffBaseUrl(), path), { ...init, headers: context.headers }),
    direct: (context) => fetchJson<T>(joinUrl(resolveCommerceBaseUrl(), path), { ...init, headers: context.headers }),
  })
}

export async function createOrder(payload: {
  cartId?: number
  items?: Array<{ skuId: number; sellerId: number; qty: number; offerId?: number; unitPrice?: number }>
  shippingAddressId?: number
  shippingSnapshot?: Record<string, unknown>
  paymentMethod?: string
  idempotencyKey?: string
}) {
  const response = await callApi<{ order: OrderSummary; items: OrderDetail['items']; events: OrderDetail['events'] }>(
    '/api/v1/orders',
    {
      method: 'POST',
      body: payload,
    },
  )
  return response
}

export async function listOrders(limit = 20) {
  const response = await callApi<{ items: OrderSummary[] }>(`/api/v1/orders?limit=${limit}`, { method: 'GET' })
  return response.items ?? []
}

export async function getOrder(orderId: number) {
  const response = await callApi<OrderDetail>(`/api/v1/orders/${orderId}`, { method: 'GET' })
  return response
}

export async function cancelOrder(orderId: number, reason?: string) {
  const response = await callApi<OrderDetail>(`/api/v1/orders/${orderId}/cancel`, {
    method: 'POST',
    body: reason ? { reason } : {},
  })
  return response
}
