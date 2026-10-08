import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { Columns3, Maximize2, Monitor, Pause, Play, RectangleHorizontal, RotateCcw, Smartphone, Tablet } from "lucide-react";
import { cn } from "@/utils/cn";
import { Button, Input, Segmented, Select } from "@/components/ui/primitives";
import { Alert, Card, PageHeader } from "@/components/ui/layout";
import { useTheme } from "@/lib/theme";

const MIN = 280; // narrowest preview
const MAX = 1600;
const PRESETS = [
  { w: 320, label: "320", icon: Smartphone, note: "Minimum reflow target" },
  { w: 390, label: "390", icon: Smartphone, note: "Modern phone" },
  { w: 768, label: "768", icon: Tablet, note: "Tablet / rail sidebar" },
  { w: 1024, label: "1024", icon: Monitor, note: "Desktop breakpoint" },
  { w: 1440, label: "1440", icon: Monitor, note: "Reference desktop" },
];
const ROUTES = [
  { value: "/dns/records", label: "DNS records (table + inline form)" },
  { value: "/forms/create", label: "Create application (long form)" },
  { value: "/forms/wizard", label: "Add a domain (wizard)" },
  { value: "/settings", label: "Settings (cards)" },
  { value: "/", label: "Overview (dashboard)" },
];

function frameSrc(route: string) {
  const u = new URL(window.location.href);
  u.searchParams.set("frame", "1");
  u.hash = "#" + route;
  return u.toString();
}

function bpFor(w: number) {
  if (w < 640) return { name: "Mobile (xs)", desc: "Drawer nav · card list instead of table · stacked buttons" };
  if (w < 768) return { name: "Mobile (sm)", desc: "Drawer nav · table with contained horizontal scroll" };
  if (w < 1024) return { name: "Tablet (md)", desc: "Rail sidebar with hover-peek · single column forms" };
  if (w < 1280) return { name: "Desktop (lg)", desc: "Sidebar pinned by default · outline column appears" };
  return { name: "Wide (xl+)", desc: "Full layout · 4-column stat grids" };
}

