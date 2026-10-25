import { Activity, ArrowRight, ChartNoAxesCombined, ChevronDown, CircleHelp, Command, Database, FlaskConical, Layers3, SlidersHorizontal } from 'lucide-react';

interface WorkspaceSidebarProps {
  active: 'mutations' | 'convergence';
  apiStatus?: 'connecting' | 'connected' | 'offline';
  profileCount?: number;
}

export function WorkspaceSidebar({ active, apiStatus, profileCount }: WorkspaceSidebarProps) {
  return (
    <aside className="sidebar">
      <div className="brand-lockup">
        <div className="brand-mark"><Activity size={18} strokeWidth={2.4} /></div>
        <div className="brand-copy"><strong>signal foundry</strong><span>RESEARCH WORKBENCH</span></div>
      </div>
      <div className="workspace-switcher">
        <div className="workspace-avatar">Q</div>
        <div className="workspace-copy"><span>Workspace</span><strong>Quant research</strong></div>
        <ChevronDown size={15} />
      </div>
      <div className="nav-label">WORKSPACE</div>
      <nav className="primary-nav" aria-label="Workspace">
        <a className="nav-item" href="#evidence"><Database size={17} /><span>Evidence</span></a>
        <a className={`nav-item${active === 'mutations' ? ' active' : ''}`} href="#mutation-builder" aria-current={active === 'mutations' ? 'page' : undefined}>
          <SlidersHorizontal size={17} /><span>Mutation builder</span>{active === 'mutations' && <span className="nav-indicator" />}
        </a>
        <a className="nav-item" href="#profiles"><Layers3 size={17} /><span>Profiles</span>{profileCount !== undefined && <span className="nav-count">{profileCount.toString().padStart(2, '0')}</span>}</a>
        <a className={`nav-item${active === 'convergence' ? ' active' : ''}`} href="#convergence" aria-current={active === 'convergence' ? 'page' : undefined}>
          <ChartNoAxesCombined size={17} /><span>Convergence testing</span>{active === 'convergence' && <span className="nav-indicator" />}
        </a>
        <a className="nav-item disabled" href="#experiments" aria-disabled="true" onClick={(event) => event.preventDefault()}><FlaskConical size={17} /><span>Experiments</span><span className="nav-soon">SOON</span></a>
      </nav>
      <div className="sidebar-bottom">
        <div className="local-status">
          <span className={`status-dot${apiStatus === 'offline' || !apiStatus ? ' offline' : ''}`} />
          <span>{apiStatus === 'connected' ? 'Local API connected' : apiStatus === 'connecting' ? 'Connecting' : apiStatus === 'offline' ? active === 'convergence' ? 'Sync disconnected' : 'Sample mode' : 'Frontend preview'}</span>
          <span className="local-lock">{apiStatus === 'connected' ? 'ONLINE' : 'LOCAL'}</span>
        </div>
        <button className="help-link" type="button" title="Convergence inputs sync to local files; active runs keep a frozen configuration"><CircleHelp size={16} /><span>Workbench guide</span><ArrowRight size={14} /></button>
        <div className="user-row"><div className="user-avatar">AS</div><div><strong>Analyst</strong><span>Personal workspace</span></div><Command size={15} /></div>
      </div>
    </aside>
  );
}
