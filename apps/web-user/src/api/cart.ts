import { createRequestContext, resolveApiMode, resolveBffBaseUrl, resolveCommerceBaseUrl, routeRequest } from './client'
import { fetchJson, type JsonInit } from './http'

export type CartItem = {
  cart_item_id: number
  sku_id: number
  seller_id: number
  qty: number
  offer_id?: number | null
  unit_price?: number | null
  currency?: string | null
  item_amount?: number
  price_changed?: boolean
  current_price?: number | null
  available_qty?: number | null
  out_of_stock?: boolean | null
  material_id?: string | null
  title?: string | null
  subtitle?: string | null
  author?: string | null
  publisher?: string | null
  issued_year?: number | null
  isbn13?: string | null
  cover_url?: string | null
  seller_name?: string | null
  format?: string | null
  edition?: string | null
  pack_size?: number | null
}

type CartTotals = {
  subtotal: number
  shipping_fee: number
  discount: number
  total: number
}

export type CartLoyalty = {
  point_balance: number
  expected_earn_points: number
  earn_rate_percent: number
}

export type CartBenefits = {
  free_shipping_threshold: number
  bonus_point_threshold: number
  base_shipping_fee: number
  fast_shipping_fee: number
}

export type CartContentItem = {
  item_id: number
  content_type: string
  title: string
  description?: string | null
  sort_order?: number
}

export type Cart = {
  cart_id: number
  user_id: number
  status: string
  items: CartItem[]
  totals: CartTotals
  loyalty?: CartLoyalty
  benefits?: CartBenefits
  promotions?: CartContentItem[]
  notices?: CartContentItem[]
}

type CartResponse = {
  cart: Cart
}

function joinUrl(base: string, path: string) {
  return `${base.replace(/\/$/, '')}${path}`
}

async function callBff<T>(path: string, init?: JsonInit) {
  const requestContext = createRequestContext()
  return routeRequest<T>({
    route: path,
    mode: resolveApiMode(),
    requestContext,
    bff: (context) => fetchJson<T>(joinUrl(resolveBffBaseUrl(), path), { ...init, headers: context.headers }),
    direct: (context) => fetchJson<T>(joinUrl(resolveCommerceBaseUrl(), path), { ...init, headers: context.headers }),
  })
}

export async function getCart() {
  const response = await callBff<CartResponse>('/api/v1/cart', { method: 'GET' })
  return response.cart
}

export async function addCartItem(payload: { skuId: number; sellerId?: number; qty: number }) {
  const response = await callBff<CartResponse>('/api/v1/cart/items', {
    method: 'POST',
    body: payload,
  })
  return response.cart
}

export async function updateCartItem(cartItemId: number, payload: { qty: number }) {
  const response = await callBff<CartResponse>(`/api/v1/cart/items/${cartItemId}`, {
    method: 'PATCH',
    body: payload,
  })
  return response.cart
}

export async function removeCartItem(cartItemId: number) {
  const response = await callBff<CartResponse>(`/api/v1/cart/items/${cartItemId}`, { method: 'DELETE' })
  return response.cart
}

export async function clearCart() {
  const response = await callBff<CartResponse>('/api/v1/cart/items', { method: 'DELETE' })
  return response.cart
}
