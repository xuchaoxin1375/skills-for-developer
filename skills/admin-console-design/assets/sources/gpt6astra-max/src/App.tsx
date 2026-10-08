import { useCallback, useEffect, useRef, useState, type KeyboardEvent } from 'react';
import { AlertCircle, ArrowRight, ArrowUpRight, BookOpen, Check, CheckCircle2, ChevronRight, Code2, FlaskConical, Info, Layers, Lightbulb, Menu, Monitor, RotateCcw, Search, X } from 'lucide-react';
import { PAGE_INFO, type Page, type Theme } from './lib/data';
import { useMediaQuery, useStoredState } from './lib/hooks';
import { Sidebar, Brand, NAV_ITEMS, ThemeMenu } from './components/Sidebar';
import { Modal } from './components/Modal';
import { Workbench } from './components/Workbench';
import { DnsConsole } from './components/DnsConsole';
import { DesignDetails, DesignGuide, DesignTokens, DocumentReader, Documentation, Overview } from './components/Documentation';

type Tab = 'preview' | 'principles' | 'implementation';
const TABS: { key: Tab; title: string; icon: typeof Monitor }[] = [
  { key: 'preview', title: '交互预览', icon: Monitor },
  { key: 'principles', title: '设计要点', icon: Lightbulb },
  { key: 'implementation', title: '实现指南', icon: Code2 },
];

function currentPage(): Page {
  const value = new URLSearchParams(window.location.search).get('page');
  return value && Object.prototype.hasOwnProperty.call(PAGE_INFO, value) ? value as Page : 'dns';
}

