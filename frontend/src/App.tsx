import { Routes, Route } from 'react-router'
import Shell from './components/layout/Shell'
import Dashboard from './pages/Dashboard'
import Sources from './pages/Sources'
import Agents from './pages/Agents'
import Playground from './pages/Playground'
import AuditLog from './pages/AuditLog'

export default function App() {
  return (
    <Shell>
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/sources" element={<Sources />} />
        <Route path="/agents" element={<Agents />} />
        <Route path="/playground" element={<Playground />} />
        <Route path="/audit" element={<AuditLog />} />
      </Routes>
    </Shell>
  )
}
