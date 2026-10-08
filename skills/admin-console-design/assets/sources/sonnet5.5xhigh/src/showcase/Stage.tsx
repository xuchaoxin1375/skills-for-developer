import { useCallback, useEffect, useRef, useState } from "react";
import { ChevronDown, ChevronUp, ExternalLink, Hand, PanelLeft, Pause, Play } from "lucide-react";
import { postToFrame, type FromFrame, type FrameState, type ToFrame } from "@/lib/bridge";
import { useElementSize, useMediaQuery } from "@/lib/hooks";
import { Link } from "@/lib/route";
import { useTheme } from "@/lib/theme";
import { Select, Switch } from "@/ui/controls";
import { cn } from "@/utils/cn";
import { Panel } from "./Panel";
import { SCENARIOS } from "./scenarios";

const MIN_W = 240;
const MAX_W = 1920;
const SWEEP_MIN = 280;
const SWEEP_MAX = 1600;
const PRESETS = [
  { w: 300, t: "极窄" },
  { w: 390, t: "手机" },
  { w: 768, t: "平板" },
  { w: 1024, t: "笔记本" },
  { w: 1440, t: "桌面" },
  { w: 1920, t: "宽屏" },
];
const TOUR = [
  { action: "pin-expanded", text: "① 固定展开：侧边栏常驻 240px，内容区让出空间" },
  { action: "pin-collapsed", text: "② 折叠：缩成 56px 图标栏，内容区变宽" },
  { action: "peek-on", text: "③ 悬停意图（120ms）→ 覆盖式展开，内容区不抖动" },
  { action: "peek-off", text: "④ 移开 250ms 后自动收起，无需任何点击" },
] as const;

type Mode = "improved" | "legacy" | "compare";
const clamp = (n: number, a: number, b: number) => Math.min(b, Math.max(a, n));
const buildSrc = (variant: string, to: string, theme: string) => `${window.location.href.split("#")[0]}#${to}?embed=1&variant=${variant}&theme=${theme}`;

function layoutName(l?: string) {
  return l === "wide" ? "宽屏（≥1024）" : l === "medium" ? "中等（768–1023）" : l === "narrow" ? "窄屏（<768）" : "—";
}
function sidebarName(s: FrameState | null) {
  if (!s) return "—";
  if (s.layout === "narrow") return s.drawer ? "抽屉已打开" : "抽屉（收起，由汉堡按钮打开）";
  if (s.layout === "medium") return s.expanded ? "图标栏 + 展开浮层" : "图标栏";
  if (s.pinned === "expanded") return "固定展开";
  return s.peek ? "折叠 · 悬停展开中" : "折叠（图标栏）";
}

function FrameBox({
  variant,
  badge,
  width,
  height,
  scale,
  initialTo,
  theme,
  register,
}: {
  variant: "cf" | "legacy";
  badge?: string;
  width: number;
  height: number;
  scale: number;
  initialTo: string;
  theme: string;
  register: (v: string, el: HTMLIFrameElement | null) => void;
}) {
  const [src] = useState(() => buildSrc(variant, initialTo, theme));
  const title = variant === "cf" ? "改进方案" : "传统方案";
  return (
    <div className="relative m-0 flex-none overflow-hidden rounded-lg border border-line-strong bg-surface shadow-md" style={{ width: width * scale, height: height * scale }}>
      {badge && (
        <span className="pointer-events-none absolute left-2 top-2 z-10 rounded-full bg-scrim px-2 py-0.5 text-xs font-medium text-white">
          {badge}
        </span>
      )}
      <iframe
        ref={(el) => register(variant, el)}
        title={`${title}预览`}
        src={src}
        style={{ width, height, border: 0, transform: `scale(${scale})`, transformOrigin: "0 0", background: "var(--bg)" }}
      />
    </div>
  );
}

