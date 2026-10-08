import { useEffect, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { ArrowDownToLine, ArrowLeft, ArrowRight, ArrowUpRight, BookOpen, Check, CheckCircle2, ChevronRight, Copy, FileText, Info, LoaderCircle, Network, PanelLeft, SlidersHorizontal } from 'lucide-react';
import { downloadFile, type Page } from '../lib/data';
import { useStoredState } from '../lib/hooks';

export const DOCUMENTS = [
  { id: '00-design-plan', number: '00', title: '设计规划与线框', description: '定位、信息架构、页面线框与视觉决策。', category: '设计基础' },
  { id: '01-design-guidelines', number: '01', title: '界面设计规范', description: '必须、推荐、可以与禁止：把原则变成规则。', category: '设计基础' },
  { id: '02-interaction-spec', number: '02', title: '交互与状态说明', description: '导航状态机、表单校验、筛选与风险操作。', category: '实现参考' },
  { id: '03-development', number: '03', title: '开发与部署指南', description: '本地运行、文件结构、静态部署和生产化边界。', category: '实现参考' },
  { id: '04-acceptance', number: '04', title: '验收与测试清单', description: '多宽度、主题、键盘、数据与极端情况。', category: '交付验收' },
  { id: '05-reference', number: '05', title: '参考来源与适用边界', description: 'Cloudflare 官方资料与本案例的独立设计决策。', category: '交付验收' },
];
const documentCache = new Map<string, string>();

export function DocumentReader({ documentId, onBack }: { documentId: string; onBack?: () => void }) {
  const [content, setContent] = useState(documentCache.get(documentId) || '');
  const [loading, setLoading] = useState(!documentCache.has(documentId));
  const [error, setError] = useState('');
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    setError('');
    if (documentCache.has(documentId)) { setContent(documentCache.get(documentId)!); setLoading(false); return; }
    setLoading(true);
    fetch(`./docs/${documentId}.md`, { signal: controller.signal }).then(response => {
      if (!response.ok) throw new Error('暂时无法加载文档，请稍后重试。');
      return response.text();
    }).then(text => {
      if (controller.signal.aborted) return;
      documentCache.set(documentId, text);
      setContent(text);
      setLoading(false);
    }).catch(caught => { if (!controller.signal.aborted) { setError(caught instanceof Error ? caught.message : '文档加载失败。'); setLoading(false); } });
    return () => controller.abort();
  }, [documentId, attempt]);

  return <div className="document-reader">
    <div className="reader-toolbar">{onBack ? <button className="text-button" onClick={onBack}><ArrowLeft size={15} />文档地图</button> : <span className="eyebrow">IMPLEMENTATION GUIDE</span>}<a className="button small" href={`./docs/${documentId}.md`} download><ArrowDownToLine size={14} />下载 Markdown</a></div>
    {loading ? <div className="document-loading" role="status"><LoaderCircle size={22} className="spin" />正在加载文档...</div> : error ? <div className="document-loading" role="alert"><Info size={22} /><p>{error}</p><button className="button" onClick={() => setAttempt(attempt + 1)}>重新加载</button></div> : <article className="markdown-content"><ReactMarkdown remarkPlugins={[remarkGfm]} components={{ h1: ({ children }) => <h2>{children}</h2>, h2: ({ children }) => <h3>{children}</h3>, h3: ({ children }) => <h4>{children}</h4>, table: ({ children }) => <div className="document-table-wrap"><table>{children}</table></div>, a: ({ href, children }) => <a href={href} target={href?.startsWith('https://') ? '_blank' : undefined} rel="noreferrer">{children}</a> }}>{content}</ReactMarkdown></article>}
  </div>;
}

