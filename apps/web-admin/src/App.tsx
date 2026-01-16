import './App.css'

function App() {
  const apiBaseUrl = import.meta.env.VITE_API_BASE_URL
  const searchBaseUrl = import.meta.env.VITE_SEARCH_BASE_URL
  const envReady = Boolean(apiBaseUrl && searchBaseUrl)

  return (
    <div className="app">
      <header className="hero">
        <p className="eyebrow">Admin Console</p>
        <h1>BSL Web Admin</h1>
        <p className={`status ${envReady ? 'ready' : ''}`}>
          {envReady ? 'Env loaded ✅' : 'Env missing'}
        </p>
      </header>

      <section className="env-card">
        <div className="env-row">
          <span className="label">VITE_API_BASE_URL</span>
          <span className="value">{apiBaseUrl || '(unset)'}</span>
        </div>
        <div className="env-row">
          <span className="label">VITE_SEARCH_BASE_URL</span>
          <span className="value">{searchBaseUrl || '(unset)'}</span>
        </div>
      </section>

      <p className="footnote">
        Update <code>.env</code> and refresh to reload values.
      </p>
    </div>
  )
}

export default App