export function PrototypeView() {
  const wide = useMediaQuery("(min-width: 1024px)");
  const { pref } = useTheme();
  const [scenarioId, setScenarioId] = useState("dns");
  const scenario = SCENARIOS.find((s) => s.id === scenarioId) ?? SCENARIOS[0];
  const [mode, setMode] = useState<Mode>("improved");
  const [width, setWidth] = useState(1280);
  const [widthDraft, setWidthDraft] = useState("1280");
  const [fit, setFit] = useState(true);
  const [panelOpen, setPanelOpen] = useState(() => window.innerWidth >= 1024);
  const [dockOpen, setDockOpen] = useState(false);
  const [dockHover, setDockHover] = useState(false);
  const expanded = dockOpen || dockHover;
  const canHover = useMediaQuery("(hover: hover)");
  const [sweep, setSweep] = useState(false);
  const [speed, setSpeed] = useState(240);
  const [tour, setTour] = useState(false);
  const [tourStep, setTourStep] = useState(0);
  const [fs, setFs] = useState<FrameState | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [lost, setLost] = useState(false);

  const frames = useRef<Record<string, HTMLIFrameElement | null>>({});
  const areaRef = useRef<HTMLDivElement>(null);
  const area = useElementSize(areaRef);
  const dockBtnRef = useRef<HTMLButtonElement>(null);
  const dockPanelRef = useRef<HTMLDivElement>(null);
  const hoverCloseT = useRef(0);
  const widthTouched = useRef(false);
  const latest = useRef({ pref, to: scenario.to, mode });
  latest.current = { pref, to: scenario.to, mode };

  const register = useCallback((v: string, el: HTMLIFrameElement | null) => {
    frames.current[v] = el;
  }, []);
  const send = useCallback((msg: ToFrame) => {
    Object.values(frames.current).forEach((el) => el && postToFrame(el.contentWindow, msg));
  }, []);

  // 来自 iframe 的消息：就绪（补发主题 / 路由）与状态上报
  useEffect(() => {
    const on = (e: MessageEvent<FromFrame>) => {
      const d = e.data;
      if (!d || typeof d !== "object" || !String(d.type).startsWith("nimbus:")) return;
      const entry = Object.entries(frames.current).find(([, el]) => el?.contentWindow === e.source);
      if (!entry) return;
      setLoaded(true);
      if (d.type === "nimbus:ready") {
        postToFrame(e.source as Window, { type: "nimbus:theme", value: latest.current.pref });
        postToFrame(e.source as Window, { type: "nimbus:navigate", to: latest.current.to });
      } else if (d.type === "nimbus:state") {
        const want = latest.current.mode === "legacy" ? "legacy" : "cf";
        if (entry[0] === want) setFs((p) => (p && JSON.stringify(p) === JSON.stringify(d) ? p : d));
      }
    };
    window.addEventListener("message", on);
    return () => window.removeEventListener("message", on);
  }, []);

  useEffect(() => {
    if (loaded) {
      setLost(false);
      return;
    }
    const t = window.setTimeout(() => setLost(true), 6000);
    return () => window.clearTimeout(t);
  }, [loaded]);

  useEffect(() => send({ type: "nimbus:theme", value: pref }), [pref, send]);
  useEffect(() => setWidthDraft(String(width)), [width]);

  // 宽度自动扫描（应力测试）：在 SWEEP_MIN ~ SWEEP_MAX 之间往返
  const pos = useRef(width);
  useEffect(() => {
    if (!sweep) return;
    widthTouched.current = true;
    pos.current = width;
    let dir = pos.current >= SWEEP_MAX ? -1 : 1;
    let last = performance.now();
    let raf = 0;
    const tick = (t: number) => {
      const dt = Math.min((t - last) / 1000, 0.1);
      last = t;
      pos.current += dir * speed * dt;
      if (pos.current >= SWEEP_MAX) {
        pos.current = SWEEP_MAX;
        dir = -1;
      } else if (pos.current <= SWEEP_MIN) {
        pos.current = SWEEP_MIN;
        dir = 1;
      }
      setWidth(Math.round(pos.current));
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sweep, speed]);

  // 侧边栏行为演示脚本
  useEffect(() => {
    if (!tour) return;
    send({ type: "nimbus:sidebar", action: TOUR[tourStep].action });
    const t = window.setTimeout(() => setTourStep((s) => (s + 1) % TOUR.length), 3400);
    return () => window.clearTimeout(t);
  }, [tour, tourStep, send]);
  useEffect(() => {
    if (!tour) send({ type: "nimbus:sidebar", action: "peek-off" });
  }, [tour, send]);

  const startTour = () => {
    if (tour) return setTour(false);
    setSweep(false);
    if (width < 1100) {
      widthTouched.current = true;
      setWidth(1280);
    }
    if (mode === "legacy") setMode("improved");
    setTourStep(0);
    setTour(true);
  };
  const manualWidth = (w: number) => {
    widthTouched.current = true;
    setSweep(false);
    setWidth(clamp(Math.round(w), MIN_W, MAX_W));
  };
  // 并排对比时两个视口需要共享舞台宽度：过宽会被缩得难以阅读，自动落到平板宽度（用户可随时再调）
  const pickMode = (v: Mode) => {
    setMode(v);
    if (v === "compare" && width > 900 && !sweep) {
      widthTouched.current = true;
      setWidth(768);
    }
  };
  const pickScenario = (id: string) => {
    const s = SCENARIOS.find((x) => x.id === id);
    if (!s) return;
    setScenarioId(id);
    send({ type: "nimbus:navigate", to: s.to });
    if (!wide) setPanelOpen(false);
  };

  // 底 dock：默认收起为半透明坞条；有悬停能力的设备上，鼠标进入展开、移出 160ms 后收起。
  // 触屏 / 键盘靠点击固定（dockOpen），悬停展开不抢焦点，点击展开后焦点送入面板、关闭后回到坞条。
  const cancelHoverClose = () => {
    if (hoverCloseT.current) {
      window.clearTimeout(hoverCloseT.current);
      hoverCloseT.current = 0;
    }
  };
  const onDockEnter = () => {
    if (!canHover) return;
    cancelHoverClose();
    setDockHover(true);
  };
  const onDockLeave = () => {
    if (!canHover) return;
    cancelHoverClose();
    hoverCloseT.current = window.setTimeout(() => setDockHover(false), 160);
  };
  const openDock = () => {
    cancelHoverClose();
    setDockOpen(true);
  };
  const closeDock = () => {
    cancelHoverClose();
    setDockOpen(false);
    setDockHover(false);
    window.setTimeout(() => dockBtnRef.current?.focus({ preventScroll: true }), 0);
  };
  useEffect(() => {
    if (dockOpen) dockPanelRef.current?.focus({ preventScroll: true });
  }, [dockOpen]);
  useEffect(
    () => () => {
      if (hoverCloseT.current) window.clearTimeout(hoverCloseT.current);
    },
    [],
  );

  // 舞台尺寸换算：并排对比时按总宽度等比缩放
  // 底部控制条为真悬浮（absolute 覆盖），不参与舞台尺寸换算、不预留高度，演示区独享全部高度
  // 设计稿与演示台之间零间隔：舞台内边距为 0，设计稿贴边铺满
  const count = mode === "compare" ? 2 : 1;
  const GAP = 24;
  const availW = Math.max(area.w - GAP * (count - 1), 120);
  const availH = Math.max(area.h, 240);
  const scale = fit ? Math.min(1, availW / (count * width)) : 1;
  const frameH = fit ? availH / scale : Math.max(availH, 480);
  const base = window.location.href.split("#")[0];
  const newTab = `${base}#${scenario.to}?theme=${pref}${mode === "legacy" ? "&variant=legacy" : ""}`;

  // 主体默认铺满演示台：用户手动调宽之前，预览宽度跟随舞台可用宽度（左右无留白）
  useEffect(() => {
    if (widthTouched.current || sweep || area.w <= 0) return;
    const avail = Math.max(area.w - GAP * (count - 1), 120);
    const n = clamp(Math.round(avail / count), MIN_W, MAX_W);
    setWidth((p) => (p === n ? p : n));
  }, [area.w, count, sweep]);

  return (
    <div className="absolute inset-0 flex min-h-0">
      <Panel open={panelOpen} onClose={() => setPanelOpen(false)} inflow={wide} label="场景与要点">
        <div className="grid gap-6 p-4">
          <p className="rounded-md bg-primary-soft p-3 text-sm">
            <strong>怎么玩：</strong>选一个场景 → 悬停底部坞条展开控制面板拖动宽度滑条 → 在预览里折叠侧边栏，把鼠标移上去再移开。
          </p>
          <div>
            <h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted">场景</h2>
            <ul className="grid gap-1">
              {SCENARIOS.map((s) => (
                <li key={s.id}>
                  <button
                    type="button"
                    aria-pressed={s.id === scenarioId}
                    onClick={() => pickScenario(s.id)}
                    className="block w-full rounded-md border border-transparent bg-transparent px-3 py-2 text-left text-fg hover:bg-hover aria-pressed:border-line-strong aria-pressed:bg-active"
                  >
                    <span className="block font-semibold">{s.title}</span>
                    <span className="block text-xs text-muted">{s.sub}</span>
                  </button>
                </li>
              ))}
            </ul>
          </div>
          <div>
            <h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted">本场景设计要点</h2>
            <ul className="grid list-disc gap-2 pl-4">
              {scenario.points.map((p) => (
                <li key={p}>{p}</li>
              ))}
            </ul>
            <p className="mt-3 text-sm">
              详见文档：
              <Link to={`/docs/${scenario.doc}`} className="link">
                {scenario.doc}
              </Link>
            </p>
          </div>
          <div>
            <h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted">试一试</h2>
            <ul className="grid list-decimal gap-2 pl-4">
              {scenario.tries.map((p) => (
                <li key={p}>{p}</li>
              ))}
            </ul>
          </div>
        </div>
      </Panel>

      <div className="relative flex min-w-0 flex-1 flex-col bg-canvas">
        <div className="flex flex-none flex-wrap items-center gap-x-3 gap-y-2 border-b border-line bg-bg px-4 py-2">
          <button type="button" className="btn btn-ghost btn-icon" aria-expanded={panelOpen} aria-label={panelOpen ? "收起场景面板" : "展开场景面板"} onClick={() => setPanelOpen((o) => !o)}>
            <PanelLeft size={18} aria-hidden="true" />
          </button>
          <div className="min-w-0 flex-1 basis-32">
            <p className="truncate font-semibold">{scenario.title}</p>
            <p className="truncate text-xs text-muted">{scenario.sub}</p>
          </div>
          <div className="seg" role="group" aria-label="查看模式">
            {(
              [
                ["improved", "改进方案"],
                ["legacy", "传统方案"],
                ["compare", "并排对比"],
              ] as const
            ).map(([v, l]) => (
              <button key={v} type="button" aria-pressed={mode === v} onClick={() => pickMode(v)}>
                {l}
              </button>
            ))}
          </div>
          <a className="btn" href={newTab} target="_blank" rel="noopener noreferrer">
            <ExternalLink size={16} aria-hidden="true" />
            <span className="max-sm:sr-only">新标签页打开</span>
            <span className="sr-only">（在新标签页中打开）</span>
          </a>
        </div>

        <div className="relative min-h-0 flex-1">
          <div ref={areaRef} className="absolute inset-0 overflow-auto">
            <div className="flex min-h-full items-start justify-center gap-6" style={{ width: "max-content", minWidth: "100%" }}>
              {mode !== "legacy" && (
                <FrameBox variant="cf" badge={mode === "compare" ? "改进方案" : undefined} width={width} height={frameH} scale={scale} initialTo={scenario.to} theme={pref} register={register} />
              )}
              {mode !== "improved" && (
                <FrameBox variant="legacy" badge={mode === "compare" ? "传统方案" : undefined} width={width} height={frameH} scale={scale} initialTo={scenario.to} theme={pref} register={register} />
              )}
            </div>
          </div>

          {lost && (
            <p className="alert alert-warn absolute left-4 right-4 top-4 z-10 mx-auto max-w-lg" role="status">
              预览尚未加载。如果运行环境禁止嵌入同源页面，请使用上方“新标签页打开”。
            </p>
          )}

          {/* 底 dock：默认收起为半透明坞条，悬停展开完整面板；真悬浮，不占演示区 */}
          <div
            className="pointer-events-none absolute bottom-4 left-1/2 z-10 flex w-[min(920px,calc(100%-16px))] -translate-x-1/2 justify-center"
            onMouseEnter={onDockEnter}
            onMouseLeave={onDockLeave}
          >
          {expanded ? (
            <div
              ref={dockPanelRef}
              tabIndex={-1}
              id="preview-dock-panel"
              role="region"
              aria-label="预览控制"
              style={{ animation: "drop-in 0.18s ease-out" }}
              className="pointer-events-auto grid w-full gap-3 rounded-lg border border-line-strong bg-surface/85 p-3 shadow-lg backdrop-blur-md"
            >
              <div className="flex flex-wrap items-center gap-3">
                <button type="button" className={cn("btn", sweep && "btn-primary")} aria-pressed={sweep} onClick={() => setSweep((s) => !s)}>
                  {sweep ? <Pause size={16} aria-hidden="true" /> : <Play size={16} aria-hidden="true" />}
                  {sweep ? "暂停扫描" : "宽度扫描"}
                </button>
                <div className="flex min-w-48 flex-1 items-center gap-3">
                  <input
                    type="range"
                    className="min-w-0 flex-1"
                    min={MIN_W}
                    max={MAX_W}
                    step={1}
                    list="bp-list"
                    value={width}
                    aria-label="预览视口宽度"
                    aria-valuetext={`${width} 像素，${layoutName(fs?.layout)}`}
                    onChange={(e) => manualWidth(Number(e.target.value))}
                  />
                  <datalist id="bp-list">
                    {[390, 640, 768, 1024, 1280].map((v) => (
                      <option key={v} value={v} />
                    ))}
                  </datalist>
                  <label className="flex flex-none items-center gap-2">
                    <span className="sr-only">宽度（像素）</span>
                    <input
                      type="number"
                      className="input w-24"
                      min={MIN_W}
                      max={MAX_W}
                      value={widthDraft}
                      onChange={(e) => setWidthDraft(e.target.value)}
                      onBlur={() => manualWidth(Number(widthDraft) || width)}
                      onKeyDown={(e) => e.key === "Enter" && manualWidth(Number(widthDraft) || width)}
                    />
                    <span className="text-muted">px</span>
                  </label>
                </div>
                <button type="button" className="btn btn-ghost btn-icon ml-auto" aria-label="收起控制浮层" onClick={closeDock}>
                  <ChevronDown size={18} aria-hidden="true" />
                </button>
              </div>

              <div className="flex flex-wrap items-center gap-2" role="group" aria-label="常用宽度">
                {PRESETS.map((p) => (
                  <button
                    key={p.w}
                    type="button"
                    aria-pressed={width === p.w}
                    onClick={() => manualWidth(p.w)}
                    className="inline-flex min-h-7 items-center rounded-full border border-line-strong bg-transparent px-3 text-xs font-medium text-fg hover:bg-hover aria-pressed:border-primary aria-pressed:bg-primary aria-pressed:text-white"
                  >
                    {p.w} · {p.t}
                  </button>
                ))}
              </div>

              <div className="flex flex-wrap items-center gap-x-4 gap-y-2 border-t border-line pt-3">
                <div className="flex items-center gap-2">
                  <span id="fit-l" className="text-sm">
                    适应舞台
                  </span>
                  <Switch checked={fit} onChange={setFit} aria-labelledby="fit-l" />
                </div>
                <label className="flex items-center gap-2 text-sm">
                  扫描速度
                  <Select className="!w-24" value={speed} onChange={(e) => setSpeed(Number(e.target.value))}>
                    <option value={120}>慢</option>
                    <option value={240}>中</option>
                    <option value={480}>快</option>
                  </Select>
                </label>
                <div className="seg" role="group" aria-label="侧边栏固定状态（手动控制）">
                  {(
                    [
                      ["pin-expanded", "expanded", "侧边栏展开"],
                      ["pin-collapsed", "collapsed", "折叠为图标栏"],
                    ] as const
                  ).map(([action, value, label]) => (
                    <button
                      key={action}
                      type="button"
                      disabled={mode === "legacy"}
                      aria-pressed={mode !== "legacy" && fs?.pinned === value}
                      onClick={() => {
                        setTour(false);
                        send({ type: "nimbus:sidebar", action });
                      }}
                    >
                      {label}
                    </button>
                  ))}
                </div>
                <button type="button" className={cn("btn", tour && "btn-primary")} aria-pressed={tour} onClick={startTour}>
                  <Hand size={16} aria-hidden="true" />
                  {tour ? "停止侧边栏演示" : "侧边栏行为演示"}
                </button>
              </div>

              <dl className="flex flex-wrap gap-x-6 gap-y-1 text-xs text-muted">
                <div>
                  <dt className="inline">方案：</dt>
                  <dd className="inline font-medium text-fg">{mode === "compare" ? "左 改进方案 · 右 传统方案" : mode === "legacy" ? "传统方案 · 反例" : "改进方案 · CF 规范"}</dd>
                </div>
                <div>
                  <dt className="inline">视口：</dt>
                  <dd className="inline font-medium text-fg">
                    {width}×{Math.round(frameH)} · {Math.round(scale * 100)}%
                  </dd>
                </div>
                <div>
                  <dt className="inline">布局：</dt>
                  <dd className="inline font-medium text-fg">{mode === "legacy" ? "固定侧边栏（无响应）" : layoutName(fs?.layout)}</dd>
                </div>
                <div>
                  <dt className="inline">侧边栏：</dt>
                  <dd className="inline font-medium text-fg">{mode === "legacy" ? "固定 220px" : sidebarName(fs)}</dd>
                </div>
                {tour && (
                  <div className="basis-full text-sm font-medium text-link">
                    <dd>{TOUR[tourStep].text}</dd>
                  </div>
                )}
              </dl>
            </div>
          ) : (
            <button
              ref={dockBtnRef}
              type="button"
              className="btn pointer-events-auto rounded-full bg-surface/70 shadow-lg backdrop-blur-md hover:bg-surface/90"
              onClick={openDock}
              aria-label={`展开控制浮层，当前视口 ${width}×${Math.round(frameH)}，缩放 ${Math.round(scale * 100)}%`}
              aria-expanded={expanded}
              aria-controls="preview-dock-panel"
              title="悬停或点击展开控制面板"
            >
              <ChevronUp size={16} aria-hidden="true" />
              {width}×{Math.round(frameH)} · {Math.round(scale * 100)}%
            </button>
          )}
          </div>
        </div>
      </div>
    </div>
  );
}
