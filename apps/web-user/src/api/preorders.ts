import { createRequestContext, resolveApiMode, resolveBffBaseUrl, resolveCommerceBaseUrl, routeRequest } from './client'
import { fetchJson, type JsonInit } from './http'

export type PreorderItem = {
  preorder_id: number
  doc_id: string
  title_ko: string
  authors: string[]
  publisher_name?: string | null
  issued_year?: number | null
  subtitle?: string | null
  summary?: string | null
  badge?: string | null
  cta_label?: string | null
  preorder_price?: number | null
  preorder_price_label?: string | null
  list_price?: number | null
  list_price_label?: string | null
  discount_rate?: number | null
  preorder_start_at?: string | null
  preorder_end_at?: string | null
  release_at?: string | null
  reservation_limit?: number | null
  reserved_count?: number | null
  remaining?: number | null
  reserved_by_me?: boolean | null
  reserved_qty?: number | null
}

export type PreorderReservation = {
  reservation_id: number
  preorder_id: number
  user_id: number
  qty: number
  status: string
  reserved_price: number
  reserved_price_label?: string | null
  reservation_limit?: number | null
  reserved_total?: number | null
  remaining?: number | null
  note?: string | null
}

type PreordersResponse = {
  items?: PreorderItem[]
  count?: number
  total_count?: number
  limit?: number
}

type ReserveResponse = {
  reservation?: PreorderReservation
}

export type PreordersResult = {
  items: PreorderItem[]
  count: number
  totalCount: number
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

export async function fetchPreorders(limit = 12): Promise<PreordersResult> {
  const params = new URLSearchParams()
  params.set('limit', String(limit))

  const response = await callApi<PreordersResponse>(`/api/v1/home/preorders?${params.toString()}`, { method: 'GET' })
  const items = Array.isArray(response.items) ? response.items : []
  const count = typeof response.count === 'number' ? response.count : items.length
  const totalCount = typeof response.total_count === 'number' ? response.total_count : count

  return {
    items,
    count,
    totalCount,
  }
}

export async function reservePreorder(preorderId: number, qty = 1, note?: string) {
  const response = await callApi<ReserveResponse>(`/api/v1/home/preorders/${preorderId}/reserve`, {
    method: 'POST',
    body: {
      qty,
      note: note && note.trim().length > 0 ? note.trim() : null,
    },
  })
  if (!response.reservation) {
    throw new Error('예약구매 처리에 실패했습니다.')
  }
  return response.reservation
}
