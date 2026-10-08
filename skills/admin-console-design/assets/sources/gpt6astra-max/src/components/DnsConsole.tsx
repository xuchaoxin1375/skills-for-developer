import { useDeferredValue, useEffect, useMemo, useRef, useState, type FormEvent } from 'react';
import {
  ArrowDown, ArrowDownUp, ArrowLeft, ArrowUpRight, BookOpen, ChartNoAxesCombined,
  ChevronDown, ChevronLeft, ChevronRight, Cloud, Download,
  Ellipsis, Filter, Globe, Info, LayoutDashboard, LockKeyhole, Mail, Menu, Network,
  PanelLeftClose, PanelLeftOpen, Plus, Search, SearchX, Settings,
  ShieldCheck, SlidersHorizontal, Star, Trash2, Upload, X, Zap,
} from 'lucide-react';
import {
  createId, DOMAIN, downloadFile, EMPTY_RECORD, isDnsRecord, recordKey, RECORD_TYPES,
  SEED_RECORDS, supportsProxy, validateRecord, type DnsRecord, type RecordDraft, type RecordType,
} from '../lib/data';
import { useHoverNavigation, useOutsideClose, useStoredState } from '../lib/hooks';
import { Modal } from './Modal';
import { RecordForm } from './RecordForm';

interface DnsConsoleProps {
  scene?: 'dns' | 'forms';
  hoverEnabled?: boolean;
  hoverDelay?: number;
  simulateFailure?: boolean;
  onReadGuide: () => void;
  onShowRecords?: () => void;
  onToast: (message: string) => void;
}

type FilterRule = { id: string; field: 'name' | 'type' | 'content' | 'proxied'; operator: 'contains' | 'equals'; value: string };
type SiteSection = 'overview' | 'analytics' | 'dns' | 'email' | 'security' | 'performance' | 'settings';
const SITE_NAV = [
  { id: 'overview' as const, label: '概览', icon: LayoutDashboard },
  { id: 'analytics' as const, label: '分析', icon: ChartNoAxesCombined },
  { id: 'dns' as const, label: 'DNS', icon: Network },
  { id: 'email' as const, label: '电子邮件', icon: Mail },
  { id: 'security' as const, label: '安全性', icon: ShieldCheck },
  { id: 'performance' as const, label: '性能', icon: Zap },
  { id: 'settings' as const, label: '设置', icon: Settings },
];

