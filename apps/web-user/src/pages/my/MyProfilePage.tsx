import { useState } from 'react'

import { getSessionUser, updateSessionUser } from '../../services/mySession'

export default function MyProfilePage() {
  const base = getSessionUser()
  const [name, setName] = useState(base?.name ?? '')
  const [phone, setPhone] = useState(base?.phone ?? '')
  const [notice, setNotice] = useState<string | null>(null)

  const handleSave = () => {
    if (!base) return
    updateSessionUser({
      ...base,
      name: name.trim() || base.name,
      phone: phone.trim() || base.phone,
    })
    setNotice('회원정보가 저장되었습니다.')
  }

  if (!base) {
    return (
      <section className="my-content-section">
        <header className="my-section-header">
          <h1>회원정보 수정</h1>
          <p>로그인 후 이용할 수 있습니다.</p>
        </header>
      </section>
    )
  }

  return (
    <section className="my-content-section">
      <header className="my-section-header">
        <h1>회원정보 수정</h1>
        <p>임시 로그인 세션 기준으로 회원 이름/연락처를 수정할 수 있습니다.</p>
      </header>

      <section className="my-panel">
        <div className="my-form-grid">
          <label>
            이메일
            <input value={base.email} disabled readOnly />
          </label>
          <label>
            이름
            <input value={name} onChange={(event) => setName(event.target.value)} />
          </label>
          <label>
            연락처
            <input value={phone} onChange={(event) => setPhone(event.target.value)} />
          </label>
          <button type="button" className="btn btn-primary align-self-start" onClick={handleSave}>
            저장
          </button>
          {notice ? <div className="my-notice">{notice}</div> : null}
        </div>
      </section>
    </section>
  )
}
