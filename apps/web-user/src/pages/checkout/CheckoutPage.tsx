import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { createOrder } from '../../api/orders'
import { createAddress, fetchCheckoutSummary, type Address } from '../../api/checkout'

function generateIdempotencyKey() {
  return `idem_${crypto.randomUUID()}`
}

export default function CheckoutPage() {
  const navigate = useNavigate()
  const [summary, setSummary] = useState<Awaited<ReturnType<typeof fetchCheckoutSummary>> | null>(null)
  const [selectedAddress, setSelectedAddress] = useState<number | null>(null)
  const [paymentMethod, setPaymentMethod] = useState('CARD')
  const [loading, setLoading] = useState(true)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)
  const [creatingOrder, setCreatingOrder] = useState(false)
  const [idempotencyKey] = useState(generateIdempotencyKey())

  const [newAddress, setNewAddress] = useState({ name: '', phone: '', zip: '', addr1: '', addr2: '' })

  useEffect(() => {
    let active = true
    setLoading(true)
    fetchCheckoutSummary()
      .then((data) => {
        if (!active) return
        setSummary(data)
        const defaultAddress = data.addresses?.find((address) => Boolean(address.is_default))
        if (defaultAddress) {
          setSelectedAddress(defaultAddress.address_id)
        } else if (data.addresses?.length) {
          setSelectedAddress(data.addresses[0].address_id)
        }
      })
      .catch((err) => {
        if (!active) return
        setErrorMessage(err instanceof Error ? err.message : 'Failed to load checkout')
      })
      .finally(() => {
        if (active) setLoading(false)
      })

    return () => {
      active = false
    }
  }, [])

  const cart = summary?.cart
  const addresses = summary?.addresses ?? []
  const cartIssues = useMemo(() => {
    if (!cart?.items) return []
    return cart.items.filter((item) => item.price_changed || item.out_of_stock)
  }, [cart])

  const handleCreateAddress = async () => {
    if (!newAddress.name || !newAddress.phone) {
      setErrorMessage('Name and phone are required for address')
      return
    }
    try {
      const address = await createAddress({ ...newAddress, isDefault: addresses.length === 0 })
      setSummary((prev) =>
        prev
          ? {
              ...prev,
              addresses: [address, ...prev.addresses],
            }
          : prev,
      )
      setSelectedAddress(address.address_id)
      setNewAddress({ name: '', phone: '', zip: '', addr1: '', addr2: '' })
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : 'Failed to add address')
    }
  }

  const handleSubmit = async () => {
    if (!cart?.cart_id) {
      setErrorMessage('Cart is empty')
      return
    }
    if (!selectedAddress) {
      setErrorMessage('Please select an address')
      return
    }
    if (cartIssues.length > 0) {
      setErrorMessage('Please resolve price or stock changes before ordering')
      return
    }
    setCreatingOrder(true)
    try {
      const response = await createOrder({
        cartId: cart.cart_id,
        shippingAddressId: selectedAddress,
        paymentMethod,
        idempotencyKey,
      })
      const orderId = response.order.order_id
      navigate(`/payment/process/${orderId}`)
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : 'Failed to create order')
    } finally {
      setCreatingOrder(false)
    }
  }

  if (loading) {
    return (
      <div className="container py-5">
        <div className="card p-4">Loading checkout...</div>
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

  if (!cart) {
    return (
      <div className="container py-5">
        <div className="card p-4">No cart found. Return to cart.</div>
      </div>
    )
  }

  return (
    <div className="container py-5">
      <div className="checkout-grid">
        <div className="checkout-main">
          <section className="card p-4 mb-4">
            <h3 className="mb-3">Shipping Address</h3>
            <div className="address-list d-flex flex-column gap-3">
              {addresses.map((address: Address) => (
                <label key={address.address_id} className="address-card d-flex gap-3">
                  <input
                    type="radio"
                    name="address"
                    checked={selectedAddress === address.address_id}
                    onChange={() => setSelectedAddress(address.address_id)}
                  />
                  <div>
                    <div className="fw-semibold">{address.name}</div>
                    <div className="text-muted small">{address.phone}</div>
                    <div className="text-muted small">
                      {[address.addr1, address.addr2, address.zip].filter(Boolean).join(' ')}
                    </div>
                  </div>
                </label>
              ))}
            </div>
            <div className="mt-4">
              <h6>Add new address</h6>
              <div className="row g-2">
                <div className="col-md-6">
                  <input
                    className="form-control"
                    placeholder="Name"
                    value={newAddress.name}
                    onChange={(event) => setNewAddress({ ...newAddress, name: event.target.value })}
                  />
                </div>
                <div className="col-md-6">
                  <input
                    className="form-control"
                    placeholder="Phone"
                    value={newAddress.phone}
                    onChange={(event) => setNewAddress({ ...newAddress, phone: event.target.value })}
                  />
                </div>
                <div className="col-md-4">
                  <input
                    className="form-control"
                    placeholder="Zip"
                    value={newAddress.zip}
                    onChange={(event) => setNewAddress({ ...newAddress, zip: event.target.value })}
                  />
                </div>
                <div className="col-md-8">
                  <input
                    className="form-control"
                    placeholder="Address line 1"
                    value={newAddress.addr1}
                    onChange={(event) => setNewAddress({ ...newAddress, addr1: event.target.value })}
                  />
                </div>
                <div className="col-12">
                  <input
                    className="form-control"
                    placeholder="Address line 2"
                    value={newAddress.addr2}
                    onChange={(event) => setNewAddress({ ...newAddress, addr2: event.target.value })}
                  />
                </div>
              </div>
              <button className="btn btn-outline-primary mt-3" onClick={handleCreateAddress}>
                Save address
              </button>
            </div>
          </section>

          <section className="card p-4 mb-4">
            <h3 className="mb-3">Payment Method</h3>
            <div className="d-flex gap-3">
              {['CARD', 'TRANSFER', 'EASY_PAY'].map((method) => (
                <label key={method} className="payment-option">
                  <input
                    type="radio"
                    name="payment_method"
                    checked={paymentMethod === method}
                    onChange={() => setPaymentMethod(method)}
                  />
                  <span>{method}</span>
                </label>
              ))}
            </div>
          </section>

          {cartIssues.length > 0 ? (
            <div className="alert alert-warning">
              Some items changed price or have limited stock. Please review your cart before ordering.
            </div>
          ) : null}
        </div>

        <aside className="checkout-summary card p-4">
          <h3 className="mb-3">Order Summary</h3>
          <div className="d-flex flex-column gap-2">
            {cart.items.map((item) => (
              <div key={item.cart_item_id} className="d-flex justify-content-between">
                <span>SKU #{item.sku_id} × {item.qty}</span>
                <span>₩{(item.item_amount ?? 0).toLocaleString()}</span>
              </div>
            ))}
          </div>
          <div className="border-top mt-3 pt-3">
            <div className="d-flex justify-content-between">
              <span>Subtotal</span>
              <span>₩{cart.totals.subtotal.toLocaleString()}</span>
            </div>
            <div className="d-flex justify-content-between">
              <span>Shipping</span>
              <span>₩{cart.totals.shipping_fee.toLocaleString()}</span>
            </div>
            <div className="d-flex justify-content-between">
              <span>Discount</span>
              <span>-₩{cart.totals.discount.toLocaleString()}</span>
            </div>
            <div className="d-flex justify-content-between fw-semibold fs-5 mt-2">
              <span>Total</span>
              <span>₩{cart.totals.total.toLocaleString()}</span>
            </div>
          </div>
          <button
            className="btn btn-primary w-100 mt-4"
            onClick={handleSubmit}
            disabled={creatingOrder || cartIssues.length > 0}
          >
            {creatingOrder ? 'Creating order...' : 'Place order'}
          </button>
        </aside>
      </div>
    </div>
  )
}
