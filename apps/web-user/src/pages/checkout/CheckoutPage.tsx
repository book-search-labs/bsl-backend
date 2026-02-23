import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'

import { createOrder } from '../../api/orders'
import { createAddress, fetchCheckoutSummary, type Address } from '../../api/checkout'

function generateIdempotencyKey() {
  return `idem_${crypto.randomUUID()}`
}

export default function CheckoutPage() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const [summary, setSummary] = useState<Awaited<ReturnType<typeof fetchCheckoutSummary>> | null>(null)
  const [selectedAddress, setSelectedAddress] = useState<number | null>(null)
  const [shippingMode, setShippingMode] = useState<'STANDARD' | 'FAST'>(
    searchParams.get('shipping_mode')?.toUpperCase() === 'FAST' ? 'FAST' : 'STANDARD',
  )
  const [paymentMethod, setPaymentMethod] = useState('CARD')
  const [loading, setLoading] = useState(true)
  const [loadErrorMessage, setLoadErrorMessage] = useState<string | null>(null)
  const [actionErrorMessage, setActionErrorMessage] = useState<string | null>(null)
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
        setLoadErrorMessage(null)
        const defaultAddress = data.addresses?.find((address) => Boolean(address.is_default))
        if (defaultAddress) {
          setSelectedAddress(defaultAddress.address_id)
        } else if (data.addresses?.length) {
          setSelectedAddress(data.addresses[0].address_id)
        }
      })
      .catch((err) => {
        if (!active) return
        setLoadErrorMessage(err instanceof Error ? err.message : '주문/결제 정보를 불러오지 못했습니다.')
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
  const baseShippingFee = useMemo(() => cart?.benefits?.base_shipping_fee ?? cart?.totals.shipping_fee ?? 3000, [cart])
  const fastShippingFee = useMemo(() => cart?.benefits?.fast_shipping_fee ?? 5000, [cart])
  const checkoutShippingFee = shippingMode === 'FAST' ? fastShippingFee : baseShippingFee
  const checkoutTotal = useMemo(() => {
    if (!cart) return 0
    return cart.totals.subtotal + checkoutShippingFee - cart.totals.discount
  }, [cart, checkoutShippingFee])
  const cartIssues = useMemo(() => {
    if (!cart?.items) return []
    return cart.items.filter((item) => item.price_changed || item.out_of_stock)
  }, [cart])

  const handleCreateAddress = async () => {
    if (!newAddress.name || !newAddress.phone) {
      setActionErrorMessage('받는 분 이름과 연락처를 입력해주세요.')
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
      setActionErrorMessage(null)
    } catch (err) {
      setActionErrorMessage(err instanceof Error ? err.message : '배송지 추가에 실패했습니다.')
    }
  }

  const handleSubmit = async () => {
    if (!cart?.cart_id) {
      setActionErrorMessage('장바구니가 비어 있습니다.')
      return
    }
    if (!selectedAddress) {
      setActionErrorMessage('배송지를 선택해주세요.')
      return
    }
    if (cartIssues.length > 0) {
      setActionErrorMessage('가격 또는 재고 변동 상품을 확인한 뒤 주문해주세요.')
      return
    }
    setActionErrorMessage(null)
    setCreatingOrder(true)
    try {
      const response = await createOrder({
        cartId: cart.cart_id,
        shippingAddressId: selectedAddress,
        shippingMode,
        paymentMethod,
        idempotencyKey,
      })
      const orderId = response.order.order_id
      navigate(`/payment/process/${orderId}`)
    } catch (err) {
      setActionErrorMessage(err instanceof Error ? err.message : '주문 생성에 실패했습니다.')
    } finally {
      setCreatingOrder(false)
    }
  }

  if (loading) {
    return (
      <div className="container py-5">
        <div className="card p-4">주문/결제 정보를 불러오는 중입니다...</div>
      </div>
    )
  }

  if (loadErrorMessage) {
    return (
      <div className="container py-5">
        <div className="alert alert-danger">{loadErrorMessage}</div>
      </div>
    )
  }

  if (!cart) {
    return (
      <div className="container py-5">
        <div className="card p-4">장바구니 정보가 없습니다. 장바구니에서 다시 확인해주세요.</div>
      </div>
    )
  }

  return (
    <div className="container py-5">
      {actionErrorMessage ? <div className="alert alert-danger">{actionErrorMessage}</div> : null}
      <div className="checkout-grid">
        <div className="checkout-main">
          <section className="card p-4 mb-4">
            <h3 className="mb-3">배송지 선택</h3>
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
              <h6>신규 배송지 추가</h6>
              <div className="row g-2">
                <div className="col-md-6">
                  <input
                    className="form-control"
                    placeholder="받는 분"
                    value={newAddress.name}
                    onChange={(event) => setNewAddress({ ...newAddress, name: event.target.value })}
                  />
                </div>
                <div className="col-md-6">
                  <input
                    className="form-control"
                    placeholder="연락처"
                    value={newAddress.phone}
                    onChange={(event) => setNewAddress({ ...newAddress, phone: event.target.value })}
                  />
                </div>
                <div className="col-md-4">
                  <input
                    className="form-control"
                    placeholder="우편번호"
                    value={newAddress.zip}
                    onChange={(event) => setNewAddress({ ...newAddress, zip: event.target.value })}
                  />
                </div>
                <div className="col-md-8">
                  <input
                    className="form-control"
                    placeholder="기본 주소"
                    value={newAddress.addr1}
                    onChange={(event) => setNewAddress({ ...newAddress, addr1: event.target.value })}
                  />
                </div>
                <div className="col-12">
                  <input
                    className="form-control"
                    placeholder="상세 주소"
                    value={newAddress.addr2}
                    onChange={(event) => setNewAddress({ ...newAddress, addr2: event.target.value })}
                  />
                </div>
              </div>
              <button className="btn btn-outline-primary mt-3" onClick={handleCreateAddress}>
                배송지 저장
              </button>
            </div>
          </section>

          <section className="card p-4 mb-4">
            <h3 className="mb-3">배송 옵션</h3>
            <div className="d-flex gap-3">
              <label className="payment-option">
                <input
                  type="radio"
                  name="shipping_mode"
                  checked={shippingMode === 'STANDARD'}
                  onChange={() => setShippingMode('STANDARD')}
                />
                <span>기본배송 (₩{baseShippingFee.toLocaleString()})</span>
              </label>
              <label className="payment-option">
                <input
                  type="radio"
                  name="shipping_mode"
                  checked={shippingMode === 'FAST'}
                  onChange={() => setShippingMode('FAST')}
                />
                <span>빠른배송 (₩{fastShippingFee.toLocaleString()})</span>
              </label>
            </div>
          </section>

          <section className="card p-4 mb-4">
            <h3 className="mb-3">결제 수단</h3>
            <div className="d-flex gap-3">
              {['CARD', 'TRANSFER', 'EASY_PAY'].map((method) => (
                <label key={method} className="payment-option">
                  <input
                    type="radio"
                    name="payment_method"
                    checked={paymentMethod === method}
                    onChange={() => setPaymentMethod(method)}
                  />
                  <span>{method === 'CARD' ? '카드' : method === 'TRANSFER' ? '계좌이체' : '간편결제'}</span>
                </label>
              ))}
            </div>
          </section>

          {cartIssues.length > 0 ? (
            <div className="alert alert-warning">
              일부 상품의 가격 또는 재고가 변경되었습니다. 주문 전에 장바구니를 확인해주세요.
            </div>
          ) : null}
        </div>

        <aside className="checkout-summary card p-4">
          <h3 className="mb-3">주문 요약</h3>
          <div className="d-flex flex-column gap-2">
            {cart.items.map((item) => (
              <div key={item.cart_item_id} className="d-flex justify-content-between">
                <span>{item.title ?? `도서 SKU #${item.sku_id}`} × {item.qty}</span>
                <span>₩{(item.item_amount ?? 0).toLocaleString()}</span>
              </div>
            ))}
          </div>
          <div className="border-top mt-3 pt-3">
            <div className="d-flex justify-content-between">
              <span>상품 금액</span>
              <span>₩{cart.totals.subtotal.toLocaleString()}</span>
            </div>
            <div className="d-flex justify-content-between">
              <span>배송비</span>
              <span>₩{checkoutShippingFee.toLocaleString()}</span>
            </div>
            <div className="d-flex justify-content-between">
              <span>할인</span>
              <span>-₩{cart.totals.discount.toLocaleString()}</span>
            </div>
            <div className="d-flex justify-content-between fw-semibold fs-5 mt-2">
              <span>총 결제금액</span>
              <span>₩{checkoutTotal.toLocaleString()}</span>
            </div>
          </div>
          <button
            className="btn btn-primary w-100 mt-4"
            onClick={handleSubmit}
            disabled={creatingOrder || cartIssues.length > 0}
          >
            {creatingOrder ? '주문 생성 중...' : '주문하기'}
          </button>
        </aside>
      </div>
    </div>
  )
}
