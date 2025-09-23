import { useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { useAuth } from '../context/AuthContext'

export default function Navbar() {
  const { user, namespaces, logout } = useAuth()
  const navigate = useNavigate()
  const [pending, setPending] = useState(false)

  const handleLogout = async () => {
    setPending(true)
    try {
      await logout()
      navigate('/login', { replace: true })
    } finally {
      setPending(false)
    }
  }

  const namespace = namespaces[0]

  return (
    <nav className="flex w-full flex-col gap-2 bg-white/90 px-4 py-3 text-sm text-gray-700 shadow md:flex-row md:items-center md:justify-between">
      <div className="flex flex-col md:flex-row md:items-center md:gap-3">
        <span className="font-medium text-gray-800">
          {user?.displayName || user?.email || 'Authenticated User'}
        </span>
        {namespace && <span className="text-gray-500">{namespace.name}</span>}
      </div>
      <button
        onClick={handleLogout}
        disabled={pending}
        className="self-start rounded-full bg-[#b52230] px-4 py-2 text-white shadow hover:bg-[#9f1e2a] disabled:cursor-not-allowed disabled:opacity-60 md:self-auto"
      >
        {pending ? 'Logging out…' : 'Logout'}
      </button>
    </nav>
  )
}
