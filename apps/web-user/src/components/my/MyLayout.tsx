import { useMemo, useState } from 'react'
import { Outlet, Link, useLocation } from 'react-router-dom'

import { getSessionUser } from '../../services/mySession'
import { findMyMenuItem } from './myNavigation'
import MySideNav from './MySideNav'

export default function MyLayout() {
  const location = useLocation()
  const [drawerOpen, setDrawerOpen] = useState(false)
  const user = useMemo(() => getSessionUser(), [])
  const currentMenu = findMyMenuItem(location.pathname)

  if (!user) {
    return (
      <section className="my-page-wrap container py-4 py-lg-5">
        <section className="my-panel">
          <h1>로그인이 필요합니다.</h1>
          <p className="mb-3">상단 메뉴에서 로그인 후 마이페이지를 이용해 주세요.</p>
          <Link to="/" className="btn btn-primary">
            홈으로 이동
          </Link>
        </section>
      </section>
    )
  }

  return (
    <section className="my-page-wrap container py-4 py-lg-5">
      <div className="my-mobile-toolbar d-lg-none">
        <button type="button" className="my-drawer-trigger" onClick={() => setDrawerOpen(true)}>
          마이 메뉴
        </button>
        <div className="my-mobile-breadcrumb">{currentMenu?.label ?? '마이페이지'}</div>
      </div>

      <div className="my-layout-grid">
        <aside className="my-layout-sidebar d-none d-lg-block">
          <div className="my-user-card">
            <div className="my-user-avatar" aria-hidden="true">
              {user.name.slice(0, 1)}
            </div>
            <div className="my-user-name">{user.name}</div>
            <div className="my-user-meta">{user.email}</div>
            <div className="my-user-tier">{user.membershipLabel}</div>
          </div>
          <MySideNav />
        </aside>

        <div className="my-layout-content">
          <div className="my-content-header">
            <div className="my-breadcrumb d-none d-lg-flex">
              <Link to="/">홈</Link>
              <span>/</span>
              <span>마이페이지</span>
              {currentMenu ? (
                <>
                  <span>/</span>
                  <span>{currentMenu.label}</span>
                </>
              ) : null}
            </div>
          </div>
          <Outlet />
        </div>
      </div>

      <div className={`my-drawer ${drawerOpen ? 'is-open' : ''}`} aria-hidden={!drawerOpen}>
        <div className="my-drawer-backdrop" onClick={() => setDrawerOpen(false)} />
        <div className="my-drawer-panel" role="dialog" aria-modal="true">
          <div className="my-drawer-header">
            <div>
              <div className="my-drawer-title">{user.name}</div>
              <div className="my-drawer-subtitle">{user.membershipLabel}</div>
            </div>
            <button type="button" className="my-drawer-close" onClick={() => setDrawerOpen(false)}>
              닫기
            </button>
          </div>
          <MySideNav onNavigate={() => setDrawerOpen(false)} />
        </div>
      </div>
    </section>
  )
}
