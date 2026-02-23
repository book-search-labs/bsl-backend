import { createRequestContext, resolveApiMode, resolveBffBaseUrl, resolveCommerceBaseUrl, routeRequest } from './client'
import { fetchJson, type JsonInit } from './http'

export type OrderSummary = {
  order_id: number
  order_no?: string
  status: string
  total_amount: number
  currency: string
  shipping_fee?: number
  shipping_mode?: 'STANDARD' | 'FAST' | string
  item_count?: number
  primary_item_title?: string | null
  primary_item_author?: string | null
  primary_item_material_id?: string | null
  primary_item_sku_id?: number | null
  created_at: string
}

export type OrderItem = {
  order_item_id: number
  sku_id: number
  qty: number
  unit_price: number
  item_amount: number
  status?: string
  material_id?: string | null
  title?: string | null
  subtitle?: string | null
  author?: string | null
  publisher?: string | null
  issued_year?: number | null
  seller_name?: string | null
  format?: string | null
  edition?: string | null
  pack_size?: number | null
}

export type OrderDetail = {
  order: OrderSummary & {
    shipping_snapshot_json?: unknown
    payment_method?: string | null
  }
  items: OrderItem[]
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

async function callApi<T>(path: string, init?: JsonInit) {
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
  shippingMode?: 'STANDARD' | 'FAST'
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
