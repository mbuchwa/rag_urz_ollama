import { Navigate } from 'react-router-dom'

import { useAuth } from '../context/AuthContext'

type Props = {
  children: JSX.Element
}

export default function ProtectedRoute({ children }: Props) {
  const { user, loading } = useAuth()

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <div className="rounded-xl bg-white/95 px-8 py-6 text-center shadow">
          <p className="text-gray-700">Checking authentication&hellip;</p>
        </div>
      </div>
    )
  }

  if (!user) {
    return <Navigate to="/login" replace />
  }

  return children
}
