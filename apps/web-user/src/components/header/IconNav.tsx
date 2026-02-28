import { Link, NavLink } from 'react-router-dom'
import type { RefObject } from 'react'

import type { MyMenuItem } from '../../types/my'
import MyDropdown from './MyDropdown'

type IconNavProps = {
  cartCount: number
  myMenuOpen: boolean
  onToggleMyMenu: () => void
  onCloseMyMenu: () => void
  dropdownItems: MyMenuItem[]
  dropdownRef: RefObject<HTMLDivElement | null>
}

const navClassName = ({ isActive }: { isActive: boolean }) =>
  `icon-nav-link ${isActive ? 'is-active' : ''}`

export default function IconNav({
  cartCount,
  myMenuOpen,
  onToggleMyMenu,
  onCloseMyMenu,
  dropdownItems,
  dropdownRef,
}: IconNavProps) {
  return (
    <div className="icon-nav" ref={dropdownRef}>
      <NavLink to="/cart" className={navClassName} aria-label="장바구니">
        <span className="icon-nav-symbol" aria-hidden="true">
          🛒
        </span>
        <span className="icon-nav-label">장바구니</span>
        {cartCount > 0 ? <span className="icon-nav-badge">{cartCount}</span> : null}
      </NavLink>

      <button
        type="button"
        className={`icon-nav-link icon-nav-link--button ${myMenuOpen ? 'is-open' : ''}`}
        aria-haspopup="menu"
        aria-expanded={myMenuOpen}
        onClick={onToggleMyMenu}
      >
        <span className="icon-nav-symbol" aria-hidden="true">
          👤
        </span>
        <span className="icon-nav-label">MY</span>
      </button>

      <MyDropdown isOpen={myMenuOpen} items={dropdownItems} onNavigate={onCloseMyMenu} />

      <Link to="/events" className="icon-nav-inline-link">
        이벤트/공지
      </Link>
    </div>
  )
}
