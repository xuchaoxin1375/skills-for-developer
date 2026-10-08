import { useState } from 'react';
import {
  ArrowUpRight, BookOpen, Check, ChevronDown, ChevronsUpDown, CircleHelp,
  FileText, FlaskConical, Grid2X2, LayoutPanelLeft, MonitorSmartphone,
  Monitor, Moon, Network, PanelLeftClose, PanelLeftOpen, Search, SlidersHorizontal, Sun, SwatchBook,
  type LucideIcon,
} from 'lucide-react';
import { useHoverNavigation, useOutsideClose, useStoredState } from '../lib/hooks';
import type { Page } from '../lib/data';

export const NAV_ITEMS: { page: Page; label: string; icon: LucideIcon; group: string }[] = [
  { page: 'overview', label: '设计总览', icon: Grid2X2, group: '开始探索' },
  { page: 'navigation', label: '侧边栏导航', icon: LayoutPanelLeft, group: '交互案例' },
  { page: 'dns', label: 'DNS 管理', icon: Network, group: '交互案例' },
  { page: 'forms', label: '表单与校验', icon: SlidersHorizontal, group: '交互案例' },
  { page: 'responsive', label: '响应式布局', icon: MonitorSmartphone, group: '交互案例' },
  { page: 'guidelines', label: '设计规范', icon: BookOpen, group: '设计资源' },
  { page: 'tokens', label: '设计令牌', icon: SwatchBook, group: '设计资源' },
  { page: 'docs', label: '交付文档', icon: FileText, group: '设计资源' },
];

export function Brand({ compact = false }: { compact?: boolean }) {
  return <div className={`brand ${compact ? 'compact-brand' : ''}`}>
    <span className="brand-mark" aria-hidden="true"><FlaskConical size={25} strokeWidth={2.1} /></span>
    <span className="brand-word">Edge<span>Lab</span><small>界面设计实验室</small></span>
  </div>;
}

interface SidebarProps {
  page: Page;
  onNavigate: (page: Page) => void;
  pinned: boolean;
  onToggle: () => void;
  onSearch: () => void;
  onAbout: () => void;
  mobile?: boolean;
}

export function Sidebar({ page, onNavigate, pinned, onToggle, onSearch, onAbout, mobile = false }: SidebarProps) {
  const hover = useHoverNavigation(pinned || mobile);
  const expanded = hover.expanded || mobile;
  const [workspace, setWorkspace] = useStoredState('edgelab.workspace', 'Acme Workspace', value => ['Acme Workspace', 'Personal Studio'].includes(value as string));
  const [workspaceOpen, setWorkspaceOpen] = useState(false);
  const workspaceRef = useOutsideClose(workspaceOpen, () => setWorkspaceOpen(false));

  return <aside className={`sidebar ${expanded ? 'expanded' : 'collapsed'} ${mobile ? 'mobile-sidebar' : ''} ${!pinned && expanded ? 'peeking' : ''}`} {...hover.handlers} aria-label="工作台导航">
    <button className="brand-button" onClick={() => onNavigate('overview')} aria-label="EdgeLab 设计总览"><Brand /></button>
    <div className="sidebar-scroll">
      <div className="workspace-wrap" ref={workspaceRef}>
        <button className="workspace-button" onClick={() => setWorkspaceOpen(!workspaceOpen)} aria-expanded={workspaceOpen} aria-label={`切换工作空间，当前 ${workspace}`}>
          <span className="workspace-avatar">{workspace === 'Acme Workspace' ? 'A' : 'P'}</span>
          <span className="sidebar-label workspace-label"><strong>{workspace}</strong><small>示例工作空间</small></span>
          <ChevronsUpDown size={14} className="sidebar-label" />
        </button>
        {workspaceOpen && <div className="popover workspace-menu">
          <p className="popover-caption">切换工作空间</p>
          {['Acme Workspace', 'Personal Studio'].map(name => <button className="menu-item" key={name} onClick={() => { setWorkspace(name); setWorkspaceOpen(false); workspaceRef.current?.querySelector<HTMLButtonElement>('[aria-expanded]')?.focus(); }}><span>{name}</span>{name === workspace && <Check size={15} />}</button>)}
          <p className="popover-footnote">空间仅用于展示导航上下文，共享本地演示记录。</p>
        </div>}
      </div>
      <button className="sidebar-search" onClick={onSearch} aria-label="搜索页面，快捷键 Control K"><Search size={16} /><span className="sidebar-label">搜索页面...</span><kbd className="sidebar-label">⌘ K</kbd></button>
      <nav>
        {['开始探索', '交互案例', '设计资源'].map(group => <div className="nav-group" key={group}>
          <div className="nav-group-title"><span className="sidebar-label">{group}</span><span className="collapsed-divider" /></div>
          {NAV_ITEMS.filter(item => item.group === group).map(({ page: itemPage, label, icon: Icon }) =>
            <button className={`nav-item ${page === itemPage ? 'active' : ''}`} key={itemPage}
              onClick={() => onNavigate(itemPage)} aria-current={page === itemPage ? 'page' : undefined} aria-label={label} title={!expanded ? label : undefined}>
              <Icon size={18} /><span className="sidebar-label">{label}</span>
              {itemPage === 'dns' && <span className="nav-demo-label sidebar-label">综合案例</span>}
              {page === itemPage && <span className="active-dot sidebar-label" />}
            </button>)}
        </div>)}
      </nav>
    </div>
    <div className="sidebar-bottom">
      <button className="nav-item help-item" onClick={onAbout} aria-label="关于这个实验室"><CircleHelp size={18} /><span className="sidebar-label">关于这个实验室</span><ArrowUpRight className="sidebar-label end-icon" size={14} /></button>
      <div className="sidebar-bottom-line" />
      <button className="nav-item collapse-button" onClick={() => { hover.reset(); onToggle(); }} data-nav-toggle aria-label={mobile ? '关闭导航' : pinned ? '收起侧边栏' : '固定展开侧边栏'} aria-expanded={expanded}>
        {pinned || mobile ? <PanelLeftClose size={18} /> : <PanelLeftOpen size={18} />}
        <span className="sidebar-label">{mobile ? '关闭导航' : pinned ? '收起侧边栏' : '固定侧边栏'}</span><span className="sidebar-label version-label">v1.0</span>
      </button>
    </div>
  </aside>;
}

export function ThemeMenu({ theme, onChange }: { theme: 'system' | 'light' | 'dark'; onChange: (theme: 'system' | 'light' | 'dark') => void }) {
  const [open, setOpen] = useState(false);
  const ref = useOutsideClose(open, () => setOpen(false));
  const ThemeIcon = theme === 'system' ? Monitor : theme === 'light' ? Sun : Moon;
  return <div className="theme-menu" ref={ref}>
    <button className="theme-trigger" onClick={() => setOpen(!open)} aria-expanded={open} aria-label="切换外观主题" title="外观主题"><ThemeIcon size={17} /><ChevronDown size={12} /></button>
    {open && <div className="popover theme-popover">
      <p className="popover-caption">外观主题</p>
      {([['system', '跟随系统', Monitor], ['light', '浅色模式', Sun], ['dark', '深色模式', Moon]] as const).map(([value, label, Icon]) => <button key={value} className="menu-item" aria-pressed={theme === value} onClick={() => { onChange(value); setOpen(false); ref.current?.querySelector<HTMLButtonElement>('[aria-expanded]')?.focus(); }}><Icon size={16} /><span>{label}</span>{theme === value && <Check size={15} />}</button>)}
    </div>}
  </div>;
}