export function DnsConsole({ scene = 'dns', hoverEnabled = true, hoverDelay = 120, simulateFailure = false, onReadGuide, onShowRecords, onToast }: DnsConsoleProps) {
  const [records, setRecords] = useStoredState<DnsRecord[]>('edgelab.records', SEED_RECORDS, value => Array.isArray(value) && value.length <= 200 && value.every(isDnsRecord) && new Set(value.map(record => record.id)).size === value.length);
  const [pinned, setPinned] = useState(false);
  const hover = useHoverNavigation(pinned, hoverEnabled, hoverDelay);
  const [section, setSection] = useState<SiteSection>('dns');
  const [mobileNav, setMobileNav] = useState(false);
  const [favorite, setFavorite] = useStoredState('edgelab.favorite', false);
  const [notice, setNotice] = useState(true);
  const [query, setQuery] = useState('');
  const deferredQuery = useDeferredValue(query);
  const [rules, setRules] = useState<FilterRule[]>([]);
  const [draftRules, setDraftRules] = useState<FilterRule[]>([{ id: 'initial', field: 'type', operator: 'equals', value: 'A' }]);
  const [filterOpen, setFilterOpen] = useState(false);
  const [displayOpen, setDisplayOpen] = useState(false);
  const [compact, setCompact] = useStoredState('edgelab.compact', false);
  const [showContent, setShowContent] = useState(true);
  const [showTtl, setShowTtl] = useState(true);
  const [selected, setSelected] = useState<string[]>([]);
  const [sort, setSort] = useState<{ field: 'name' | 'type'; ascending: boolean } | null>(null);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const [editor, setEditor] = useState<DnsRecord | 'new' | null>(null);
  const [deleteIds, setDeleteIds] = useState<string[]>([]);
  const [importOpen, setImportOpen] = useState(false);
  const consoleRef = useRef<HTMLDivElement>(null);
  const [narrow, setNarrow] = useState(() => window.innerWidth <= 640);
  const selectAll = useRef<HTMLInputElement>(null);
  const filterRef = useOutsideClose(filterOpen, () => setFilterOpen(false));
  const displayRef = useOutsideClose(displayOpen, () => setDisplayOpen(false));
  const isTable = section === 'dns' || section === 'email';

  function closeFilters() {
    setFilterOpen(false);
    filterRef.current?.querySelector<HTMLButtonElement>('[aria-expanded]')?.focus();
  }

  const filteredRecords = useMemo(() => {
    const search = deferredQuery.trim().toLowerCase();
    const result = records.filter(record => {
      if (section === 'email' && !['MX', 'TXT'].includes(record.type)) return false;
      if (search && !`${record.name} ${record.name === '@' ? DOMAIN : `${record.name}.${DOMAIN}`} ${record.type} ${record.content} ${record.comment}`.toLowerCase().includes(search)) return false;
      return rules.every(rule => {
        const value = String(record[rule.field]).toLowerCase();
        const target = rule.value.toLowerCase();
        return rule.operator === 'equals' ? value === target : value.includes(target);
      });
    });
    if (sort) result.sort((a, b) => a[sort.field].localeCompare(b[sort.field]) * (sort.ascending ? 1 : -1));
    return result;
  }, [records, deferredQuery, rules, sort, section]);

  const totalPages = Math.max(1, Math.ceil(filteredRecords.length / pageSize));
  const currentPage = Math.min(page, totalPages);
  const visibleRecords = filteredRecords.slice((currentPage - 1) * pageSize, currentPage * pageSize);
  const allSelected = visibleRecords.length > 0 && visibleRecords.every(record => selected.includes(record.id));
  const someSelected = visibleRecords.some(record => selected.includes(record.id));

  useEffect(() => { setPage(1); setSelected([]); }, [query, rules, pageSize, section]);
  useEffect(() => { if (selectAll.current) selectAll.current.indeterminate = someSelected && !allSelected; }, [someSelected, allSelected, narrow, displayOpen]);
  useEffect(() => {
    const node = consoleRef.current;
    if (!node) return;
    const observer = new ResizeObserver(entries => {
      const isNarrow = entries[0].contentRect.width <= 640;
      setNarrow(isNarrow);
      if (isNarrow && node.querySelector('.site-sidebar')?.contains(document.activeElement)) {
        node.querySelector<HTMLButtonElement>('.site-mobile-menu')?.focus({ preventScroll: true });
      } else if (isNarrow && node.querySelector('thead')?.contains(document.activeElement)) {
        node.querySelector<HTMLInputElement>('.record-search input')?.focus({ preventScroll: true });
      }
    });
    observer.observe(node);
    return () => observer.disconnect();
  }, []);

  function navigateSite(next: SiteSection) {
    setSection(next);
    setMobileNav(false);
    setQuery('');
    setRules([]);
    if (scene === 'forms') onShowRecords?.();
  }

  async function saveRecord(draft: RecordDraft, id?: string) {
    if (!id && records.length >= 200) throw new Error('演示记录数量上限为 200 条，请先删除不需要的记录。');
    if (records.some(record => record.id !== id && recordKey(record) === recordKey(draft))) throw new Error('已存在相同类型、名称和内容的记录。请检查后重试。');
    const normalized = { ...draft, ttl: draft.proxied ? 'auto' : draft.ttl };
    const nextRecord = { ...normalized, id: id || createId() };
    setRecords(previous => id ? previous.map(record => record.id === id ? nextRecord : record) : [...previous, nextRecord]);
    if (!id) { try { localStorage.removeItem('edgelab.draft'); } catch { /* Optional persistence. */ } }
    setEditor(null);
    onToast(id ? '更改已保存，演示记录已更新。' : '记录已添加，仅保存到当前浏览器。');
  }

  function deleteRecords() {
    const count = deleteIds.length;
    setRecords(previous => previous.filter(record => !deleteIds.includes(record.id)));
    setSelected(previous => previous.filter(id => !deleteIds.includes(id)));
    if (editor !== 'new' && editor && deleteIds.includes(editor.id)) setEditor(null);
    setDeleteIds([]);
    onToast(`已删除 ${count} 条本地演示记录。`);
  }

  function toggleAll() {
    setSelected(previous => allSelected ? previous.filter(id => !visibleRecords.some(record => record.id === id)) : Array.from(new Set([...previous, ...visibleRecords.map(record => record.id)])));
  }

  function changeSort(field: 'name' | 'type') {
    setSort(previous => ({ field, ascending: previous?.field === field ? !previous.ascending : true }));
  }

  function exportRecords() {
    const data = selected.length ? records.filter(record => selected.includes(record.id)) : records;
    downloadFile('example.com-dns.json', JSON.stringify({ version: 1, domain: DOMAIN, records: data }, null, 2));
    onToast(`已导出 ${data.length} 条记录为 JSON 文件。`);
  }

  const navItems = (mobile = false) => <>
    <button className="site-nav-item site-back" onClick={() => navigateSite('overview')} title="返回站点概览" aria-label="返回站点概览"><ArrowLeft size={17} /><span>返回站点概览</span></button>
    <div className="site-nav-divider" />
    {SITE_NAV.map(({ id, label, icon: Icon }) => <div key={id}>
      <button className={`site-nav-item ${section === id ? 'active' : ''}`} aria-current={section === id ? 'page' : undefined} aria-label={label} title={hover.expanded || mobile ? undefined : label} onClick={() => navigateSite(id)}><Icon size={18} /><span>{label}</span>{id === 'dns' && <ChevronDown size={14} className="site-nav-chevron" />}</button>
      {id === 'dns' && (hover.expanded || mobile) && <div className="site-subnav"><button className={section === 'dns' ? 'selected' : ''} onClick={() => navigateSite('dns')}>记录</button><button onClick={() => navigateSite('settings')}>设置</button></div>}
    </div>)}
  </>;

  return <div ref={consoleRef} className={`console-shell ${pinned ? 'site-pinned' : ''}`}>
    <header className="console-topbar">
      <div className="console-cloud"><Cloud size={25} fill="currentColor" strokeWidth={0} /></div>
      <button className="icon-button site-mobile-menu" onClick={() => setMobileNav(true)} aria-label="打开站点导航"><Menu size={18} /></button>
      <button className={`favorite-button ${favorite ? 'is-favorite' : ''}`} onClick={() => setFavorite(!favorite)} aria-label={favorite ? '取消收藏域名' : '收藏域名'} aria-pressed={favorite}><Star size={15} fill={favorite ? 'currentColor' : 'none'} /></button>
      <span className="console-domain">{DOMAIN}</span><span className="plan-label">Free</span>
      <span className="console-topbar-spacer" />
      <span className="domain-status"><span className="status-dot" />已激活</span>
      <button className="icon-button console-help" onClick={onReadGuide} aria-label="查看 DNS 设计说明"><BookOpen size={16} /></button>
    </header>
    <div className="console-body">
      <aside className={`site-sidebar ${hover.expanded ? 'expanded' : ''} ${hover.expanded && !pinned ? 'site-peeking' : ''}`} {...hover.handlers} aria-label="站点导航">
        <div className="site-nav-scroll">{navItems()}</div>
        <button className="site-nav-item site-collapse" onClick={() => { hover.reset(); setPinned(!pinned); }} data-nav-toggle aria-label={pinned ? '收起站点导航' : '固定展开站点导航'} aria-expanded={hover.expanded}>{pinned ? <PanelLeftClose size={18} /> : <PanelLeftOpen size={18} />}<span>{pinned ? '收起导航' : '固定展开'}</span></button>
      </aside>
      <section className={`console-main ${scene === 'forms' ? 'form-scene' : ''}`} aria-label="DNS 演示工作区">
        {scene === 'forms' ? <RecordForm inline onSave={saveRecord} onCancel={onShowRecords} simulateFailure={simulateFailure} /> : isTable ? <div className="dns-page">
          <div className="dns-heading"><div><h2>{section === 'email' ? '邮件 DNS 记录' : 'DNS 记录'}<span className="record-count">{section === 'email' ? records.filter(record => ['MX', 'TXT'].includes(record.type)).length : records.length}</span></h2><p>管理域名解析，让流量准确抵达。</p></div><button className="button small dns-docs-button" onClick={onReadGuide}><BookOpen size={14} />DNS 文档<ArrowUpRight size={13} /></button></div>
          {notice && <div className="dns-notice"><ShieldCheck size={17} /><p><strong>更快，也更安全。</strong><span>开启代理，获得边缘网络的加速与防护。</span></p><button className="notice-link" onClick={onReadGuide}>了解更多<ArrowUpRight size={12} /></button><button className="notice-dismiss icon-button" onClick={() => setNotice(false)} aria-label="关闭代理提示"><X size={13} /></button></div>}
          <div className="dns-toolbar">
            <div className="record-search"><Search size={15} /><input aria-label="搜索 DNS 记录" placeholder="搜索 DNS 记录..." value={query} onChange={event => setQuery(event.target.value)} />{query && <button className="icon-button" onClick={() => setQuery('')} aria-label="清除搜索"><X size={13} /></button>}</div>
            <div className="filter-wrap" ref={filterRef}>
              <button className={`button small ${rules.length ? 'filter-active' : ''}`} onClick={() => { if (!filterOpen && rules.length) setDraftRules(rules); setFilterOpen(!filterOpen); setDisplayOpen(false); }} aria-expanded={filterOpen}><Filter size={14} />筛选{rules.length > 0 && <span className="filter-count">{rules.length}</span>}<ChevronDown size={12} /></button>
              {filterOpen && <form className="popover filter-popover" onSubmit={(event: FormEvent) => { event.preventDefault(); setRules(draftRules.filter(rule => rule.value.trim()).map(rule => ({ ...rule, value: rule.value.trim() }))); closeFilters(); }} aria-label="筛选 DNS 记录">
                <div className="popover-heading"><strong>筛选记录</strong><button type="button" className="icon-button" onClick={closeFilters} aria-label="关闭筛选"><X size={16} /></button></div>
                {draftRules.map((rule, index) => <div className="filter-row" key={rule.id}>
                  <select aria-label={`筛选 ${index + 1} 字段`} value={rule.field} onChange={event => setDraftRules(previous => previous.map(item => item.id === rule.id ? { ...item, field: event.target.value as FilterRule['field'], value: event.target.value === 'type' ? 'A' : event.target.value === 'proxied' ? 'true' : '', operator: ['type', 'proxied'].includes(event.target.value) ? 'equals' : item.operator } : item))}><option value="name">名称</option><option value="type">类型</option><option value="content">内容</option><option value="proxied">代理状态</option></select>
                  <select aria-label={`筛选 ${index + 1} 条件`} value={rule.operator} onChange={event => setDraftRules(previous => previous.map(item => item.id === rule.id ? { ...item, operator: event.target.value as FilterRule['operator'] } : item))}><option value="equals">等于</option><option value="contains">包含</option></select>
                  {rule.field === 'type' ? <select aria-label={`筛选 ${index + 1} 值`} value={rule.value} onChange={event => setDraftRules(previous => previous.map(item => item.id === rule.id ? { ...item, value: event.target.value } : item))}>{RECORD_TYPES.map(type => <option key={type}>{type}</option>)}</select> : rule.field === 'proxied' ? <select aria-label={`筛选 ${index + 1} 值`} value={rule.value} onChange={event => setDraftRules(previous => previous.map(item => item.id === rule.id ? { ...item, value: event.target.value } : item))}><option value="true">已代理</option><option value="false">仅 DNS</option></select> : <input aria-label={`筛选 ${index + 1} 值`} placeholder="输入筛选内容" value={rule.value} onChange={event => setDraftRules(previous => previous.map(item => item.id === rule.id ? { ...item, value: event.target.value } : item))} />}
                  <button type="button" className="icon-button" aria-label={`移除筛选 ${index + 1}`} onClick={() => setDraftRules(previous => previous.filter(item => item.id !== rule.id))}><Trash2 size={14} /></button>
                </div>)}
                <div className="filter-footer"><button type="button" className="text-button" disabled={draftRules.length >= 4} onClick={() => setDraftRules(previous => [...previous, { id: createId(), field: 'name', operator: 'contains', value: '' }])}><Plus size={14} />添加条件</button><span>Enter 应用</span><button className="button primary small" type="submit">应用筛选</button></div>
              </form>}
            </div>
            <div className="display-wrap" ref={displayRef}>
              <button className="button small display-button" onClick={() => { setDisplayOpen(!displayOpen); setFilterOpen(false); }} aria-expanded={displayOpen} aria-label="显示设置"><SlidersHorizontal size={14} /><span>显示设置</span></button>
              {displayOpen && <div className="popover display-popover"><p className="popover-caption">表格显示</p><label className="check-option"><input type="checkbox" checked={compact} onChange={event => setCompact(event.target.checked)} />紧凑行间距</label><label className="check-option"><input type="checkbox" checked={showContent} onChange={event => setShowContent(event.target.checked)} />显示记录内容</label><label className="check-option"><input type="checkbox" checked={showTtl} onChange={event => setShowTtl(event.target.checked)} />显示 TTL</label>
                {narrow && <div className="mobile-table-controls"><label className="sort-option">排序方式<select value={sort ? `${sort.field}-${sort.ascending ? 'asc' : 'desc'}` : 'default'} onChange={event => { const [field, order] = event.target.value.split('-'); setSort(field === 'default' ? null : { field: field as 'name' | 'type', ascending: order === 'asc' }); }}><option value="default">默认顺序</option><option value="name-asc">名称：升序</option><option value="name-desc">名称：降序</option><option value="type-asc">类型：升序</option><option value="type-desc">类型：降序</option></select></label><label className="check-option"><input ref={selectAll} type="checkbox" checked={allSelected} onChange={toggleAll} disabled={!visibleRecords.length} />选择当前页全部记录</label></div>}
              </div>}
            </div>
            <div className="transfer-buttons"><button className="button small icon-only" onClick={() => setImportOpen(true)} title="导入 JSON 记录" aria-label="导入记录"><Upload size={15} /></button><button className="button small icon-only" onClick={exportRecords} title="导出 JSON 记录" aria-label="导出记录"><Download size={15} /></button></div>
            <button className="button primary small add-record-button" data-focus-fallback onClick={() => setEditor('new')}><Plus size={16} />添加记录</button>
          </div>
          {rules.length > 0 && <div className="applied-filters"><Filter size={13} /><span>已应用 {rules.length} 个筛选条件</span><button className="text-button" onClick={() => setRules([])}>清除筛选<X size={12} /></button></div>}
          <div className={`dns-table-section ${compact ? 'compact-table' : ''}`}>
            <div className="table-scroll">
              <table className="dns-table">
                <caption className="sr-only">{DOMAIN} 的 DNS 记录，共 {filteredRecords.length} 条匹配记录</caption>
                <thead><tr>
                  <th className="check-cell">{narrow ? '选择' : <label className="checkbox-hit"><input ref={selectAll} type="checkbox" aria-label="选择当前页全部记录" checked={allSelected} onChange={toggleAll} disabled={!visibleRecords.length} /></label>}</th>
                  <th className="type-cell" aria-sort={sort?.field === 'type' ? sort.ascending ? 'ascending' : 'descending' : 'none'}>{narrow ? '类型' : <button onClick={() => changeSort('type')}>类型<ArrowDownUp size={12} /></button>}</th>
                  <th className="name-cell" aria-sort={sort?.field === 'name' ? sort.ascending ? 'ascending' : 'descending' : 'none'}>{narrow ? '名称' : <button onClick={() => changeSort('name')}>名称{sort?.field === 'name' ? <ArrowDown size={12} className={!sort.ascending ? 'sort-reverse' : ''} /> : <ArrowDownUp size={12} />}</button>}</th>
                  {showContent && <th className="content-cell">内容</th>}
                  <th className="proxy-cell">代理状态<Info size={12} /></th>
                  {showTtl && <th className="ttl-cell">TTL</th>}
                  <th className="action-cell"><span className="sr-only">操作</span></th>
                </tr></thead>
                <tbody>{visibleRecords.map(record => <tr key={record.id} className={selected.includes(record.id) ? 'selected-row' : ''}>
                  <td className="check-cell"><label className="checkbox-hit"><input type="checkbox" checked={selected.includes(record.id)} onChange={event => setSelected(previous => event.target.checked ? [...previous, record.id] : previous.filter(id => id !== record.id))} aria-label={`选择 ${record.type} ${record.name}`} /></label></td>
                  <td className="type-cell" data-label="类型"><span className={`record-type type-${record.type.toLowerCase()}`}>{record.type}</span></td>
                  <td className="name-cell" data-label="名称"><span className="record-name" title={record.name === '@' ? DOMAIN : `${record.name}.${DOMAIN}`}>{record.name === '@' ? DOMAIN : record.name}</span></td>
                  {showContent && <td className="content-cell" data-label="内容"><code title={record.content}>{record.content}</code>{record.type === 'MX' && <span className="mx-priority" title="邮件服务器优先级">{record.priority}</span>}</td>}
                  <td className="proxy-cell" data-label="代理状态"><span className={record.proxied ? 'proxy-status proxied' : 'proxy-status'}><Cloud size={17} fill={record.proxied ? 'currentColor' : 'none'} strokeWidth={record.proxied ? 0 : 1.6} />{record.proxied ? '已代理' : '仅 DNS'}</span></td>
                  {showTtl && <td className="ttl-cell" data-label="TTL">{record.ttl === 'auto' ? '自动' : record.ttl === '3600' ? '1 小时' : `${Number(record.ttl) / 60} 分钟`}</td>}
                  <td className="action-cell"><button className="edit-button" onClick={() => setEditor(record)} aria-label={`编辑 ${record.type} ${record.name}`}>编辑<Ellipsis size={15} /></button></td>
                </tr>)}</tbody>
              </table>
              {!visibleRecords.length && <div className="empty-records"><SearchX size={29} /><h3>没有找到匹配记录</h3><p>试试其他关键词，或清除当前筛选。</p><button className="button small" onClick={() => { setQuery(''); setRules([]); }}>清除搜索与筛选</button></div>}
            </div>
            <div className="table-footer"><span className="table-count">{selected.length ? `已选择 ${selected.length} 条记录` : `共 ${filteredRecords.length} 条记录`}</span>{selected.length > 0 ? <div className="selection-actions"><button className="text-button" onClick={() => setSelected([])}>取消选择</button><button className="text-button danger-text" onClick={() => setDeleteIds(selected)}><Trash2 size={13} />删除所选</button></div> : <><label className="page-size-label">每页<select aria-label="每页记录数" value={pageSize} onChange={event => setPageSize(Number(event.target.value))}><option value={10}>10 条</option><option value={25}>25 条</option><option value={50}>50 条</option></select></label><div className="pagination"><button className="icon-button" aria-label="上一页" disabled={currentPage <= 1} onClick={() => setPage(currentPage - 1)}><ChevronLeft size={14} /></button><span>{currentPage}<span className="muted"> / {totalPages}</span></span><button className="icon-button" aria-label="下一页" disabled={currentPage >= totalPages} onClick={() => setPage(currentPage + 1)}><ChevronRight size={14} /></button></div></>}</div>
          </div>
        </div> : <SiteSectionContent section={section} records={records} onBack={() => navigateSite('dns')} onGuide={onReadGuide} />}
      </section>
    </div>
    <footer className="console-statusbar"><span><span className="status-dot" />本地沙盒</span><span><LockKeyhole size={11} />不连接真实 DNS 服务</span><span className="sandbox-version">EDGELAB / DEMO</span></footer>
    {mobileNav && <Modal title="站点导航" onClose={() => setMobileNav(false)} className="site-nav-dialog"><div className="mobile-site-nav">{navItems(true)}</div></Modal>}
    {editor && <Modal title={editor === 'new' ? '添加 DNS 记录' : '编辑 DNS 记录'} description={editor === 'new' ? '填写必要信息，为你的域名添加一条解析。' : `${editor.type} · ${editor.name === '@' ? DOMAIN : `${editor.name}.${DOMAIN}`}`} onClose={() => { setEditor(null); if (editor === 'new') onToast('草稿已保留，下次添加时可继续编辑。'); }} className="record-drawer"><RecordForm record={editor === 'new' ? undefined : editor} onSave={saveRecord} onCancel={() => { setEditor(null); if (editor === 'new') onToast('草稿已保留，下次添加时可继续编辑。'); }} onDelete={editor === 'new' ? undefined : () => setDeleteIds([editor.id])} /></Modal>}
    {deleteIds.length > 0 && <Modal title={`删除 ${deleteIds.length} 条 DNS 记录？`} description="此操作只影响本地演示，但删除后无法直接撤销。请确认选择的记录。" onClose={() => setDeleteIds([])} danger><div className="modal-body"><ul className="delete-record-list">{records.filter(record => deleteIds.includes(record.id)).map(record => <li key={record.id}><span className="record-type">{record.type}</span><span>{record.name === '@' ? DOMAIN : record.name}</span><code>{record.content}</code></li>)}</ul><p className="muted">需要时可通过页面顶部的“重置演示”恢复初始数据。</p></div><div className="modal-actions"><button className="button" data-autofocus onClick={() => setDeleteIds([])}>保留记录</button><button className="button danger" onClick={deleteRecords}>确认删除</button></div></Modal>}
    {importOpen && <ImportRecords onClose={() => setImportOpen(false)} existingRecords={records} onImport={next => { setRecords(previous => [...previous, ...next]); setImportOpen(false); onToast(`成功导入 ${next.length} 条演示记录。`); }} />}
  </div>;
}

