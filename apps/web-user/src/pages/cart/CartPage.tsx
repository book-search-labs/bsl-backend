import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import { addCartItem, clearCart, getCart, removeCartItem, updateCartItem, type Cart } from '../../api/cart'
import { getCurrentOfferByMaterial, type CurrentOffer } from '../../api/catalog'
import { search } from '../../api/searchApi'
import BookCover from '../../components/books/BookCover'
import type { BookHit } from '../../types/search'

type RecommendationTab = 'ai' | 'today' | 'new'

type RecommendationItem = {
  docId: string
  title: string
  authors: string[]
  publisher: string | null
  isbn13: string | null
  coverUrl: string | null
  offer: CurrentOffer | null
}

function normalizeSeed(value?: string | null) {
  if (!value) return null
  const normalized = value.replace(/\s+/g, ' ').trim()
  if (!normalized) return null
  if (normalized.startsWith('도서 SKU #')) return null
  return normalized
}

function normalizeText(value?: string | null) {
  if (!value) return ''
  return value
    .toLowerCase()
    .replace(/\s+/g, ' ')
    .replace(/[^\p{L}\p{N}\s]/gu, '')
    .trim()
}

function buildRecommendationFingerprint(item: Omit<RecommendationItem, 'offer'>) {
  const titleKey = normalizeText(item.title)
  const authorKey = item.authors.map((author) => normalizeText(author)).filter(Boolean).sort().join(',')
  const publisherKey = normalizeText(item.publisher)
  return `${titleKey}|${authorKey}|${publisherKey}`
}

function buildAiQuery(cart: Cart) {
  const seeds = new Set<string>()
  cart.items.forEach((item) => {
    const candidates = [item.title, item.author, item.publisher]
    candidates.forEach((candidate) => {
      const normalized = normalizeSeed(candidate)
      if (normalized && seeds.size < 4) {
        seeds.add(normalized)
      }
    })
  })
  return seeds.size > 0 ? Array.from(seeds).join(' ') : '도서 추천'
}

function mapHitToRecommendation(hit: BookHit): Omit<RecommendationItem, 'offer'> | null {
  const docId = typeof hit.doc_id === 'string' ? hit.doc_id : null
  if (!docId) return null
  const source = hit.source ?? {}
  const title = typeof source.title_ko === 'string' ? source.title_ko : '제목 정보 없음'
  const authors = Array.isArray(source.authors) ? source.authors.filter((author) => typeof author === 'string') : []
  const publisher = typeof source.publisher_name === 'string' ? source.publisher_name : null
  const isbn13 = typeof source.isbn13 === 'string' ? source.isbn13 : null
  const coverUrl = typeof source.cover_url === 'string' ? source.cover_url : null

  return {
    docId,
    title,
    authors,
    publisher,
    isbn13,
    coverUrl,
  }
}

