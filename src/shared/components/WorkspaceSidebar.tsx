import { Activity, ChartNoAxesCombined, SlidersHorizontal } from 'lucide-react';

interface WorkspaceSidebarProps {
  active: 'mutations' | 'convergence';
  apiStatus?: 'connecting' | 'connected' | 'offline';
}

export function WorkspaceSidebar({ active, apiStatus }: WorkspaceSidebarProps) {
  return (
    <aside className="sidebar">
      <div className="brand-lockup">
        <div className="brand-mark"><Activity size={18} strokeWidth={2.4} /></div>
        <div className="brand-copy"><strong>signal foundry</strong><span>RESEARCH WORKBENCH</span></div>
      </div>
      <div className="nav-label">WORKSPACE</div>
      <nav className="primary-nav" aria-label="Workspace">
        <a className={`nav-item${active === 'mutations' ? ' active' : ''}`} href="#mutation-builder" aria-current={active === 'mutations' ? 'page' : undefined}>
          <SlidersHorizontal size={17} /><span>Mutation builder</span>{active === 'mutations' && <span className="nav-indicator" />}
        </a>
        <a className={`nav-item${active === 'convergence' ? ' active' : ''}`} href="#convergence" aria-current={active === 'convergence' ? 'page' : undefined}>
          <ChartNoAxesCombined size={17} /><span>Convergence testing</span>{active === 'convergence' && <span className="nav-indicator" />}
        </a>
      </nav>
      <div className="sidebar-bottom">
        <div className="local-status">
          <span className={`status-dot${apiStatus === 'offline' || !apiStatus ? ' offline' : ''}`} />
          <span>{apiStatus === 'connected' ? 'Local API connected' : apiStatus === 'connecting' ? 'Connecting' : apiStatus === 'offline' ? active === 'convergence' ? 'Sync disconnected' : 'Sample mode' : 'Frontend preview'}</span>
          <span className="local-lock">{apiStatus === 'connected' ? 'ONLINE' : 'LOCAL'}</span>
        </div>
      </div>
    </aside>
  );
}
