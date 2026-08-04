import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { useState, useEffect } from 'react'
import Layout from './components/Layout'
import LoginForm from './components/LoginForm'
import DiscoveryForm from './components/DiscoveryForm'
import TopologyViewer from './components/TopologyViewer'
import { setToken } from './api'

export default function App() {
  const [loggedIn, setLoggedIn] = useState(false)

  useEffect(() => {
    setLoggedIn(!!localStorage.getItem('token'))
  }, [])

  if (!loggedIn) {
    return (
      <LoginForm
        onSuccess={() => setLoggedIn(true)}
      />
    )
  }

  return (
    <BrowserRouter>
      <Layout onLogout={() => { setToken(null); setLoggedIn(false) }}>
        <Routes>
          <Route path="/" element={<TopologyViewer />} />
          <Route path="/discover" element={<DiscoveryForm />} />
          <Route path="/topology" element={<TopologyViewer />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </Layout>
    </BrowserRouter>
  )
}
