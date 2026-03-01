import { createRequestContext, resolveApiMode, resolveBffBaseUrl, resolveCommerceBaseUrl, routeRequest } from './client'
import { fetchJson, type JsonInit } from './http'

export type Payment = {
  payment_id: number
  order_id: number
  status: string
  amount: number
  currency: string
  method?: string
  provider?: string
  provider_payment_id?: string | null
  failure_reason?: string | null
  checkout_session_id?: string | null
  checkout_url?: string | null
  return_url?: string | null
  webhook_url?: string | null
  expires_at?: string | null
  authorized_at?: string | null
  captured_at?: string | null
  failed_at?: string | null
  canceled_at?: string | null
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

export async function createPayment(payload: {
  orderId: number
  amount: number
  method?: string
  idempotencyKey?: string
  provider?: 'MOCK' | 'LOCAL_SIM' | 'TOSS' | 'STRIPE'
  returnUrl?: string
  webhookUrl?: string
}) {
  const response = await callApi<{ payment: Payment }>('/api/v1/payments', {
    method: 'POST',
    body: payload,
  })
  return response.payment
}

export async function getPayment(paymentId: number) {
  const response = await callApi<{ payment: Payment }>(`/api/v1/payments/${paymentId}`, { method: 'GET' })
  return response.payment
}

export async function mockCompletePayment(paymentId: number, result: 'SUCCESS' | 'FAIL') {
  const response = await callApi<{ payment: Payment }>(`/api/v1/payments/${paymentId}/mock/complete`, {
    method: 'POST',
    body: { result },
  })
  return response.payment
}