function SiteSectionContent({ section, records, onBack, onGuide }: { section: SiteSection; records: DnsRecord[]; onBack: () => void; onGuide: () => void }) {
  const [dnssec, setDnssec] = useStoredState('edgelab.dnssec', false);
  const [development, setDevelopment] = useStoredState('edgelab.development', false);
  const label = SITE_NAV.find(item => item.id === section)?.label;
  return <section className="site-section-content"><span className="eyebrow">站点导航示例</span><h2>{label}</h2><p className="muted">导航保留域名上下文，内容区域随任务切换。</p>
    {section === 'overview' && <><div className="domain-overview"><Globe size={30} /><div><h3>{DOMAIN}</h3><p><span className="status-dot" />本地示例站点 · {records.length} 条记录</p></div></div><p>这是保留用于文档的示例域名。实验室的完整交互集中于 DNS 记录管理，不会产生网络配置变更。</p></>}
    {section === 'analytics' && <div className="record-distribution"><h3>记录类型分布</h3><p className="field-help">根据当前本地数据计算，不是实时流量统计。</p>{RECORD_TYPES.map(type => { const count = records.filter(record => record.type === type).length; return <div className="distribution-row" key={type}><span>{type}</span><div className="distribution-track"><div style={{ width: `${records.length ? count / records.length * 100 : 0}%` }} /></div><span>{count} 条</span></div>; })}</div>}
    {(section === 'security' || section === 'settings') && <div className="demo-setting-row"><div><h3>DNSSEC 演示开关</h3><p>展示带说明的开关模式，不执行真实域名签名。</p></div><button className={`switch ${dnssec ? 'on' : ''}`} role="switch" aria-checked={dnssec} aria-label="DNSSEC 演示开关" onClick={() => setDnssec(!dnssec)}><span /></button></div>}
    {section === 'performance' && <div className="demo-setting-row"><div><h3>开发模式演示</h3><p>偏好会在当前浏览器保留，不影响真实缓存。</p></div><button className={`switch ${development ? 'on' : ''}`} role="switch" aria-checked={development} aria-label="开发模式演示" onClick={() => setDevelopment(!development)}><span /></button></div>}
    <div className="section-page-actions"><button className="button primary" onClick={onBack}><Network size={15} />前往 DNS 记录</button><button className="text-button" onClick={onGuide}>理解这个设计<ArrowUpRight size={14} /></button></div>
  </section>;
}

