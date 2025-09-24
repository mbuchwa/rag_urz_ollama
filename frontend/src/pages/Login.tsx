import { FormEvent, useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { useAuth } from '../context/AuthContext'

export default function Login() {
  const { user, loading, refresh } = useAuth()
  const navigate = useNavigate()
  const [email, setEmail] = useState('test@uni-heidelberg.de')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  const canSubmit = useMemo(() => email.trim().length > 0 && password.length > 0 && !submitting, [
    email,
    password,
    submitting,
  ])

  useEffect(() => {
    if (!loading && user) {
      navigate('/chat', { replace: true })
    }
  }, [loading, user, navigate])

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (!canSubmit) return
    setSubmitting(true)
    setError(null)
    try {
      const response = await fetch('/auth/local-login', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        credentials: 'include',
        body: JSON.stringify({ email, password }),
      })

      if (!response.ok) {
        const payload = await response.json().catch(() => null)
        const detail = typeof payload?.detail === 'string' ? payload.detail : 'Login fehlgeschlagen'
        setError(detail)
        return
      }

      await refresh()
      navigate('/chat', { replace: true })
    } catch (err) {
      console.error('Login request failed', err)
      setError('Verbindung fehlgeschlagen. Bitte später erneut versuchen.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="login-page">
      <div className="login-card">
        <header className="login-header">
          <div className="login-logo">heiBOX</div>
          <div className="login-subtitle">Universitätsrechenzentrum Heidelberg</div>
        </header>
        <main>
          <h1 className="login-title">Anmelden</h1>
          <form className="login-form" onSubmit={handleSubmit}>
            <label className="login-label" htmlFor="email">
              Benutzername
            </label>
            <input
              id="email"
              type="email"
              autoComplete="email"
              className="login-input"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              placeholder="test@uni-heidelberg.de"
              required
            />

            <label className="login-label" htmlFor="password">
              Passwort
            </label>
            <input
              id="password"
              type="password"
              autoComplete="current-password"
              className="login-input"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              placeholder="Passwort eingeben"
              required
            />

            <label className="login-remember">
              <input type="checkbox" disabled />
              <span>Für 7 Tage an mich erinnern</span>
            </label>

            {error ? <div className="login-error">{error}</div> : null}

            <button className="login-button" type="submit" disabled={!canSubmit}>
              {submitting ? 'Wird angemeldet…' : 'Anmelden'}
            </button>
          </form>
        </main>
        <footer className="login-footer">
          <button
            className="login-link"
            type="button"
            onClick={() => {
              window.location.href = '/auth/login'
            }}
          >
            Mit OIDC anmelden
          </button>
          <div className="login-language">Deutsch ▾</div>
        </footer>
      </div>
    </div>
  )
}
