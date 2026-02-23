import { createRequestContext, resolveApiMode, resolveBffBaseUrl, resolveCommerceBaseUrl, routeRequest } from './client'
import { fetchJson, type JsonInit } from './http'

export type Shipment = {
  shipment_id: number
  order_id: number
  status: string
  carrier?: string | null
  tracking_no?: string | null
  shipped_at?: string | null
  delivered_at?: string | null
}

export type ShipmentEvent = {
  event_type: string
  event_time: string
  payload_json?: unknown
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

export async function getShipmentsByOrder(orderId: number) {
  const response = await callApi<{ items: Shipment[] }>(`/api/v1/shipments/by-order/${orderId}`, { method: 'GET' })
  return response.items ?? []
}

export async function getShipment(shipmentId: number) {
  const response = await callApi<{ shipment: Shipment; events: ShipmentEvent[] }>(`/api/v1/shipments/${shipmentId}`, {
    method: 'GET',
  })
  return response
}
