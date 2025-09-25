import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'

import Home from './components/Home'
import Callback from './pages/Callback'
import Login from './pages/Login'
import ProtectedRoute from './pages/ProtectedRoute'
import { useAuth } from './context/AuthContext'
import { getClientAssets } from './utils/clientAssets'

export default function App() {
  const { namespaces } = useAuth()
  const { background } = getClientAssets(namespaces[0]?.slug)

  return (
    <BrowserRouter>
      <div
        className="flex min-h-screen flex-col bg-cover bg-center"
        style={background ? { backgroundImage: `url(${background})` } : undefined}
      >
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/callback" element={<Callback />} />
          <Route
            path="/chat"
            element={
              <ProtectedRoute>
                <Home />
              </ProtectedRoute>
            }
          />
          <Route path="/" element={<Navigate to="/chat" replace />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </div>
    </BrowserRouter>
  )
}