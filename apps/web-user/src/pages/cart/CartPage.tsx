import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'

import { clearCart, getCart, removeCartItem, updateCartItem } from '../../api/cart'

export default function CartPage() {
  const [cart, setCart] = useState<Awaited<ReturnType<typeof getCart>> | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)

  useEffect(() => {
    let active = true
    setIsLoading(true)
    getCart()
      .then((data) => {
        if (!active) return
        setCart(data)
        setErrorMessage(null)
      })
      .catch((err) => {
        if (!active) return
        setErrorMessage(err instanceof Error ? err.message : 'Failed to load cart')
      })
      .finally(() => {
        if (active) setIsLoading(false)
      })
    return () => {
      active = false
    }
  }, [])

  const totalItems = useMemo(() => cart?.items?.reduce((sum, item) => sum + item.qty, 0) ?? 0, [cart])

  const handleQtyChange = async (cartItemId: number, qty: number) => {
    if (!cart) return
    try {
      const next = await updateCartItem(cartItemId, { qty })
      setCart(next)
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : 'Failed to update item')
    }
  }

  const handleRemove = async (cartItemId: number) => {
    if (!cart) return
    try {
      const next = await removeCartItem(cartItemId)
      setCart(next)
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : 'Failed to remove item')
    }
  }

  const handleClear = async () => {
    if (!cart) return
    try {
      const next = await clearCart()
      setCart(next)
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : 'Failed to clear cart')
    }
  }

  if (isLoading) {
    return (
      <div className="container py-5">
        <div className="card shadow-sm p-4">Loading cart...</div>
      </div>
    )
  }

  if (errorMessage) {
    return (
      <div className="container py-5">
        <div className="alert alert-danger">{errorMessage}</div>
      </div>
    )
  }

  if (!cart || cart.items.length === 0) {
    return (
      <div className="container py-5">
        <div className="cart-empty text-center p-5">
          <h2 className="mb-3">Your cart is empty</h2>
          <p className="text-muted mb-4">Add a few titles to start your next reading journey.</p>
          <Link to="/search" className="btn btn-primary">
            Browse books
          </Link>
        </div>
      </div>
    )
  }

  return (
    <div className="container py-5">
      <div className="d-flex flex-column flex-lg-row gap-4">
        <div className="flex-grow-1">
          <div className="d-flex align-items-center justify-content-between mb-3">
            <h2 className="mb-0">Cart</h2>
            <button className="btn btn-outline-secondary btn-sm" onClick={handleClear}>
              Clear all
            </button>
          </div>
          <div className="cart-list d-flex flex-column gap-3">
            {cart.items.map((item) => (
              <div key={item.cart_item_id} className="card cart-item p-3 shadow-sm">
                <div className="d-flex flex-column flex-md-row gap-3 align-items-md-center">
                  <div className="cart-item-meta">
                    <div className="text-muted small">SKU #{item.sku_id}</div>
                    <div className="fw-semibold">Seller #{item.seller_id}</div>
                    {item.price_changed ? <span className="badge text-bg-warning">Price changed</span> : null}
                    {item.out_of_stock ? <span className="badge text-bg-danger ms-2">Low stock</span> : null}
                  </div>
                  <div className="ms-md-auto d-flex flex-column align-items-md-end gap-2">
                    <div className="fw-semibold">₩{(item.unit_price ?? 0).toLocaleString()}</div>
                    <div className="small text-muted">Line total ₩{(item.item_amount ?? 0).toLocaleString()}</div>
                  </div>
                </div>
                <div className="d-flex flex-column flex-sm-row justify-content-between align-items-sm-center mt-3">
                  <div className="cart-qty d-flex align-items-center gap-2">
                    <button
                      className="btn btn-outline-secondary btn-sm"
                      onClick={() => handleQtyChange(item.cart_item_id, Math.max(1, item.qty - 1))}
                    >
                      -
                    </button>
                    <input
                      type="number"
                      className="form-control form-control-sm"
                      value={item.qty}
                      min={1}
                      onChange={(event) => handleQtyChange(item.cart_item_id, Number(event.target.value))}
                    />
                    <button
                      className="btn btn-outline-secondary btn-sm"
                      onClick={() => handleQtyChange(item.cart_item_id, item.qty + 1)}
                    >
                      +
                    </button>
                  </div>
                  <button className="btn btn-link text-danger" onClick={() => handleRemove(item.cart_item_id)}>
                    Remove
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
        <aside className="cart-summary card shadow-sm p-4">
          <h3 className="mb-3">Order Summary</h3>
          <div className="d-flex justify-content-between mb-2">
            <span className="text-muted">Items</span>
            <span>{totalItems}</span>
          </div>
          <div className="d-flex justify-content-between mb-2">
            <span className="text-muted">Subtotal</span>
            <span>₩{cart.totals.subtotal.toLocaleString()}</span>
          </div>
          <div className="d-flex justify-content-between mb-2">
            <span className="text-muted">Shipping</span>
            <span>₩{cart.totals.shipping_fee.toLocaleString()}</span>
          </div>
          <div className="d-flex justify-content-between mb-3">
            <span className="text-muted">Discount</span>
            <span>-₩{cart.totals.discount.toLocaleString()}</span>
          </div>
          <div className="d-flex justify-content-between fs-5 fw-semibold border-top pt-3">
            <span>Total</span>
            <span>₩{cart.totals.total.toLocaleString()}</span>
          </div>
          <Link to="/checkout" className="btn btn-primary w-100 mt-4">
            Proceed to checkout
          </Link>
        </aside>
      </div>
    </div>
  )
}