export function Documentation({ onToast }: { onToast: (message: string, tone?: 'success' | 'info' | 'error') => void }) {
  const [selected, setSelected] = useState<string | null>(null);
  const [downloading, setDownloading] = useState(false);
  async function downloadAll() {
    setDownloading(true);
    try {
      const texts = await Promise.all(DOCUMENTS.map(async document => {
        const response = await fetch(`./docs/${document.id}.md`);
        if (!response.ok) throw new Error('有文档未能加载，请稍后重试。');
        return response.text();
      }));
      downloadFile('EdgeLab-完整设计指南.md', texts.join('\n\n---\n\n'), 'text/markdown;charset=utf-8');
      onToast('完整指南已下载，包含 6 份设计与交付文档。');
    } catch (error) { onToast(error instanceof Error ? error.message : '下载失败，请重试。', 'error'); }
    finally { setDownloading(false); }
  }
  if (selected) return <DocumentReader documentId={selected} onBack={() => setSelected(null)} />;
  return <div className="documentation-page page-enter"><div className="section-heading"><div><span className="eyebrow">DOCUMENTATION</span><h2>一张地图，完整交付。</h2><p>从上到下阅读，或直接跳到你需要的部分。</p></div><button className="button" disabled={downloading} onClick={downloadAll}>{downloading ? <LoaderCircle className="spin" size={15} /> : <ArrowDownToLine size={15} />}{downloading ? '正在整理...' : '下载完整指南'}</button></div><div className="document-list">{DOCUMENTS.map(document => <div className="document-row" key={document.id}><span className="document-number">{document.number}</span><FileText size={22} /><button className="document-open" onClick={() => setSelected(document.id)}><strong>{document.title}</strong><span>{document.description}</span></button><span className="document-category">{document.category}</span><a className="icon-button" href={`./docs/${document.id}.md`} download aria-label={`下载${document.title}`}><ArrowDownToLine size={16} /></a><button className="icon-button" onClick={() => setSelected(document.id)} aria-label={`阅读${document.title}`}><ChevronRight size={17} /></button></div>)}</div><div className="docs-bottom-note"><Info size={17} /><p>文档与代码一同交付。涉及动画参数与布局尺寸的说明，均为本实验室的实践建议，并非 Cloudflare 官方规范。</p></div></div>;
}

const CHECKLIST = [
  '300px 宽度下，仍可以完成添加与修改记录',
  '不使用鼠标，也能展开导航和关闭浮层',
  '表单错误与字段关联，提交后定位首个错误',
  '深色、浅色与系统模式均有清晰的焦点样式',
  '失败不会清空输入，删除始终需要二次确认',
];

