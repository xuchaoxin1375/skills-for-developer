import { useEffect, useRef, useState } from 'react';
import { ArrowRight, Expand, Info, Monitor, MousePointer2, Pause, Play, Smartphone, Tablet } from 'lucide-react';
import { useMediaQuery } from '../lib/hooks';
import type { Page } from '../lib/data';
import { DnsConsole } from './DnsConsole';

interface WorkbenchProps {
  page: Page;
  onReadGuide: () => void;
  onNavigate: (page: Page) => void;
  onToast: (message: string) => void;
}

export function Workbench({ page, onReadGuide, onNavigate, onToast }: WorkbenchProps) {
  const stage = useRef<HTMLDivElement>(null);
  const [availableWidth, setAvailableWidth] = useState(1100);
  const [targetWidth, setTargetWidth] = useState<number | null>(null);
  const [preset, setPreset] = useState('desktop');
  const [playing, setPlaying] = useState(false);
  const [hoverEnabled, setHoverEnabled] = useState(true);
  const [hoverDelay, setHoverDelay] = useState(120);
  const [simulateFailure, setSimulateFailure] = useState(false);
  const reducedMotion = useMediaQuery('(prefers-reduced-motion: reduce)');
  const direction = useRef(-1);
  const actualWidth = Math.round(Math.min(targetWidth ?? availableWidth, availableWidth));
  const minimumWidth = Math.min(300, availableWidth);

  useEffect(() => { if (availableWidth <= 300) setPlaying(false); }, [availableWidth]);

  useEffect(() => {
    const node = stage.current;
    if (!node) return;
    const observer = new ResizeObserver(entries => {
      const width = Math.floor(entries[0].contentRect.width);
      if (width > 0) setAvailableWidth(width);
    });
    observer.observe(node);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    if (!playing) return;
    const max = availableWidth;
    const min = Math.min(300, max);
    let value = Math.min(targetWidth ?? max, max);
    let tick = 0;
    const timer = window.setInterval(() => {
      if (document.hidden) return;
      if (reducedMotion) {
        const sizes = [max, Math.min(768, max), Math.min(390, max), min];
        value = sizes[++tick % sizes.length];
      } else {
        value += direction.current * 12;
        if (value <= min) { value = min; direction.current = 1; }
        if (value >= max) { value = max; direction.current = -1; }
      }
      setTargetWidth(value);
      setPreset('custom');
    }, reducedMotion ? 1800 : 80);
    return () => window.clearInterval(timer);
    // Target width is animation output, so changing it must not restart the clock.
  }, [playing, availableWidth, reducedMotion]);

  function choosePreset(name: string, width: number | null) {
    setPlaying(false);
    setPreset(name);
    setTargetWidth(width);
  }

  return <section className="workbench" aria-label="可交互的响应式设计预览">
    {page === 'navigation' && <div className="lab-option-row"><label className="inline-switch-label"><button className={`switch small-switch ${hoverEnabled ? 'on' : ''}`} role="switch" aria-checked={hoverEnabled} aria-label="悬停自动展开" onClick={() => setHoverEnabled(!hoverEnabled)}><span /></button>悬停自动展开</label><label className="delay-control">展开延时<select value={hoverDelay} onChange={event => setHoverDelay(Number(event.target.value))}><option value={120}>120 ms</option><option value={250}>250 ms</option><option value={400}>400 ms</option></select></label><span className="option-description">键盘聚焦始终可以展开导航</span></div>}
    {page === 'forms' && <div className="lab-option-row"><label className="inline-switch-label"><button className={`switch small-switch ${simulateFailure ? 'on' : ''}`} role="switch" aria-checked={simulateFailure} aria-label="模拟保存失败" onClick={() => setSimulateFailure(!simulateFailure)}><span /></button>模拟保存失败</label><span className="option-description">试试留空提交，或输入不正确的 IP 地址。</span></div>}
    <div className="preview-toolbar">
      <div className="device-controls" role="group" aria-label="设备宽度预设"><button className={preset === 'desktop' ? 'active' : ''} onClick={() => choosePreset('desktop', null)} aria-pressed={preset === 'desktop'} title="桌面：使用全部可用画布"><Monitor size={16} /><span>桌面</span></button><button className={preset === 'tablet' ? 'active' : ''} onClick={() => choosePreset('tablet', 768)} aria-pressed={preset === 'tablet'} title="平板：768px，受可用画布上限约束"><Tablet size={16} /><span>平板</span></button><button className={preset === 'mobile' ? 'active' : ''} onClick={() => choosePreset('mobile', 390)} aria-pressed={preset === 'mobile'} title="手机：390px，受可用画布上限约束"><Smartphone size={15} /><span>手机</span></button></div>
      <span className="toolbar-divider" />
      <div className="width-control"><label htmlFor="preview-width">预览宽度</label><input id="preview-width" type="range" min={minimumWidth} max={Math.max(minimumWidth, availableWidth)} value={Math.max(minimumWidth, actualWidth)} onChange={event => { setPlaying(false); setPreset('custom'); setTargetWidth(Number(event.target.value)); }} aria-valuetext={`${actualWidth} 像素`} /><output htmlFor="preview-width"><strong>{actualWidth}</strong><span>px</span></output></div>
      <div className="preview-toolbar-actions"><button className={`button playback-button ${playing ? 'playing' : ''}`} onClick={() => setPlaying(!playing)} aria-label={playing ? '暂停演示' : '自动演示'} aria-pressed={playing} disabled={availableWidth <= 300}>{playing ? <Pause size={14} /> : <Play size={14} />}<span>{playing ? '暂停演示' : '自动演示'}</span></button><a className="icon-button standalone-link" href="?preview=1" target="_blank" rel="noreferrer" title="在独立窗口打开，可按真实视口测试 1440px" aria-label="在新窗口打开独立预览"><Expand size={16} /></a></div>
    </div>
    <div className={`preview-stage ${actualWidth < availableWidth - 8 ? 'constrained' : ''} ${playing ? 'is-playing' : ''}`} ref={stage} onFocusCapture={() => setPlaying(false)} onPointerDownCapture={() => setPlaying(false)}>
      <div className="preview-frame" style={{ width: targetWidth === null ? '100%' : `${actualWidth}px` }}>
        <DnsConsole key={page === 'forms' ? 'form-preview' : 'dns-preview'} scene={page === 'forms' ? 'forms' : 'dns'} hoverEnabled={hoverEnabled} hoverDelay={hoverDelay} simulateFailure={simulateFailure} onReadGuide={onReadGuide} onShowRecords={() => onNavigate('dns')} onToast={onToast} />
      </div>
    </div>
    <div className="preview-caption"><span><MousePointer2 size={14} /><span>{page === 'forms' ? '字段失焦时校验，提交时再次检查。输入始终为你保留。' : '试试悬停左侧图标栏，体验不打断工作的自动展开。'}</span></span><button className="text-button" onClick={onReadGuide}>查看交互逻辑<ArrowRight size={14} /></button></div>
    {page === 'responsive' && <div className="responsive-explainer"><Info size={16} /><p>这里改变的是真实容器宽度，不是缩放截图。桌面预设使用当前全部可用空间；更大视口请打开独立预览。<button className="text-button" onClick={() => choosePreset('custom', 300)}>试试 300px 极窄布局<ArrowRight size={13} /></button></p></div>}
  </section>;
}