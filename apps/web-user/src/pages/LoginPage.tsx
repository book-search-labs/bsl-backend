import { type FormEvent, useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'

import { loginWithPassword } from '../api/auth'
import { HttpError } from '../api/http'
import { getSessionId, setSession } from '../services/mySession'

function resolveRedirect(raw: string | null) {
  if (!raw) return '/'
  if (!raw.startsWith('/')) return '/'
  if (raw.startsWith('/login')) return '/'
  return raw
}

export default function LoginPage() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const redirectTo = useMemo(() => resolveRedirect(searchParams.get('redirect')), [searchParams])
  const [email, setEmail] = useState('demo@bslbooks.local')
  const [password, setPassword] = useState('demo1234!')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)

  useEffect(() => {
    if (getSessionId()) {
      navigate(redirectTo, { replace: true })
    }
  }, [navigate, redirectTo])

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const normalizedEmail = email.trim().toLowerCase()
    if (!normalizedEmail || !password) {
      setErrorMessage('이메일과 비밀번호를 입력해 주세요.')
      return
    }

    setIsSubmitting(true)
    setErrorMessage(null)

    void loginWithPassword(normalizedEmail, password)
      .then((result) => {
        setSession(result.sessionId, result.user)
        navigate(redirectTo, { replace: true })
      })
      .catch((error: unknown) => {
        if (error instanceof HttpError) {
          setErrorMessage(error.message || '로그인에 실패했습니다.')
          return
        }
        setErrorMessage('로그인에 실패했습니다.')
      })
      .finally(() => {
        setIsSubmitting(false)
      })
  }

  return (
    <main className="container py-5">
      <div className="row justify-content-center">
        <div className="col-12 col-md-8 col-lg-5">
          <section className="card shadow-sm">
            <div className="card-body p-4 p-lg-5">
              <h1 className="h4 mb-3">로그인</h1>
              <p className="text-muted small mb-4">
                주문/장바구니/마이페이지 이용을 위해 로그인이 필요합니다.
              </p>

              <form className="d-grid gap-3" onSubmit={handleSubmit}>
                <label className="form-label mb-0">
                  이메일
                  <input
                    className="form-control mt-2"
                    type="email"
                    autoComplete="username"
                    value={email}
                    onChange={(event) => setEmail(event.target.value)}
                    required
                  />
                </label>

                <label className="form-label mb-0">
                  비밀번호
                  <input
                    className="form-control mt-2"
                    type="password"
                    autoComplete="current-password"
                    value={password}
                    onChange={(event) => setPassword(event.target.value)}
                    required
                  />
                </label>

                {errorMessage ? <div className="alert alert-danger py-2 mb-0">{errorMessage}</div> : null}

                <button type="submit" className="btn btn-primary" disabled={isSubmitting}>
                  {isSubmitting ? '로그인 중...' : '로그인'}
                </button>
              </form>

              <div className="mt-3 small text-muted">
                홈으로 돌아가기: <Link to="/">메인 페이지</Link>
              </div>
            </div>
          </section>
        </div>
      </div>
    </main>
  )
}