export function DesignGuide({ onNavigate }: { onNavigate: (page: Page) => void }) {
  const [checks, setChecks] = useStoredState<string[]>('edgelab.checklist', [], value => Array.isArray(value) && value.every(item => typeof item === 'string'));
  return <div className="guide-layout page-enter"><article className="guide-article">
    <div className="guide-intro"><span className="eyebrow">DESIGN PRINCIPLES</span><h2>借鉴设计逻辑，<br />而不只是复制像素。</h2><p>成熟的控制台不依赖复杂的装饰。它通过可预测的布局、清晰的反馈和稳定的交互，帮助用户有把握地完成任务。</p></div>
    <section id="guide-navigation" className="guide-section"><div className="guide-section-title"><span>01</span><h3>把空间留给内容，把导航交给意图。</h3></div><p>固定展开用于探索，图标栏用于专注。悬停预览必须是覆盖层，只有主动固定才改变内容宽度。</p><div className="nav-state-diagram" aria-label="导航状态示意"><div><div className="mini-shell"><span className="mini-rail narrow" /><span className="mini-content" /></div><strong>收起</strong><small>64px 工作台 / 56px 站点</small></div><ArrowRight size={16} /><div><div className="mini-shell"><span className="mini-rail overlay" /><span className="mini-content" /></div><strong>悬停预览</strong><small>120ms 延时 · 不挤动内容</small></div><ArrowRight size={16} /><div><div className="mini-shell"><span className="mini-rail wide" /><span className="mini-content" /></div><strong>固定展开</strong><small>224px · 主动改变布局</small></div></div><Rule level="MUST" title="必须">键盘聚焦与点击都能访问同样的导航；移出鼠标不能隐藏仍持有键盘焦点的菜单。</Rule><Rule level="SHOULD" title="推荐">进入延时 120ms、离开延时 240ms。快速跨过侧栏时不要闪烁，清理所有计时器。</Rule><button className="text-button" onClick={() => onNavigate('navigation')}>体验导航状态<ArrowRight size={14} /></button></section>
    <section id="guide-forms" className="guide-section"><div className="guide-section-title"><span>02</span><h3>错误是需要解释的状态，不是死路。</h3></div><p>先告诉用户要填什么，再解释为什么。字段失焦时轻量检查，提交时完整校验，保留用户已经完成的工作。</p><Rule level="MUST" title="必须">使用可见标签、持久辅助说明、字段级错误与提交级摘要。提交失败后聚焦第一个错误字段。</Rule><Rule level="SHOULD" title="推荐">超过 7 项的表单应分组或分步。保存失败保留内容，异步保存期间防止重复提交。</Rule><Rule level="NEVER" title="避免">不以禁用提交按钮代替校验；不禁止粘贴；不把 placeholder 当作唯一标签；不使用 alert。</Rule><button className="text-button" onClick={() => onNavigate('forms')}>体验输入与校验<ArrowRight size={14} /></button></section>
    <section id="guide-responsive" className="guide-section"><div className="guide-section-title"><span>03</span><h3>响应式不是缩小，而是重新安排。</h3></div><p>根据内容可用空间，而非设备名称决定布局。工作台使用媒体查询，嵌套预览使用容器查询，两者独立响应。</p><div className="breakpoint-table"><div><strong>宽屏</strong><code>&gt; 1000px</code><span>工作台侧栏固定，列表信息横向对齐。</span></div><div><strong>中屏</strong><code>641 - 1000px</code><span>工作台改用抽屉，操作栏按需换行。</span></div><div><strong>窄屏</strong><code>≤ 640px</code><span>站点导航抽屉化，记录按字段重新排版。</span></div></div><Rule level="MUST" title="必须">在 390 / 768 / 1440px 验收，并补测 320 / 300px。不能依赖缩放或隐藏溢出来伪造适配。</Rule><Rule level="MAY" title="可以">在宽度模拟器中自动往返播放；尊重减少动态效果偏好，并在后台页面暂停更新。</Rule></section>
    <section id="guide-accessibility" className="guide-section"><div className="guide-section-title"><span>04</span><h3>可访问，是质量底线。</h3></div><p>无障碍不应是最后增加的模式，而应是每个组件的默认行为。</p><Rule level="MUST" title="必须">普通文本对比度目标至少 4.5:1；焦点始终可见；触屏操作目标至少 44px；正文行高至少 1.6。</Rule><Rule level="SHOULD" title="推荐">优先使用原生按钮、表单、表格和 dialog。浮层支持 Escape，关闭后把焦点交还触发器。</Rule><Rule level="NEVER" title="避免">不使用 div onClick 假按钮，不移除焦点样式，不用颜色作为唯一状态提示，不提供仅 hover 可用的功能。</Rule></section>
    <section id="guide-checklist" className="guide-section"><div className="guide-section-title"><span>05</span><h3>把规范变成可检查的结果。</h3></div><p>下面是个人验收笔记，不是自动化测试报告。勾选项会保留在当前浏览器。</p><div className="interactive-checklist">{CHECKLIST.map(item => <label key={item}><input type="checkbox" checked={checks.includes(item)} onChange={event => setChecks(previous => event.target.checked ? [...previous, item] : previous.filter(value => value !== item))} /><span>{item}</span></label>)}</div><div className="checklist-summary"><CheckCircle2 size={15} /><span>已检查 {checks.length} / {CHECKLIST.length} 项</span><button className="text-button" onClick={() => setChecks([])}>清空记录</button></div></section>
    <section className="source-note"><BookOpen size={17} /><div><strong>设计有出处，决策有边界。</strong><p>参考 Cloudflare 官方无障碍和深色模式实践。本实验室不声称通过 WCAG 认证。</p><a href="https://blog.cloudflare.com/project-a11y/" target="_blank" rel="noreferrer">阅读官方无障碍实践<ArrowUpRight size={13} /></a></div></section>
  </article><aside className="guide-outline"><span>本页内容</span><a href="#guide-navigation">导航与空间</a><a href="#guide-forms">表单与反馈</a><a href="#guide-responsive">响应式布局</a><a href="#guide-accessibility">无障碍底线</a><a href="#guide-checklist">验收清单</a><div className="outline-footnote">少一点打扰。<br />多一点确定。</div></aside></div>;
}

