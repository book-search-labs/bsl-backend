import { createRequestContext, resolveApiMode, resolveBffBaseUrl, resolveCommerceBaseUrl, routeRequest } from './client'
import { fetchJson, type JsonInit } from './http'

export type Refund = {
  refund_id: number
  order_id: number
  status: string
  amount: number
  item_amount?: number
  shipping_refund_amount?: number
  return_fee_amount?: number
  policy_code?: string | null
  reason_code?: string
  reason_text?: string
}

export type RefundItem = {
  order_item_id: number
  qty: number
  amount: number
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

export async function createRefund(payload: {
  orderId: number
  items?: Array<{ orderItemId: number; qty: number }>
  reasonCode?: string
  reasonText?: string
  idempotencyKey?: string
}) {
  const response = await callApi<{ refund: Refund; items: RefundItem[] }>('/api/v1/refunds', {
    method: 'POST',
    body: payload,
  })
  return response
}

export async function listRefundsByOrder(orderId: number) {
  const response = await callApi<{ items: Refund[] }>(`/api/v1/refunds/by-order/${orderId}`, { method: 'GET' })
  return response.items ?? []
}

export async function getRefund(refundId: number) {
  const response = await callApi<{ refund: Refund; items: RefundItem[] }>(`/api/v1/refunds/${refundId}`, {
    method: 'GET',
  })
  return response
}
