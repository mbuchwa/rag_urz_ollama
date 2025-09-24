import { useState, ChangeEvent } from 'react'
import { useNavigate } from 'react-router-dom'

import { useAuth } from '../context/AuthContext'

type Props = {
  selectedNamespaceId: string | null
  onNamespaceChange: (namespaceId: string) => void
}

export default function Navbar({ selectedNamespaceId, onNamespaceChange }: Props) {
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

  const namespace = namespaces.find((ns) => ns.id === selectedNamespaceId) || namespaces[0] || null

  const handleNamespaceChange = (event: ChangeEvent<HTMLSelectElement>) => {
    const value = event.target.value
    onNamespaceChange(value)
  }

  return (
    <nav className="flex w-full flex-col gap-2 bg-white/90 px-4 py-3 text-sm text-gray-700 shadow md:flex-row md:items-center md:justify-between">
      <div className="flex flex-col md:flex-row md:items-center md:gap-3">
        <span className="font-medium text-gray-800">
          {user?.displayName || user?.email || 'Authenticated User'}
        </span>
        {namespaces.length > 0 && (
          <select
            value={namespace?.id || ''}
            onChange={handleNamespaceChange}
            className="mt-1 rounded-full border border-gray-200 bg-white px-3 py-1 text-xs text-gray-600 shadow-sm md:mt-0"
          >
            {namespaces.map((ns) => (
              <option key={ns.id} value={ns.id}>
                {ns.name}
              </option>
            ))}
          </select>
        )}
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