function Rule({ level, title, children }: { level: 'MUST' | 'SHOULD' | 'MAY' | 'NEVER'; title: string; children: React.ReactNode }) {
  return <div className={`design-rule rule-${level.toLowerCase()}`}><span className="rule-level">{title}<small>{level}</small></span><p>{children}</p></div>;
}

export function Overview({ onNavigate }: { onNavigate: (page: Page) => void }) {
  const journeys = [
    { number: '01', icon: PanelLeft, title: '让导航自然进退', description: '固定、收起与悬停预览，在空间和效率之间找到平衡。', page: 'navigation' as const },
    { number: '02', icon: Network, title: '在真实任务里体验', description: '用一套完整的 DNS 管理流程，串起搜索、筛选与编辑。', page: 'dns' as const },
    { number: '03', icon: SlidersHorizontal, title: '给每次输入以回应', description: '分组清晰的表单、两级校验，以及可靠的恢复路径。', page: 'forms' as const },
  ];
  return <div className="overview-page page-enter"><div className="overview-lead"><span className="eyebrow">A SMALL LAB FOR BETTER INTERFACES</span><h2>好的设计，<br />可以被理解，也可以被实践。</h2><p>EdgeLab 把 Cloudflare 控制台中值得借鉴的交互，转化为可调节、可操作、可阅读的设计参考。不是一张静态截图，而是一套可以亲手验证的体验。</p><button className="button primary" onClick={() => onNavigate('dns')}>开始体验综合案例<ArrowRight size={15} /></button></div><div className="learning-journey">{journeys.map(({ number, icon: Icon, title, description, page }) => <button className="journey-row" key={number} onClick={() => onNavigate(page)}><span>{number}</span><Icon size={24} /><div><h3>{title}</h3><p>{description}</p></div><ArrowUpRight size={20} /></button>)}</div><div className="overview-boundary"><Info size={17} /><p>独立设计研究项目。所有交互在浏览器内运行，不需要账户，不连接真实 DNS 服务。</p></div></div>;
}

export function DesignDetails({ onNavigate }: { onNavigate: (page: Page) => void }) {
  return <section className="design-details"><div className="details-title"><span className="eyebrow">THOUGHTFUL BY DESIGN</span><h2>细节有章法，体验更自然。</h2></div><div className="detail-columns">{[
    { number: '01', title: '导航，懂得适时退让', text: '悬停展开不挤动内容，离开后自然收起。专注与探索，随心切换。', page: 'navigation' as const, label: '探索导航设计' },
    { number: '02', title: '表单，始终给予回应', text: '清晰分组、即时校验、保留草稿。出错不必重来，每一步都有把握。', page: 'forms' as const, label: '体验表单交互' },
    { number: '03', title: '布局，适应每一块屏幕', text: '不是等比缩小，而是重新组织。从宽屏到极窄窗口，任务始终清晰。', page: 'responsive' as const, label: '检查响应式布局' },
  ].map(item => <article key={item.number}><span className="detail-number">{item.number}</span><h3>{item.title}</h3><p>{item.text}</p><button className="text-button" onClick={() => onNavigate(item.page)}>{item.label}<ArrowRight size={13} /></button></article>)}</div></section>;
}