function ImportRecords({ onClose, existingRecords, onImport }: { onClose: () => void; existingRecords: DnsRecord[]; onImport: (records: DnsRecord[]) => void }) {
  const [text, setText] = useState('');
  const [error, setError] = useState('');
  const errorRef = useRef<HTMLDivElement>(null);
  const [reading, setReading] = useState(false);
  const alive = useRef(true);
  const readVersion = useRef(0);
  useEffect(() => { alive.current = true; return () => { alive.current = false; }; }, []);
  async function loadFile(file?: File) {
    if (!file) return;
    const version = ++readVersion.current;
    if (file.size > 1024 * 1024) { setError('文件不能超过 1 MB。'); setReading(false); return; }
    setReading(true);
    try { const content = await file.text(); if (alive.current && version === readVersion.current) { setText(content); setError(''); } }
    catch { if (alive.current && version === readVersion.current) setError('文件读取失败，请重新选择。'); }
    finally { if (alive.current && version === readVersion.current) setReading(false); }
  }
  function submit(event: FormEvent) {
    event.preventDefault();
    if (reading) return;
    try {
      if (new Blob([text]).size > 1024 * 1024) throw new Error('JSON 内容不能超过 1 MB。');
      const parsed: unknown = JSON.parse(text);
      if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
        const envelope = parsed as { domain?: unknown; version?: unknown };
        if (envelope.domain !== undefined && envelope.domain !== DOMAIN) throw new Error(`此演示仅接受 ${DOMAIN} 的记录，请确认文件中的域名。`);
        if (envelope.version !== undefined && envelope.version !== 1) throw new Error('暂不支持此文件版本，请使用 version: 1 的导出格式。');
      }
      const data: unknown = Array.isArray(parsed) ? parsed : parsed && typeof parsed === 'object' ? (parsed as { records?: unknown }).records : null;
      if (!Array.isArray(data) || !data.length) throw new Error('请提供非空记录数组，或含 records 数组的导出文件。');
      if (data.length + existingRecords.length > 200) throw new Error('导入后最多允许 200 条演示记录。');
      const next = data.map((item: unknown, index) => {
        if (!item || typeof item !== 'object') throw new Error(`第 ${index + 1} 条记录不是有效对象。`);
        const raw = item as Partial<DnsRecord>;
        if (!RECORD_TYPES.includes(raw.type as RecordType) || typeof raw.name !== 'string' || typeof raw.content !== 'string') throw new Error(`第 ${index + 1} 条记录需要有效的 type、name 和 content。`);
        const draft: RecordDraft = { ...EMPTY_RECORD, type: raw.type as RecordType, name: raw.name.trim(), content: raw.content.trim(), proxied: raw.proxied === true && supportsProxy(raw.type as RecordType), ttl: typeof raw.ttl === 'string' ? raw.ttl : 'auto', priority: typeof raw.priority === 'string' ? raw.priority : '10', comment: typeof raw.comment === 'string' ? raw.comment : '' };
        if (draft.proxied) draft.ttl = 'auto';
        const errors = validateRecord(draft);
        if (Object.keys(errors).length) throw new Error(`第 ${index + 1} 条记录：${Object.values(errors)[0]}`);
        return { ...draft, id: createId() };
      });
      const keys = new Set(existingRecords.map(recordKey));
      for (const record of next) {
        if (keys.has(recordKey(record))) throw new Error(`记录 ${record.type} ${record.name} 已存在或在文件内重复。请移除重复项后重试，当前没有导入任何记录。`);
        keys.add(recordKey(record));
      }
      onImport(next);
    } catch (caught) {
      setError(caught instanceof SyntaxError ? 'JSON 格式不正确，请检查引号、逗号和方括号。' : caught instanceof Error ? caught.message : '导入失败，请检查数据。');
      requestAnimationFrame(() => errorRef.current?.focus());
    }
  }
  return <Modal title="导入 DNS 记录" description="支持本实验室导出的 JSON。导入前会校验每条记录，有错误时不会写入任何数据。" onClose={onClose} className="import-dialog"><form onSubmit={submit} noValidate><div className="modal-body">{error && <div className="form-server-error" role="alert" tabIndex={-1} ref={errorRef}><Info size={17} />{error}</div>}<label className="file-input-label">选择 JSON 文件<input type="file" accept=".json,application/json" onChange={event => loadFile(event.target.files?.[0])} /></label><label className="textarea-label" htmlFor="import-json">或粘贴 JSON 内容</label><textarea id="import-json" className="import-textarea" data-autofocus rows={9} value={text} onChange={event => { setText(event.target.value); setError(''); }} placeholder={'[\n  { "type": "A", "name": "dev",\n    "content": "192.0.2.10" }\n]'} /><div className="import-note"><span className="field-help">上限 1 MB / 200 条记录。</span><button type="button" className="text-button" onClick={() => setText(JSON.stringify([{ type: 'A', name: 'dev', content: '192.0.2.10', proxied: false, ttl: 'auto' }], null, 2))}>填入示例</button></div></div><div className="modal-actions"><button type="button" className="button" onClick={onClose}>取消</button><button type="submit" className="button primary" disabled={reading}><Upload size={15} />{reading ? '读取中...' : '校验并导入'}</button></div></form></Modal>;
}