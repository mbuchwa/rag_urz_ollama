import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'

import Home from './components/Home'
import Callback from './pages/Callback'
import Login from './pages/Login'
import ProtectedRoute from './pages/ProtectedRoute'
import background from '/imgs/background.jpg'

export default function App() {
  return (
    <BrowserRouter>
      <div
        className="flex min-h-screen flex-col bg-cover bg-center"
        style={{ backgroundImage: `url(${background})` }}
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