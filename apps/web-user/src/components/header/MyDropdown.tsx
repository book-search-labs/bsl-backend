import { NavLink } from 'react-router-dom'

import type { MyMenuItem } from '../../types/my'

type MyDropdownProps = {
  isOpen: boolean
  items: MyMenuItem[]
  onNavigate: () => void
}

const linkClassName = ({ isActive }: { isActive: boolean }) =>
  `my-dropdown-link ${isActive ? 'is-active' : ''}`

export default function MyDropdown({ isOpen, items, onNavigate }: MyDropdownProps) {
  if (!isOpen) {
    return null
  }

  return (
    <div className="my-dropdown" role="menu" aria-label="마이 메뉴">
      {items.map((item) => (
        <NavLink key={item.key} to={item.to} className={linkClassName} role="menuitem" onClick={onNavigate}>
          {item.label}
        </NavLink>
      ))}
    </div>
  )
}