function Frame({ width, route, height, theme, onReady }: { width: number; route: string; height: number; theme: string; onReady?: (w: Window) => void }) {
  const ref = useRef<HTMLIFrameElement>(null);
  const wrap = useRef<HTMLDivElement>(null);
  const [scale, setScale] = useState(1);
  const src = useMemo(() => frameSrc(route), []); // eslint-disable-line react-hooks/exhaustive-deps

  // navigate without reload
  useEffect(() => {
    const w = ref.current?.contentWindow;
    if (w && w.location.hash !== "#" + route) {
      try {
        w.location.hash = "#" + route;
      } catch {
        /* cross-origin unlikely */
      }
    }
  }, [route]);

  // propagate theme
  useEffect(() => {
    try {
      ref.current?.contentDocument?.documentElement.setAttribute("data-theme", theme);
    } catch {
      /* ignore */
    }
  }, [theme]);

  // scale down when the preview is wider than the available space
  useLayoutEffect(() => {
    const el = wrap.current;
    if (!el) return;
    const ro = new ResizeObserver(([e]) => {
      const avail = e.contentRect.width;
      setScale(avail > 0 && width > avail ? avail / width : 1);
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, [width]);

  return (
    <div ref={wrap} className="w-full flex justify-center">
      <div style={{ width: width * scale, height: height * scale }} className="relative">
        <div
          style={{ width, height, transform: `scale(${scale})`, transformOrigin: "top left" }}
          className="absolute left-0 top-0 rounded-md overflow-hidden border border-line-strong bg-bg shadow-2"
        >
          <iframe
            ref={ref}
            title={`Preview at ${width}px`}
            src={src}
            width={width}
            height={height}
            className="block border-0 bg-bg"
            onLoad={() => {
              try {
                ref.current?.contentDocument?.documentElement.setAttribute("data-theme", theme);
                if (ref.current?.contentWindow) onReady?.(ref.current.contentWindow);
              } catch {
                /* ignore */
              }
            }}
          />
        </div>
      </div>
    </div>
  );
}

export function ResponsiveLabPage() {
  const { resolved } = useTheme();
  const [mode, setMode] = useState<"single" | "triple">("single");
  const [width, setWidth] = useState(1024);
  const [route, setRoute] = useState(ROUTES[0].value);
  const [height, setHeight] = useState(720);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(1);
  const dir = useRef(-1);
  const raf = useRef<number | null>(null);
  const last = useRef<number>(0);
  const [controlsDocked, setControlsDocked] = useState(true);

  const stop = useCallback(() => {
    setPlaying(false);
    if (raf.current) cancelAnimationFrame(raf.current);
    raf.current = null;
  }, []);

  // auto sweep: ping-pong between MIN and MAX; pauses briefly at preset widths
  useEffect(() => {
    if (!playing) return;
    const pxPerSec = 260 * speed;
    const tick = (t: number) => {
      if (!last.current) last.current = t;
      const dt = (t - last.current) / 1000;
      last.current = t;
      setWidth((w) => {
        let n = w + dir.current * pxPerSec * dt;
        if (n <= MIN) { n = MIN; dir.current = 1; }
        if (n >= MAX) { n = MAX; dir.current = -1; }
        return Math.round(n);
      });
      raf.current = requestAnimationFrame(tick);
    };
    last.current = 0;
    raf.current = requestAnimationFrame(tick);
    return () => {
      if (raf.current) cancelAnimationFrame(raf.current);
    };
  }, [playing, speed]);

  // pause with Space when the lab has focus and user isn't typing
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement;
      if (t && (t.tagName === "INPUT" || t.tagName === "SELECT" || t.tagName === "TEXTAREA")) return;
      if (e.key === " " ) { e.preventDefault(); setPlaying((p) => !p); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const bp = bpFor(width);

  const controls = (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <Segmented
          ariaLabel="View mode"
          value={mode}
          onChange={(m) => { setMode(m); if (m === "triple") stop(); }}
          options={[
            { value: "single", label: <><RectangleHorizontal className="size-4" /> <span className="hidden sm:inline">Single</span></>, title: "Single width with slider" },
            { value: "triple", label: <><Columns3 className="size-4" /> <span className="hidden sm:inline">Side by side</span></>, title: "390 / 768 / 1440 together" },
          ]}
        />
        <Select aria-label="Page to preview" value={route} onChange={(e) => setRoute(e.target.value)} options={ROUTES} className="min-w-[200px] flex-1 sm:flex-none sm:w-[300px]" />
        <Select aria-label="Preview height" value={String(height)} onChange={(e) => setHeight(Number(e.target.value))} options={[{ value: "560", label: "560 px tall" }, { value: "720", label: "720 px tall" }, { value: "900", label: "900 px tall" }]} className="w-[130px]" />
        <Button variant="ghost" size="md" square aria-label={controlsDocked ? "Undock controls" : "Dock controls"} onClick={() => setControlsDocked((d) => !d)} icon={<Maximize2 className="size-4" />} className="ml-auto hidden lg:inline-flex" />
      </div>

      {mode === "single" && (
        <>
          <div className="flex flex-wrap items-center gap-2">
            <div className="flex items-center gap-1 flex-wrap">
              {PRESETS.map((p) => (
                <Button key={p.w} size="sm" variant={width === p.w ? "primary" : "secondary"} aria-pressed={width === p.w} title={p.note} onClick={() => { stop(); setWidth(p.w); }} icon={<p.icon className="size-3.5" />}>
                  {p.label}
                </Button>
              ))}
            </div>
            <div className="flex items-center gap-2 ml-auto">
              <Button size="sm" variant={playing ? "secondary" : "primary"} onClick={() => setPlaying((p) => !p)} icon={playing ? <Pause className="size-4" /> : <Play className="size-4" />} aria-pressed={playing}>
                {playing ? "Pause" : "Auto sweep"}
              </Button>
              <Select aria-label="Sweep speed" value={String(speed)} onChange={(e) => setSpeed(Number(e.target.value))} options={[{ value: "0.5", label: "0.5×" }, { value: "1", label: "1×" }, { value: "2", label: "2×" }]} className="w-[84px]" />
              <Button size="sm" variant="ghost" square aria-label="Reset" onClick={() => { stop(); setWidth(1024); }} icon={<RotateCcw className="size-4" />} />
            </div>
          </div>
          <div className="flex items-center gap-3">
            <label htmlFor="lab-width" className="text-sm text-fg-2 shrink-0 w-12">Width</label>
            <input
              id="lab-width"
              type="range"
              min={MIN}
              max={MAX}
              step={1}
              value={width}
              onChange={(e) => { stop(); setWidth(Number(e.target.value)); }}
              className="flex-1 accent-[var(--c-primary)] h-6 cursor-pointer min-w-0"
              aria-valuetext={`${width} pixels, ${bp.name}`}
            />
            <Input aria-label="Width in pixels" inputMode="numeric" value={String(width)} onChange={(e) => { const n = Number(e.target.value); if (Number.isFinite(n)) setWidth(Math.max(MIN, Math.min(MAX, n))); }} className="w-[88px]" trailing={<span className="text-xs text-fg-3">px</span>} />
          </div>
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm">
            <span className="font-medium text-fg tabular-nums">{width}px</span>
            <span className="text-primary-text font-medium">{bp.name}</span>
            <span className="text-fg-3">{bp.desc}</span>
          </div>
        </>
      )}
    </div>
  );

  return (
    <>
      <PageHeader title="Responsive Lab" description="Preview any page of this mock at an exact viewport width. The preview is a real frame, so media queries, the sidebar state machine and overlays behave exactly as they would on a device." />

      <Alert tone="info" className="mb-4">
        Tips: press <kbd className="font-sans text-xs border border-line rounded-xs px-1">Space</kbd> to toggle the auto sweep. Previews wider than this window are scaled down to fit — the frame still reports the real CSS width.
      </Alert>

      <Card className={cn("p-4 mb-4 z-30", controlsDocked && "lg:sticky lg:top-[calc(var(--topbar-h)_+_12px)]")}>{controls}</Card>

      {mode === "single" ? (
        <Frame width={width} route={route} height={height} theme={resolved} />
      ) : (
        <div className="grid grid-cols-1 xl:grid-cols-[390px_minmax(0,1fr)] gap-4">
          <div>
            <p className="text-sm text-fg-2 mb-2">390 px · Mobile</p>
            <Frame width={390} route={route} height={height} theme={resolved} />
          </div>
          <div className="space-y-4 min-w-0">
            <div>
              <p className="text-sm text-fg-2 mb-2">768 px · Tablet (rail sidebar — hover it)</p>
              <Frame width={768} route={route} height={Math.round(height * 0.8)} theme={resolved} />
            </div>
            <div>
              <p className="text-sm text-fg-2 mb-2">1440 px · Desktop (scaled to fit)</p>
              <Frame width={1440} route={route} height={height} theme={resolved} />
            </div>
          </div>
        </div>
      )}
    </>
  );
}
