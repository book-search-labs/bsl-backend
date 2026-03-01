import { Link } from 'react-router-dom'

export default function AboutPage() {
  return (
    <section className="page-section support-page">
      <div className="container py-5">
        <div className="section-header">
          <div>
            <p className="section-kicker">고객센터</p>
            <h1 className="section-title">배송/반품 안내</h1>
            <p className="section-note">주문, 배송, 반품/환불 정책을 한 번에 확인하세요.</p>
          </div>
          <Link to="/orders" className="section-link">
            주문/배송 조회
          </Link>
        </div>

        <div className="support-highlight-grid">
          <article className="help-card">
            <h2 className="help-title">배송 정책</h2>
            <ul className="support-list">
              <li>기본 배송비: 3,000원</li>
              <li>빠른 배송비: 5,000원</li>
              <li>20,000원 이상 주문 시 배송비 무료</li>
              <li>주문 상태는 주문/배송 메뉴에서 실시간 확인</li>
            </ul>
          </article>
          <article className="help-card">
            <h2 className="help-title">반품/환불 정책</h2>
            <ul className="support-list">
              <li>배송 완료 후 7일 이내 반품 신청 가능</li>
              <li>상품 하자/오배송은 반품 수수료 무료</li>
              <li>단순 변심 반품은 주문 상태에 따라 수수료가 적용될 수 있음</li>
              <li>환불 금액은 주문 상세의 환불 규칙에 따라 자동 계산</li>
            </ul>
          </article>
        </div>

        <div className="placeholder-card">
          <h2 className="section-title">자주 묻는 질문</h2>
          <div className="support-faq-list">
            <div className="support-faq-item">
              <div className="support-faq-q">Q. 빠른 배송 주문 버튼을 누르면 무엇이 달라지나요?</div>
              <div className="support-faq-a">A. 빠른 배송 모드로 주문되며 배송비는 5,000원이 적용됩니다.</div>
            </div>
            <div className="support-faq-item">
              <div className="support-faq-q">Q. 주문 취소는 언제까지 가능한가요?</div>
              <div className="support-faq-a">A. 결제 대기/결제 완료/출고 준비 단계에서는 주문 취소가 가능합니다.</div>
            </div>
            <div className="support-faq-item">
              <div className="support-faq-q">Q. 반품 신청은 어디서 하나요?</div>
              <div className="support-faq-a">A. 주문 상세 화면의 환불/반품 신청 메뉴에서 접수할 수 있습니다.</div>
            </div>
          </div>
        </div>

        <div className="help-grid">
          <article className="help-card">
            <div className="help-title">주문 상태 확인</div>
            <p className="help-meta">최근 주문 내역과 배송 단계를 확인하세요.</p>
            <Link to="/orders" className="help-link">
              주문 내역 보기
            </Link>
          </article>
          <article className="help-card">
            <div className="help-title">반품 신청</div>
            <p className="help-meta">주문 상세에서 사유를 선택해 반품/환불을 신청할 수 있습니다.</p>
            <Link to="/orders" className="help-link">
              환불/반품 접수하기
            </Link>
          </article>
          <article className="help-card">
            <div className="help-title">장바구니 이동</div>
            <p className="help-meta">선택한 도서를 확인하고 결제를 진행하세요.</p>
            <Link to="/cart" className="help-link">
              장바구니 열기
            </Link>
          </article>
        </div>
      </div>
    </section>
  )
}