export function DesignTokens({ onToast }: { onToast: (message: string, tone?: 'success' | 'info' | 'error') => void }) {
  const [tab, setTab] = useState<'colors' | 'type' | 'space'>('colors');
  const [copied, setCopied] = useState('');
  const colors = [
    { name: '品牌强调', token: '--brand', value: '#F07832', className: 'brand-swatch' },
    { name: '主要操作', token: '--action', value: '#2563EB', className: 'action-swatch' },
    { name: '主要文字', token: '--text', value: '#25262B', className: 'text-swatch' },
    { name: '辅助文字', token: '--muted', value: '#6C707A', className: 'muted-swatch' },
    { name: '成功状态', token: '--success', value: '#16794B', className: 'success-swatch' },
    { name: '危险操作', token: '--danger', value: '#BC3441', className: 'danger-swatch' },
  ];
  async function copy(value: string) {
    try { await navigator.clipboard.writeText(value); setCopied(value); onToast(`已复制 ${value}`); }
    catch { onToast(`浏览器不允许自动复制，请手动选择：${value}`, 'info'); }
  }
  return <div className="tokens-page page-enter"><div className="token-tabs" role="group" aria-label="设计令牌分类">{([['colors', '语义颜色'], ['type', '字体层级'], ['space', '间距与动效']] as const).map(([key, label]) => <button className={tab === key ? 'active' : ''} aria-pressed={tab === key} key={key} onClick={() => setTab(key)}>{label}</button>)}</div>
    {tab === 'colors' && <section><div className="section-heading"><div><h2>使用语义，而不是颜色名称。</h2><p>点击复制 CSS 变量。浅色与深色主题共享语义，分别调整色值。</p></div></div><div className="color-token-grid">{colors.map(color => <button className="color-token" key={color.token} onClick={() => copy(`var(${color.token})`)}><span className={`color-swatch ${color.className}`} /><span className="token-info"><strong>{color.name}</strong>{copied === `var(${color.token})` ? <Check size={15} /> : <Copy size={14} />}</span><code>{color.token}</code><small>浅色基准 {color.value}</small></button>)}</div><div className="docs-bottom-note"><Info size={17} /><p>品牌橙用于图形与强调。小字号的橙色文字采用更深的语义色，以提升对比度。危险与成功状态同时搭配文字，不只依靠颜色。</p></div></section>}
    {tab === 'type' && <section><div className="section-heading"><div><h2>七档字号，让层级更清晰。</h2><p>中文采用系统无衬线，技术数据使用等宽字体。正文行高不低于 1.6。</p></div></div><div className="type-token-list">{[{ size: 32, name: '展示标题' }, { size: 28, name: '页面标题' }, { size: 22, name: '区块标题' }, { size: 18, name: '小节标题' }, { size: 14, name: '正文内容' }, { size: 13, name: '操作与列表' }, { size: 12, name: '辅助说明' }].map(token => <div key={token.size}><code>{token.size}px</code><span>{token.name}</span><strong style={{ fontSize: token.size }}>让信息一目了然</strong></div>)}</div></section>}
    {tab === 'space' && <section><div className="section-heading"><div><h2>克制的尺度，可预测的节奏。</h2><p>间距只使用 4 / 8 / 12 / 16 / 24 / 32 / 48，避免一次性的魔法数值。</p></div></div><div className="spacing-token-list">{[4, 8, 12, 16, 24, 32, 48].map(value => <div key={value}><code>{value}px</code><span style={{ width: value * 5 }} /><small>space-{value}</small></div>)}</div><div className="motion-token-list"><div><strong>圆角</strong><code>4 / 6 / 8 / 12px</code><span>控件、按钮、交互容器、弹窗</span></div><div><strong>阴影</strong><code>subtle / popover / modal</code><span>只表达真实的层级关系</span></div><div><strong>动画</strong><code>160 / 220 / 320ms</code><span>反馈、导航与页面进入</span></div><div><strong>曲线</strong><code>cubic-bezier(.22, 1, .36, 1)</code><span>减少动态效果时取消位移动画</span></div></div></section>}
  </div>;
}