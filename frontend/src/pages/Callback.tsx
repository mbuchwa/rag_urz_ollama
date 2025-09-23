import { useEffect } from 'react'
import { useNavigate } from 'react-router-dom'

import { useAuth } from '../context/AuthContext'

export default function Callback() {
  const { refresh } = useAuth()
  const navigate = useNavigate()

  useEffect(() => {
    let active = true
    ;(async () => {
      const ok = await refresh()
      if (!active) return
      navigate(ok ? '/chat' : '/login', { replace: true })
    })()

    return () => {
      active = false
    }
  }, [refresh, navigate])

  return (
    <div className="flex min-h-screen items-center justify-center">
      <div className="rounded-xl bg-white/95 px-8 py-6 text-center shadow">
        <p className="text-gray-700">Completing sign-in&hellip;</p>
      </div>
    </div>
  )
}
