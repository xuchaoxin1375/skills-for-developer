import { useCallback, useEffect, useState, useSyncExternalStore, type RefObject } from "react";

export type Layout = "wide" | "medium" | "narrow";

/** 与 Tailwind 的 lg(1024) / md(768) 断点保持一致 */
const Q_WIDE = "(min-width: 1024px)";
const Q_MED = "(min-width: 768px)";

function getLayout(): Layout {
  if (window.matchMedia(Q_WIDE).matches) return "wide";
  if (window.matchMedia(Q_MED).matches) return "medium";
  return "narrow";
}

function subscribeLayout(cb: () => void) {
  const a = window.matchMedia(Q_WIDE);
  const b = window.matchMedia(Q_MED);
  a.addEventListener("change", cb);
  b.addEventListener("change", cb);
  return () => {
    a.removeEventListener("change", cb);
    b.removeEventListener("change", cb);
  };
}

export function useLayout(): Layout {
  return useSyncExternalStore(subscribeLayout, getLayout, () => "wide" as Layout);
}

export function useMediaQuery(q: string): boolean {
  const subscribe = useCallback(
    (cb: () => void) => {
      const m = window.matchMedia(q);
      m.addEventListener("change", cb);
      return () => m.removeEventListener("change", cb);
    },
    [q],
  );
  return useSyncExternalStore(
    subscribe,
    () => window.matchMedia(q).matches,
    () => false,
  );
}

/** 持久化到 localStorage 的受限字符串状态 */
export function usePersisted<T extends string>(key: string, initial: T, allowed?: readonly T[]): [T, (v: T) => void] {
  const [v, setV] = useState<T>(() => {
    try {
      const s = localStorage.getItem(key) as T | null;
      if (s && (!allowed || allowed.includes(s))) return s;
    } catch {
      /* ignore */
    }
    return initial;
  });
  const set = useCallback(
    (n: T) => {
      setV(n);
      try {
        localStorage.setItem(key, n);
      } catch {
        /* ignore */
      }
    },
    [key],
  );
  return [v, set];
}

export function useViewportWidth(): number {
  const [w, setW] = useState(() => window.innerWidth);
  useEffect(() => {
    let raf = 0;
    const on = () => {
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(() => setW(window.innerWidth));
    };
    window.addEventListener("resize", on);
    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("resize", on);
    };
  }, []);
  return w;
}

export function useElementSize(ref: RefObject<HTMLElement | null>): { w: number; h: number } {
  const [size, setSize] = useState({ w: 0, h: 0 });
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const ro = new ResizeObserver(([entry]) => {
      const r = entry.contentRect;
      setSize((p) => (Math.abs(p.w - r.width) < 0.5 && Math.abs(p.h - r.height) < 0.5 ? p : { w: r.width, h: r.height }));
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, [ref]);
  return size;
}

/** 元素宽度是否小于阈值：仅在跨越阈值时才触发重渲染（宽度扫描 / 拖动时零额外开销） */
export function useBelow(ref: RefObject<HTMLElement | null>, px: number): boolean {
  const [below, setBelow] = useState(false);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const ro = new ResizeObserver(([entry]) => {
      const v = entry.contentRect.width < px;
      setBelow((p) => (p === v ? p : v));
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, [ref, px]);
  return below;
}

export function isEditable(t: EventTarget | null): boolean {
  const el = t as HTMLElement | null;
  if (!el || !el.tagName) return false;
  return el.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(el.tagName);
}