export default function CartPage() {
  const navigate = useNavigate()
  const [cart, setCart] = useState<Awaited<ReturnType<typeof getCart>> | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)
  const [noticeMessage, setNoticeMessage] = useState<string | null>(null)
  const [deliveryFilter, setDeliveryFilter] = useState<'all' | 'fast'>('all')
  const [recommendationTab, setRecommendationTab] = useState<RecommendationTab>('ai')
  const [recommendations, setRecommendations] = useState<RecommendationItem[]>([])
  const [recommendationLoading, setRecommendationLoading] = useState(false)
  const [recommendationError, setRecommendationError] = useState<string | null>(null)
  const [recommendationBusyId, setRecommendationBusyId] = useState<string | null>(null)

  useEffect(() => {
    let active = true
    setIsLoading(true)
    getCart()
      .then((data) => {
        if (!active) return
        setCart(data)
        setErrorMessage(null)
        setNoticeMessage(null)
      })
      .catch((err) => {
        if (!active) return
        setErrorMessage(err instanceof Error ? err.message : '장바구니 조회에 실패했습니다.')
      })
      .finally(() => {
        if (active) setIsLoading(false)
      })
    return () => {
      active = false
    }
  }, [])

  const cartSeed = useMemo(
    () => cart?.items.map((item) => `${item.cart_item_id}:${item.qty}:${item.material_id ?? item.sku_id}`).join('|') ?? '',
    [cart],
  )

  useEffect(() => {
    let active = true
    if (!cart || cart.items.length === 0) {
      setRecommendations([])
      setRecommendationError(null)
      setRecommendationLoading(false)
      return () => {
        active = false
      }
    }

    const loadRecommendations = async () => {
      setRecommendationLoading(true)
      setRecommendationError(null)

      try {
        const query =
          recommendationTab === 'ai'
            ? buildAiQuery(cart)
            : recommendationTab === 'today'
              ? '오늘의 책 추천'
              : '신간 도서 추천'
        const response = await search(query, {
          size: recommendationTab === 'ai' ? 80 : 40,
          from: 0,
          vector: recommendationTab === 'ai',
        })
        const hits = Array.isArray(response.hits) ? response.hits : []
        const cartMaterialIds = new Set(
          cart.items.map((item) => item.material_id).filter((materialId): materialId is string => Boolean(materialId)),
        )
        const seenDocIds = new Set<string>()
        const seenFingerprints = new Set<string>()
        const seenTitles = new Set<string>()

        const candidates = hits
          .map(mapHitToRecommendation)
          .filter((item): item is Omit<RecommendationItem, 'offer'> => item !== null)
          .filter((item) => {
            if (seenDocIds.has(item.docId)) return false
            seenDocIds.add(item.docId)
            if (cartMaterialIds.has(item.docId)) return false

            const fingerprint = buildRecommendationFingerprint(item)
            if (fingerprint && seenFingerprints.has(fingerprint)) return false
            if (fingerprint) {
              seenFingerprints.add(fingerprint)
            }

            const titleKey = normalizeText(item.title)
            if (titleKey && seenTitles.has(titleKey)) return false
            if (titleKey) {
              seenTitles.add(titleKey)
            }

            return true
          })
          .slice(0, 8)

        const withOffer = await Promise.all(
          candidates.map(async (candidate) => {
            try {
              const offer = await getCurrentOfferByMaterial(candidate.docId)
              return { ...candidate, offer }
            } catch {
              return { ...candidate, offer: null }
            }
          }),
        )

        if (!active) return
        setRecommendations(withOffer)
      } catch (err) {
        if (!active) return
        setRecommendationError(err instanceof Error ? err.message : '추천 도서를 불러오지 못했습니다.')
      } finally {
        if (active) setRecommendationLoading(false)
      }
    }

    void loadRecommendations()

    return () => {
      active = false
    }
  }, [cart, cartSeed, recommendationTab])

  const visibleItems = useMemo(() => {
    if (!cart) return []
    if (deliveryFilter === 'fast') {
      return cart.items.filter((item) => !item.out_of_stock)
    }
    return cart.items
  }, [cart, deliveryFilter])

  const totalItems = useMemo(() => cart?.items?.reduce((sum, item) => sum + item.qty, 0) ?? 0, [cart])
  const rewardThreshold = useMemo(() => cart?.benefits?.bonus_point_threshold ?? 50000, [cart])
  const baseShippingFee = useMemo(() => cart?.benefits?.base_shipping_fee ?? 3000, [cart])
  const fastShippingFee = useMemo(() => cart?.benefits?.fast_shipping_fee ?? 5000, [cart])
  const rewardProgress = useMemo(() => {
    if (!cart) return 0
    if (cart.totals.subtotal <= 0) return 0
    return Math.min(100, Math.round((cart.totals.subtotal / rewardThreshold) * 100))
  }, [cart, rewardThreshold])
  const pointsEstimate = useMemo(() => cart?.loyalty?.expected_earn_points ?? 0, [cart])
  const pointBalance = useMemo(() => cart?.loyalty?.point_balance ?? 0, [cart])
  const activeFastCount = useMemo(() => cart?.items.filter((item) => !item.out_of_stock).length ?? 0, [cart])

  const handleQtyChange = async (cartItemId: number, qty: number) => {
    if (!cart) return
    try {
      const next = await updateCartItem(cartItemId, { qty })
      setCart(next)
      setNoticeMessage(null)
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : '수량 변경에 실패했습니다.')
    }
  }

  const handleRemove = async (cartItemId: number) => {
    if (!cart) return
    try {
      const next = await removeCartItem(cartItemId)
      setCart(next)
      setNoticeMessage(null)
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : '상품 삭제에 실패했습니다.')
    }
  }

  const handleClear = async () => {
    if (!cart) return
    try {
      const next = await clearCart()
      setCart(next)
      setNoticeMessage('장바구니를 비웠습니다.')
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : '장바구니 비우기에 실패했습니다.')
    }
  }

  const handleAddRecommendation = async (item: RecommendationItem) => {
    if (!item.offer) {
      setNoticeMessage('추천 도서의 판매 정보를 찾지 못했습니다.')
      return
    }
    try {
      setRecommendationBusyId(item.docId)
      const next = await addCartItem({
        skuId: item.offer.sku_id,
        sellerId: item.offer.seller_id,
        qty: 1,
      })
      setCart(next)
      setNoticeMessage(`'${item.title}' 도서를 장바구니에 담았습니다.`)
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : '추천 도서 담기에 실패했습니다.')
    } finally {
      setRecommendationBusyId(null)
    }
  }

  const handleProceedCheckout = (mode: 'STANDARD' | 'FAST') => {
    navigate(`/checkout?shipping_mode=${mode}`)
  }

  if (isLoading) {
    return (
      <div className="container py-5">
        <div className="card shadow-sm p-4">장바구니 정보를 불러오는 중입니다...</div>
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
          <h2 className="mb-3">장바구니가 비어 있습니다</h2>
          <p className="text-muted mb-4">원하는 도서를 담고 주문을 시작해보세요.</p>
          <Link to="/search" className="btn btn-primary">
            도서 둘러보기
          </Link>
        </div>
      </div>
    )
  }

  return (
    <div className="container py-5 cart-page">
      <div className="cart-header-row">
        <div className="cart-header-left">
          <h2 className="mb-0">장바구니 ({totalItems})</h2>
          <span className="cart-chip">기본배송지</span>
        </div>
        <div className="cart-filter-toggle" role="tablist" aria-label="배송 필터">
          <button
            type="button"
            className={`cart-filter-btn ${deliveryFilter === 'all' ? 'active' : ''}`}
            onClick={() => setDeliveryFilter('all')}
          >
            모두보기
          </button>
          <button
            type="button"
            className={`cart-filter-btn ${deliveryFilter === 'fast' ? 'active' : ''}`}
            onClick={() => setDeliveryFilter('fast')}
          >
            빠른배송만
          </button>
        </div>
        <ol className="cart-steps" aria-label="주문 단계">
          <li className="active">장바구니</li>
          <li>사은품선택</li>
          <li>주문/결제</li>
          <li>주문완료</li>
        </ol>
      </div>

      {noticeMessage ? <div className="alert alert-success py-2">{noticeMessage}</div> : null}

      <div className="cart-layout">
        <div className="cart-main-col">
          <section className="cart-card card shadow-sm">
            <div className="cart-card-toolbar">
              <div className="fw-semibold">전체 {visibleItems.length}건</div>
              <button className="btn btn-outline-secondary btn-sm" onClick={handleClear}>
                전체 비우기
              </button>
            </div>

            <div className="cart-seller-badge">BSL 스토어/빠른배송</div>

            <div className="cart-reward-strip">
              <div className="cart-reward-text">
                <strong>{rewardThreshold.toLocaleString()}원 이상 구매 시 추가 적립!</strong>
                <span>{cart.totals.subtotal.toLocaleString()}원 구매 중</span>
              </div>
              <div className="cart-progress-track">
                <div className="cart-progress-fill" style={{ width: `${rewardProgress}%` }} />
              </div>
              <div className="cart-reward-action">
                {cart.totals.subtotal >= rewardThreshold
                  ? '적립 기준 달성'
                  : `${(rewardThreshold - cart.totals.subtotal).toLocaleString()}원 더 담기`}
              </div>
            </div>

            {deliveryFilter === 'fast' ? (
              <div className="cart-filter-note">
                빠른배송 가능 상품 {activeFastCount}건을 보고 있습니다.
                <button type="button" className="btn btn-link btn-sm p-0 ms-2" onClick={() => setDeliveryFilter('all')}>
                  모두보기
                </button>
              </div>
            ) : null}

            <div className="cart-list d-flex flex-column">
              {visibleItems.length === 0 ? (
                <div className="text-muted py-4 px-4">선택한 조건에 맞는 상품이 없습니다.</div>
              ) : (
                visibleItems.map((item) => (
                  <article key={item.cart_item_id} className="cart-item-row">
                    <Link to={item.material_id ? `/book/${encodeURIComponent(item.material_id)}` : '/search'} className="cart-cover">
                      <BookCover
                        className="book-cover-image"
                        title={item.title ?? '도서 표지'}
                        coverUrl={item.cover_url ?? null}
                        isbn13={item.isbn13 ?? null}
                        docId={item.material_id ?? `sku:${item.sku_id}`}
                        size="M"
                      />
                    </Link>
                    <div className="cart-item-body">
                      <div className="cart-item-title">{item.title ?? `도서 SKU #${item.sku_id}`}</div>
                      <div className="cart-item-meta">
                        {[item.author, item.publisher].filter(Boolean).join(' · ') || '도서 메타데이터 준비 중'}
                      </div>
                      <div className="cart-item-meta">{item.seller_name ?? `판매자 #${item.seller_id}`}</div>
                      <div className="cart-item-badges">
                        {item.price_changed ? <span className="badge text-bg-warning">가격 변동</span> : null}
                        {item.out_of_stock ? <span className="badge text-bg-danger">재고 부족</span> : null}
                      </div>
                    </div>
                    <div className="cart-item-price">
                      <div className="cart-item-price-main">₩{(item.unit_price ?? 0).toLocaleString()}</div>
                      <div className="cart-item-price-sub">{(item.item_amount ?? 0).toLocaleString()}원</div>
                      <div className="cart-qty d-flex align-items-center gap-2 mt-2">
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
                    </div>
                    <div className="cart-item-side">
                      <div className="small text-muted">
                        {item.available_qty === null || item.available_qty === undefined
                          ? '재고 확인 중'
                          : `재고 ${item.available_qty}권`}
                      </div>
                      <button className="btn btn-link text-danger px-0 mt-2" onClick={() => handleRemove(item.cart_item_id)}>
                        삭제
                      </button>
                    </div>
                  </article>
                ))
              )}
            </div>
          </section>

          <section className="cart-card card shadow-sm">
            <div className="cart-reco-header">
              <div className="cart-reco-tabs">
                <button
                  type="button"
                  className={`cart-reco-tab ${recommendationTab === 'ai' ? 'active' : ''}`}
                  onClick={() => setRecommendationTab('ai')}
                >
                  AI 맞춤추천
                </button>
                <button
                  type="button"
                  className={`cart-reco-tab ${recommendationTab === 'today' ? 'active' : ''}`}
                  onClick={() => setRecommendationTab('today')}
                >
                  오늘의 책
                </button>
                <button
                  type="button"
                  className={`cart-reco-tab ${recommendationTab === 'new' ? 'active' : ''}`}
                  onClick={() => setRecommendationTab('new')}
                >
                  새로 나온 책
                </button>
              </div>
            </div>

            {recommendationLoading ? <div className="text-muted px-4 pb-4">추천 도서를 불러오는 중입니다...</div> : null}
            {recommendationError ? <div className="text-danger px-4 pb-4">{recommendationError}</div> : null}

            {!recommendationLoading && !recommendationError ? (
              recommendations.length > 0 ? (
                <div className="cart-reco-list">
                  {recommendations.map((item) => (
                    <article key={item.docId} className="cart-reco-item">
                      <Link to={`/book/${encodeURIComponent(item.docId)}`} className="cart-reco-cover">
                        <BookCover
                          className="book-cover-image"
                          title={item.title}
                          coverUrl={item.coverUrl}
                          isbn13={item.isbn13}
                          docId={item.docId}
                          size="M"
                        />
                      </Link>
                      <Link to={`/book/${encodeURIComponent(item.docId)}`} className="cart-reco-title">
                        {item.title}
                      </Link>
                      <div className="cart-reco-meta">{item.authors.length > 0 ? item.authors.join(', ') : '저자 정보 없음'}</div>
                      <div className="cart-reco-price">
                        {item.offer ? `₩${item.offer.effective_price.toLocaleString()}` : '판매 정보 없음'}
                      </div>
                      <button
                        type="button"
                        className="cart-reco-add"
                        onClick={() => handleAddRecommendation(item)}
                        disabled={!item.offer || recommendationBusyId === item.docId}
                      >
                        {recommendationBusyId === item.docId ? '담는 중...' : '장바구니'}
                      </button>
                    </article>
                  ))}
                </div>
              ) : (
                <div className="text-muted px-4 pb-4">추천 도서가 없습니다. 다른 도서를 담아보세요.</div>
              )
            ) : null}
          </section>

          <section className="cart-card card shadow-sm">
            <h4 className="cart-section-title">결제 프로모션</h4>
            <div className="cart-promo-list">
              {(cart.promotions ?? []).map((promotion) => (
                <details key={`promotion-${promotion.item_id}`}>
                  <summary>{promotion.title}</summary>
                </details>
              ))}
              {(cart.promotions ?? []).length === 0 ? (
                <div className="text-muted small px-1 py-2">현재 적용 가능한 프로모션이 없습니다.</div>
              ) : null}
            </div>
          </section>

          <section className="cart-card card shadow-sm">
            <h4 className="cart-section-title">장바구니 유의사항</h4>
            <ul className="cart-notice-list">
              {(cart.notices ?? []).map((notice) => (
                <li key={`notice-${notice.item_id}`}>{notice.title}</li>
              ))}
              {(cart.notices ?? []).length === 0 ? <li>표시할 유의사항이 없습니다.</li> : null}
            </ul>
          </section>
        </div>

        <aside className="cart-summary card shadow-sm p-4">
          <h3 className="mb-3">주문 요약</h3>
          <div className="d-flex justify-content-between mb-2">
            <span className="text-muted">상품 금액</span>
            <span>₩{cart.totals.subtotal.toLocaleString()}</span>
          </div>
          <div className="d-flex justify-content-between mb-2">
            <span className="text-muted">배송비</span>
            <span>₩{cart.totals.shipping_fee.toLocaleString()}</span>
          </div>
          <div className="d-flex justify-content-between mb-3">
            <span className="text-muted">할인</span>
            <span className="text-primary">-₩{cart.totals.discount.toLocaleString()}</span>
          </div>
          <div className="d-flex justify-content-between fs-5 fw-semibold border-top pt-3">
            <span>총 결제금액</span>
            <span>₩{cart.totals.total.toLocaleString()}</span>
          </div>
          <div className="d-flex justify-content-between mt-2">
            <span className="text-muted">적립 예정 포인트</span>
            <span>{pointsEstimate.toLocaleString()}P</span>
          </div>
          <div className="d-flex justify-content-between mt-1">
            <span className="text-muted">보유 포인트</span>
            <span>{pointBalance.toLocaleString()}P</span>
          </div>
          <div className="d-flex justify-content-between mt-1">
            <span className="text-muted">기본/빠른 배송비</span>
            <span>
              {baseShippingFee.toLocaleString()}원 / {fastShippingFee.toLocaleString()}원
            </span>
          </div>
          <button type="button" className="btn btn-primary w-100 mt-4 cart-order-btn" onClick={() => handleProceedCheckout('STANDARD')}>
            주문하기 ({totalItems})
          </button>
          <button
            type="button"
            className="btn btn-outline-primary w-100 mt-2"
            onClick={() => handleProceedCheckout('FAST')}
            disabled={activeFastCount === 0}
          >
            빠른배송 주문 ({activeFastCount})
          </button>
          <div className="cart-summary-sub-actions">
            <button type="button" className="btn btn-outline-secondary btn-sm">
              선물하기
            </button>
            <button type="button" className="btn btn-outline-secondary btn-sm">
              여러곳 배송
            </button>
          </div>
        </aside>
      </div>
    </div>
  )
}
