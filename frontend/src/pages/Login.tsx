import { useEffect } from 'react'
import { useNavigate } from 'react-router-dom'

import { useAuth } from '../context/AuthContext'

export default function Login() {
  const { user, loading } = useAuth()
  const navigate = useNavigate()

  useEffect(() => {
    if (!loading && user) {
      navigate('/chat', { replace: true })
    }
  }, [loading, user, navigate])

  return (
    <div className="flex min-h-screen items-center justify-center">
      <div className="rounded-xl bg-white/95 px-8 py-10 text-center shadow-xl">
        <h1 className="mb-6 text-2xl font-semibold text-gray-800">Welcome to the URZ Chatbot</h1>
        <p className="mb-8 text-gray-600">Sign in with your organization account to continue.</p>
        <button
          onClick={() => {
            window.location.href = '/auth/login'
          }}
          className="rounded-full bg-[#b52230] px-6 py-3 text-white shadow hover:bg-[#9f1e2a]"
        >
          Sign in with OIDC
        </button>
      </div>
    </div>
  )
}
