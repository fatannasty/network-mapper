import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { useState, useEffect } from 'react'
import AppShell from './app/layouts/AppShell'
import LoginForm from './components/LoginForm'
import Ingest from './components/Ingest'
import TopologyViewer from './components/TopologyViewer'
import DeviceInventory from './components/DeviceInventory'
import DataQuality from './components/DataQuality'
import OperationsDashboard from './components/OperationsDashboard'
import AdminPage from './components/AdminPage'
import { getMe, logout, setToken } from './api'

export default function App() {
  const [loggedIn, setLoggedIn] = useState(false)
  const [checking, setChecking] = useState(true)

  useEffect(() => {
    getMe()
      .then(() => setLoggedIn(true))
      .catch(() => setLoggedIn(false))
      .finally(() => setChecking(false))
  }, [])

  if (checking) {
    return (
      <div className="min-h-screen flex items-center justify-center text-muted text-sm">
        Checking session…
      </div>
    )
  }

  if (!loggedIn) {
    return (
      <LoginForm
        onSuccess={() => setLoggedIn(true)}
      />
    )
  }

  return (
    <BrowserRouter>
      <AppShell onLogout={() => { setToken(null); void logout(); setLoggedIn(false) }}>
        <Routes>
          <Route path="/" element={<Navigate to="/topology" replace />} />
          <Route path="/dashboard" element={<OperationsDashboard />} />
          <Route path="/topology" element={<TopologyViewer />} />
          <Route path="/ingest" element={<Ingest />} />
          <Route path="/inventory" element={<DeviceInventory />} />
          <Route path="/quality" element={<DataQuality />} />
          <Route path="/admin" element={<AdminPage />} />
          {/* Legacy redirects */}
          <Route path="/discover" element={<Navigate to="/ingest" replace />} />
          <Route path="/catalyst" element={<Navigate to="/ingest?tab=catalyst" replace />} />
          <Route path="/meraki" element={<Navigate to="/ingest?tab=meraki" replace />} />
          <Route path="/velocloud" element={<Navigate to="/ingest?tab=velocloud" replace />} />
          <Route path="/reports" element={<Navigate to="/dashboard" replace />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </AppShell>
    </BrowserRouter>
  )
}
