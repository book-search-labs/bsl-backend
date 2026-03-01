import { Link, NavLink } from 'react-router-dom'

type UtilityMenuProps = {
  isLoggedIn: boolean
  onLogin: () => void
  onLogout: () => void
}

const linkClassName = ({ isActive }: { isActive: boolean }) =>
  `utility-text-link ${isActive ? 'is-active' : ''}`

export default function UtilityMenu({ isLoggedIn, onLogin, onLogout }: UtilityMenuProps) {
  const authAction = isLoggedIn ? onLogout : onLogin
  const authLabel = isLoggedIn ? '로그아웃' : '로그인'

  return (
    <div className="utility-menu-row" aria-label="유틸리티 메뉴">
      <button type="button" className="utility-text-link utility-text-button" onClick={authAction}>
        {authLabel}
      </button>
      <span className="utility-divider" aria-hidden="true" />
      <NavLink to="/my/wallet/points" className={linkClassName}>
        회원혜택
      </NavLink>
      <span className="utility-divider" aria-hidden="true" />
      <NavLink to="/my/orders" className={linkClassName}>
        주문/배송
      </NavLink>
      <span className="utility-divider" aria-hidden="true" />
      <Link to="/my/support/inquiries" className="utility-text-link">
        고객센터
      </Link>
    </div>
  )
}