export default function App() {
  const [page, setPage] = useState<Page>(currentPage);
  const [tab, setTab] = useState<Tab>('preview');
  const [theme, setTheme] = useStoredState<Theme>('edgelab.theme', 'system', value => ['system', 'light', 'dark'].includes(value as string));
  const [pinned, setPinned] = useStoredState('edgelab.sidebar-pinned', true);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);
  const [search, setSearch] = useState('');
  const [aboutOpen, setAboutOpen] = useState(false);
  const [resetOpen, setResetOpen] = useState(false);
  const [standaloneGuide, setStandaloneGuide] = useState(false);
  const [resetVersion, setResetVersion] = useState(0);
  const [toast, setToast] = useState<{ message: string; key: number; tone: 'success' | 'info' | 'error' } | null>(null);
  const systemDark = useMediaQuery('(prefers-color-scheme: dark)');
  const mobile = useMediaQuery('(max-width: 1000px)');
  const tabsRef = useRef<HTMLDivElement>(null);
  const pageRef = useRef(page);
  pageRef.current = page;
  const standalone = new URLSearchParams(window.location.search).get('preview') === '1';
  const isLab = ['dns', 'navigation', 'forms', 'responsive'].includes(page);

  useEffect(() => {
    document.documentElement.dataset.theme = theme === 'system' ? systemDark ? 'dark' : 'light' : theme;
    document.documentElement.style.colorScheme = theme === 'system' ? systemDark ? 'dark' : 'light' : theme;
    document.querySelector('meta[name="theme-color"]')?.setAttribute('content', document.documentElement.dataset.theme === 'dark' ? '#1d2025' : '#ffffff');
  }, [theme, systemDark]);

  useEffect(() => {
    document.title = standalone ? 'DNS 管理预览 | EdgeLab' : `${PAGE_INFO[page].label} | EdgeLab 界面设计实验室`;
  }, [page, standalone]);

  useEffect(() => {
    const onPopState = () => {
      const next = currentPage();
      if (next !== pageRef.current) { setPage(next); setTab('preview'); }
    };
    window.addEventListener('popstate', onPopState);
    return () => window.removeEventListener('popstate', onPopState);
  }, []);

  useEffect(() => {
    const shortcut = (event: globalThis.KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k' && !standalone) {
        event.preventDefault();
        if (!document.querySelector('dialog[open]')) { setSearch(''); setSearchOpen(true); }
      }
    };
    document.addEventListener('keydown', shortcut);
    return () => document.removeEventListener('keydown', shortcut);
  }, [standalone]);

  useEffect(() => { if (!mobile) setMobileOpen(false); }, [mobile]);
  useEffect(() => {
    if (!toast) return;
    const timer = setTimeout(() => setToast(null), 5000);
    return () => clearTimeout(timer);
  }, [toast]);

  const notify = useCallback((message: string, tone: 'success' | 'info' | 'error' = 'success') => setToast({ message, key: Date.now(), tone }), []);
  useEffect(() => {
    try { localStorage.setItem('edgelab.storage-probe', '1'); localStorage.removeItem('edgelab.storage-probe'); }
    catch { notify('本地存储不可用。当前页面仍可操作，但刷新或切换页面后可能丢失修改。', 'info'); }
  }, [notify]);

  function navigate(next: Page) {
    setPage(next);
    setTab('preview');
    setMobileOpen(false);
    setSearchOpen(false);
    const url = new URL(window.location.href);
    url.searchParams.set('page', next);
    url.hash = '';
    if (next !== page) window.history.pushState({ page: next }, '', url);
    window.scrollTo({ top: 0, behavior: 'instant' });
    requestAnimationFrame(() => requestAnimationFrame(() => document.getElementById('main-content')?.focus({ preventScroll: true })));
  }

  function openSearch() { setSearch(''); setSearchOpen(true); }
  function readGuide() {
    setTab('principles');
    requestAnimationFrame(() => {
      document.getElementById('panel-principles')?.focus({ preventScroll: true });
      document.getElementById('page-tabs')?.scrollIntoView({ block: 'start', behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth' });
    });
  }
  function resetDemo() {
    ['records', 'draft', 'favorite', 'compact', 'dnssec', 'development'].forEach(key => { try { localStorage.removeItem(`edgelab.${key}`); } catch { /* The remount also resets an in-memory session. */ } });
    setResetVersion(previous => previous + 1);
    setResetOpen(false);
    notify('已恢复 6 条初始记录，并清空演示草稿。主题偏好保持不变。');
  }

  function tabKeys(event: KeyboardEvent<HTMLButtonElement>, index: number) {
    let next = index;
    if (event.key === 'ArrowRight') next = (index + 1) % TABS.length;
    else if (event.key === 'ArrowLeft') next = (index + TABS.length - 1) % TABS.length;
    else if (event.key === 'Home') next = 0;
    else if (event.key === 'End') next = TABS.length - 1;
    else return;
    event.preventDefault();
    setTab(TABS[next].key);
    tabsRef.current?.querySelectorAll<HTMLButtonElement>('[role="tab"]')[next]?.focus();
  }

  const ToastIcon = toast?.tone === 'error' ? AlertCircle : toast?.tone === 'info' ? Info : CheckCircle2;
  const toastView = <div className="toast-region" aria-live="polite" aria-atomic="true">{toast && <div className={`toast toast-${toast.tone}`} key={toast.key}><ToastIcon size={18} /><span>{toast.message}</span><button className="icon-button" aria-label="关闭通知" onClick={() => setToast(null)}><X size={15} /></button></div>}</div>;

  if (standalone) return <div className="standalone-page">
    <header className="standalone-header"><a href="./" aria-label="返回 EdgeLab"><Brand compact /></a><span>独立响应式预览</span><ThemeMenu theme={theme} onChange={setTheme} /></header>
    <main className="standalone-console preview-frame"><DnsConsole onReadGuide={() => setStandaloneGuide(true)} onToast={notify} /></main>
    {standaloneGuide && <Modal title="DNS 管理设计说明" onClose={() => setStandaloneGuide(false)} className="guide-dialog"><div className="modal-body"><DocumentReader documentId="02-interaction-spec" /></div></Modal>}
    {toastView}
  </div>;

  return <div className={`app-shell ${pinned ? 'nav-pinned' : 'nav-collapsed'}`}>
    <a className="skip-link" href="#main-content">跳到主要内容</a>
    <div className="desktop-sidebar"><Sidebar page={page} onNavigate={navigate} pinned={pinned} onToggle={() => setPinned(!pinned)} onSearch={openSearch} onAbout={() => setAboutOpen(true)} /></div>
    <div className="workspace-main">
      <header className="topbar">
        <button className="icon-button mobile-menu-button" onClick={() => setMobileOpen(true)} aria-label="打开工作台导航"><Menu size={20} /></button>
        <div className="breadcrumb"><Layers size={16} /><span>工作空间</span><ChevronRight size={13} /><strong>设计实验室</strong></div>
        <div className="mobile-top-brand">EdgeLab</div>
        <div className="topbar-actions"><button className="header-docs" onClick={() => navigate('docs')}><BookOpen size={15} /><span>使用指南</span><ArrowUpRight size={12} /></button><span className="topbar-divider" /><ThemeMenu theme={theme} onChange={setTheme} /><button className="user-avatar" aria-label="关于本地演示账户" onClick={() => setAboutOpen(true)}>L</button></div>
      </header>
      <main id="main-content" className="page-content" tabIndex={-1}>
        <div className="page-heading page-enter"><div><div className="page-title-line"><h1>{PAGE_INFO[page].title}</h1>{page === 'dns' && <span className="title-label">Cloudflare-inspired</span>}</div><p>{PAGE_INFO[page].subtitle}</p></div>{isLab && <button className="button reset-button" aria-label="重置演示" onClick={() => setResetOpen(true)}><RotateCcw size={14} /><span>重置演示</span></button>}</div>
        {isLab ? <>
          <div className="content-tabs" id="page-tabs"><div className="tabs-list" role="tablist" aria-label="案例查看模式" ref={tabsRef}>{TABS.map(({ key, title, icon: Icon }, index) => <button key={key} role="tab" id={`tab-${key}`} aria-controls={`panel-${key}`} aria-selected={tab === key} tabIndex={tab === key ? 0 : -1} className={tab === key ? 'active' : ''} onClick={() => setTab(key)} onKeyDown={event => tabKeys(event, index)}><Icon size={15} />{title}</button>)}</div><span className="live-preview-label"><span className="status-dot" />可交互的设计参考</span></div>
          <section id={`panel-${tab}`} role="tabpanel" aria-labelledby={`tab-${tab}`} tabIndex={0} className="tab-panel" key={tab}>
            {tab === 'preview' ? <><Workbench key={`${resetVersion}-${page}`} page={page} onNavigate={navigate} onReadGuide={readGuide} onToast={notify} /><DesignDetails onNavigate={navigate} /></> : tab === 'principles' ? <DesignGuide onNavigate={navigate} /> : <DocumentReader documentId={page === 'forms' || page === 'navigation' ? '02-interaction-spec' : '03-development'} />}
          </section>
        </> : page === 'overview' ? <Overview onNavigate={navigate} /> : page === 'guidelines' ? <DesignGuide onNavigate={navigate} /> : page === 'tokens' ? <DesignTokens onToast={notify} /> : <Documentation onToast={notify} />}
        <footer className="page-footer"><span><FlaskConical size={13} />EdgeLab<span className="footer-dot">·</span>让好的体验，有迹可循。</span><span>独立设计研究<span className="footer-dot">/</span>非 Cloudflare 官方产品</span></footer>
      </main>
    </div>
    {mobileOpen && <Modal title="工作台导航" onClose={() => setMobileOpen(false)} className="mobile-nav-dialog"><Sidebar mobile page={page} onNavigate={navigate} pinned onToggle={() => setMobileOpen(false)} onSearch={() => { setMobileOpen(false); openSearch(); }} onAbout={() => { setMobileOpen(false); setAboutOpen(true); }} /></Modal>}
    {searchOpen && <Modal title="快速前往" onClose={() => setSearchOpen(false)} className="search-dialog"><div className="command-input"><Search size={19} /><input data-autofocus aria-label="搜索设计案例与文档" value={search} onChange={event => setSearch(event.target.value)} placeholder="搜索设计案例与文档..." onKeyDown={event => { if (event.key === 'ArrowDown') { event.preventDefault(); document.querySelector<HTMLButtonElement>('.command-result')?.focus(); } }} /><kbd>ESC</kbd></div><div className="command-results">{NAV_ITEMS.filter(item => `${item.label} ${item.group} ${item.page}`.toLowerCase().includes(search.toLowerCase())).map(({ page: itemPage, label, group, icon: Icon }) => <button className="command-result" key={itemPage} onClick={() => navigate(itemPage)}><Icon size={18} /><span>{label}<small>{group}</small></span>{page === itemPage ? <Check size={16} /> : <ArrowRight size={16} />}</button>)}{!NAV_ITEMS.some(item => `${item.label} ${item.group} ${item.page}`.toLowerCase().includes(search.toLowerCase())) && <p className="command-empty">没有匹配的页面，试试“表单”或“设计”。</p>}</div><div className="command-footer"><span><kbd>Tab</kbd>切换结果</span><span><kbd>Enter</kbd>前往页面</span></div></Modal>}
    {aboutOpen && <Modal title="关于 EdgeLab" description="一个认真对待细节的界面设计实验室。" onClose={() => setAboutOpen(false)}><div className="modal-body about-content"><div className="about-brand"><Brand /></div><p>参考 Cloudflare 控制台的成熟实践，探索更清晰的导航、更可靠的表单，以及适应每一块屏幕的布局。</p><div className="about-account"><span className="user-avatar">L</span><div><strong>本地体验者</strong><p>无需登录 · 数据仅保留在当前浏览器</p></div></div><p className="muted">这是独立设计研究，与 Cloudflare 没有隶属或合作关系。所有域名、记录与设置均为演示，不能用于真实流量管理。</p><a className="text-button" href="https://blog.cloudflare.com/dark-mode/" target="_blank" rel="noreferrer">阅读官方设计实践<ArrowUpRight size={14} /></a></div><div className="modal-actions"><button className="button primary" onClick={() => setAboutOpen(false)}>开始探索<ArrowRight size={15} /></button></div></Modal>}
    {resetOpen && <Modal title="恢复初始演示？" description="将恢复 6 条示例 DNS 记录，并清除未保存的新增草稿、收藏和站点演示设置。你的主题偏好不会改变。" onClose={() => setResetOpen(false)}><div className="modal-actions"><button className="button" data-autofocus onClick={() => setResetOpen(false)}>保留当前演示</button><button className="button primary" onClick={resetDemo}><RotateCcw size={14} />确认重置</button></div></Modal>}
    {toastView}
  </div>;
}
