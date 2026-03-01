import { NavLink } from 'react-router-dom'

import { MY_MENU_GROUPS } from './myNavigation'

type MySideNavProps = {
  onNavigate?: () => void
}

const sideNavLinkClassName = ({ isActive }: { isActive: boolean }) =>
  `my-side-link ${isActive ? 'is-active' : ''}`

export default function MySideNav({ onNavigate }: MySideNavProps) {
  return (
    <nav className="my-side-nav" aria-label="마이페이지 메뉴">
      {MY_MENU_GROUPS.map((group) => (
        <section key={group.key} className="my-side-group">
          <h3 className="my-side-group-title">{group.title}</h3>
          <div className="my-side-group-links">
            {group.items
              .filter((item) => !item.hidden)
              .map((item) => (
                <NavLink key={item.key} to={item.to} className={sideNavLinkClassName} onClick={onNavigate}>
                  {item.label}
                </NavLink>
              ))}
          </div>
        </section>
      ))}
    </nav>
  )
}
