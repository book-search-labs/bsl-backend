import { createRequestContext, resolveApiMode, resolveBffBaseUrl, resolveCommerceBaseUrl, routeRequest } from './client'
import { fetchJson } from './http'

type CartItem = {
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
}

type CartTotals = {
  subtotal: number
  shipping_fee: number
  discount: number
  total: number
}

type Cart = {
  cart_id: number
  user_id: number
  status: string
  items: CartItem[]
  totals: CartTotals
}

type CartResponse = {
  cart: Cart
}

function joinUrl(base: string, path: string) {
  return `${base.replace(/\/$/, '')}${path}`
}

async function callBff<T>(path: string, init?: RequestInit) {
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
