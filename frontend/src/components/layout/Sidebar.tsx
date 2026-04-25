import { NavLink } from 'react-router'
import { LayoutDashboard, Database, Bot, FlaskConical, Shield } from 'lucide-react'
import { cn } from '../../lib/utils'

const links = [
  { to: '/', icon: LayoutDashboard, label: 'Dashboard' },
  { to: '/sources', icon: Database, label: 'Sources' },
  { to: '/agents', icon: Bot, label: 'Agents' },
  { to: '/playground', icon: FlaskConical, label: 'Playground' },
  { to: '/audit', icon: Shield, label: 'Audit' },
]

export default function Sidebar() {
  return (
    <aside className="flex h-screen w-60 flex-col border-r border-zinc-800 bg-zinc-950">
      <div className="flex items-center gap-3 px-5 py-5">
        <img src="/lattice-logo.svg" alt="Lattice" className="h-8 w-8" />
        <div>
          <h1 className="text-lg font-bold tracking-tight text-white">Lattice</h1>
          <p className="text-[10px] uppercase tracking-widest text-zinc-500">Context Engine</p>
        </div>
      </div>
      <nav className="flex-1 space-y-1 px-3 pt-2">
        {links.map(({ to, icon: Icon, label }) => (
          <NavLink
            key={to}
            to={to}
            end={to === '/'}
            className={({ isActive }) =>
              cn(
                'flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors',
                isActive
                  ? 'bg-zinc-800 text-white'
                  : 'text-zinc-400 hover:bg-zinc-800/50 hover:text-zinc-200',
              )
            }
          >
            <Icon className="h-4 w-4" />
            {label}
          </NavLink>
        ))}
      </nav>
      <div className="border-t border-zinc-800 px-5 py-4">
        <p className="text-[10px] text-zinc-600">v0.1.0 — Demo Mode</p>
      </div>
    </aside>
  )
}
