import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type KeyboardEvent,
  type PointerEvent as RPointerEvent,
  type RefObject,
} from "react";

/* ==========================================================================
   可调列宽（table-layout: fixed + <colgroup>）

   - 拖动过程中只直接改写 <col> 与 <table> 的 style（零 React 重渲染）；松手时一次性提交到 state 并持久化
   - 键盘：聚焦分隔条后 ←/→ 调整 8px（Shift 32px），Home/End 到最小 / 最大，Enter 或双击恢复默认
   - 表格 min-width = 各列宽之和 + 固定列宽；容器更宽时由一列「填充列」（<col /> 无宽度）吸收剩余空间，
     因此用户设置的列宽永远是精确值，不会被按比例拉伸
   ========================================================================== */

export interface ColSpec {
  id: string;
  min: number;
  def: number;
  max?: number;
}
const MAX_W = 720;

function load(key: string, specs: ColSpec[]): Record<string, number> {
  const out: Record<string, number> = Object.fromEntries(specs.map((s) => [s.id, s.def]));
  try {
    const raw = localStorage.getItem(key);
    if (raw) {
      const o = JSON.parse(raw) as Record<string, unknown>;
      for (const s of specs) {
        const v = o[s.id];
        if (typeof v === "number" && Number.isFinite(v)) out[s.id] = Math.min(s.max ?? MAX_W, Math.max(s.min, v));
      }
    }
  } catch {
    /* 损坏的存储值直接忽略，使用默认宽度 */
  }
  return out;
}

export function useColumnWidths(storageKey: string, specs: ColSpec[], visible: string[], fixedExtra: number) {
  const [widths, setWidths] = useState(() => load(storageKey, specs));
  const cols = useRef(new Map<string, HTMLTableColElement>());
  const table = useRef<HTMLTableElement | null>(null);
  const latest = useRef({ widths, visible, fixedExtra });
  latest.current = { widths, visible, fixedExtra };

  const sum = (w: Record<string, number>) => latest.current.visible.reduce((a, id) => a + (w[id] ?? 0), 0) + latest.current.fixedExtra;

  const clampW = useCallback(
    (id: string, w: number) => {
      const s = specs.find((x) => x.id === id);
      return Math.round(Math.min(s?.max ?? MAX_W, Math.max(s?.min ?? 48, w)));
    },
    [specs],
  );

  /** 拖动中的即时预览：直接写 DOM，不触发 React 渲染 */
  const preview = useCallback(
    (id: string, w: number) => {
      const v = clampW(id, w);
      cols.current.get(id)?.style.setProperty("width", `${v}px`);
      const t = table.current;
      if (t) t.style.minWidth = `${latest.current.visible.reduce((a, c) => a + (c === id ? v : (latest.current.widths[c] ?? 0)), 0) + latest.current.fixedExtra}px`;
    },
    [clampW],
  );
  const commit = useCallback((id: string, w: number) => setWidths((p) => ({ ...p, [id]: clampW(id, w) })), [clampW]);
  const reset = useCallback((id: string) => setWidths((p) => ({ ...p, [id]: specs.find((s) => s.id === id)?.def ?? p[id] })), [specs]);
  const resetAll = useCallback(() => setWidths(Object.fromEntries(specs.map((s) => [s.id, s.def]))), [specs]);

  useEffect(() => {
    try {
      localStorage.setItem(storageKey, JSON.stringify(widths));
    } catch {
      /* 隐私模式：仅保存在内存 */
    }
  }, [storageKey, widths]);

  const colRef = (id: string) => (el: HTMLTableColElement | null) => {
    if (el) cols.current.set(id, el);
    else cols.current.delete(id);
  };
  const tableRef = useCallback((el: HTMLTableElement | null) => {
    table.current = el;
  }, []);

  const isDefault = specs.every((s) => widths[s.id] === s.def);
  return { widths, total: sum(widths), colRef, tableRef, preview, commit, reset, resetAll, isDefault };
}

/** 表头右缘的拖动分隔条（role="separator" + 可聚焦 + aria-valuenow，满足键盘与读屏） */
export function ResizeHandle({
  label,
  value,
  min,
  max = MAX_W,
  onPreview,
  onCommit,
  onReset,
}: {
  label: string;
  value: number;
  min: number;
  max?: number;
  onPreview: (w: number) => void;
  onCommit: (w: number) => void;
  onReset: () => void;
}) {
  const drag = useRef<{ x: number; w: number } | null>(null);
  const [active, setActive] = useState(false);
  const calc = (e: RPointerEvent) => Math.min(max, Math.max(min, (drag.current?.w ?? value) + e.clientX - (drag.current?.x ?? e.clientX)));

  const onKeyDown = (e: KeyboardEvent) => {
    const step = e.shiftKey ? 32 : 8;
    if (e.key === "ArrowLeft") onCommit(value - step);
    else if (e.key === "ArrowRight") onCommit(value + step);
    else if (e.key === "Home") onCommit(min);
    else if (e.key === "End") onCommit(max);
    else if (e.key === "Enter") onReset();
    else return;
    e.preventDefault();
  };

  return (
    <span
      role="separator"
      aria-orientation="vertical"
      aria-label={`Resize ${label} column`}
      aria-valuenow={Math.round(value)}
      aria-valuemin={min}
      aria-valuemax={max}
      tabIndex={0}
      className="col-resizer"
      data-active={active || undefined}
      title="Drag to resize · double-click to reset"
      onClick={(e) => e.stopPropagation()}
      onDoubleClick={onReset}
      onKeyDown={onKeyDown}
      onPointerDown={(e) => {
        if (e.button !== 0) return;
        e.preventDefault();
        e.currentTarget.setPointerCapture(e.pointerId);
        drag.current = { x: e.clientX, w: value };
        setActive(true);
      }}
      onPointerMove={(e) => {
        if (drag.current) onPreview(calc(e));
      }}
      onPointerUp={(e) => {
        if (!drag.current) return;
        const w = calc(e);
        drag.current = null;
        setActive(false);
        onCommit(w);
      }}
      onPointerCancel={() => {
        if (!drag.current) return;
        onPreview(drag.current.w);
        drag.current = null;
        setActive(false);
      }}
    />
  );
}

/**
 * 横向滚动的视觉提示：在容器上写入 data-more-left / data-more-right（CSS 据此给粘性列加阴影），
 * 并写入 --sw（容器可视宽度，供「行内编辑区」固定在可视范围内）。
 * 直接操作 DOM + rAF 合并，滚动时不触发 React 渲染。
 */
export function useScrollAffordance(ref: RefObject<HTMLElement | null>, key: unknown) {
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    let raf = 0;
    const update = () => {
      raf = 0;
      const max = el.scrollWidth - el.clientWidth;
      el.dataset.moreLeft = String(el.scrollLeft > 1);
      el.dataset.moreRight = String(el.scrollLeft < max - 1);
      el.style.setProperty("--sw", `${el.clientWidth}px`);
    };
    const schedule = () => {
      if (!raf) raf = requestAnimationFrame(update);
    };
    update();
    el.addEventListener("scroll", schedule, { passive: true });
    const ro = new ResizeObserver(schedule);
    ro.observe(el);
    if (el.firstElementChild) ro.observe(el.firstElementChild);
    return () => {
      cancelAnimationFrame(raf);
      el.removeEventListener("scroll", schedule);
      ro.disconnect();
    };
  }, [ref, key]);
}
