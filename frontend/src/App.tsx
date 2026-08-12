import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { useState, useEffect } from 'react'
import AppShell from './app/layouts/AppShell'
import LoginForm from './components/LoginForm'
import Ingest from './components/Ingest'
import TopologyViewer from './components/TopologyViewer'
import Configs from './components/Configs'
import DeviceInventory from './components/DeviceInventory'
import DataQuality from './components/DataQuality'
import OperationsDashboard from './components/OperationsDashboard'
import AdminPage from './components/AdminPage'
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
      <AppShell onLogout={() => { setToken(null); setLoggedIn(false) }}>
        <Routes>
          <Route path="/" element={<Navigate to="/topology" replace />} />
          <Route path="/dashboard" element={<OperationsDashboard />} />
          <Route path="/topology" element={<TopologyViewer />} />
          <Route path="/ingest" element={<Ingest />} />
          <Route path="/configs" element={<Configs />} />
          <Route path="/inventory" element={<DeviceInventory />} />
          <Route path="/quality" element={<DataQuality />} />
          <Route path="/admin" element={<AdminPage />} />
          {/* Legacy redirects */}
          <Route path="/discover" element={<Navigate to="/ingest" replace />} />
          <Route path="/catalyst" element={<Navigate to="/ingest?tab=catalyst" replace />} />
          <Route path="/meraki" element={<Navigate to="/ingest?tab=meraki" replace />} />
          <Route path="/velocloud" element={<Navigate to="/ingest?tab=velocloud" replace />} />
          <Route path="/changes" element={<Navigate to="/configs?tab=changes" replace />} />
          <Route path="/reports" element={<Navigate to="/dashboard" replace />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </AppShell>
    </BrowserRouter>
  )
}
