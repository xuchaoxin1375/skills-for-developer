import { useCallback, useEffect, useRef, useState } from "react";
import { cn } from "@/utils/cn";

/**
 * Column width model for resizable tables.
 * - widths live in React state during a drag (cheap re-render of one table);
 * - they are persisted to localStorage only on pointer-up / keyboard change.
 */
export interface ColumnDef {
  key: string;
  width: number;
  min?: number;
  max?: number;
  /** cannot be resized (checkbox, actions) */
  fixed?: boolean;
}

export function useColumnWidths(storageKey: string, defs: ColumnDef[]) {
  const defaults = useCallback(() => Object.fromEntries(defs.map((d) => [d.key, d.width])), [defs]);
  const [widths, setWidths] = useState<Record<string, number>>(() => {
    try {
      const raw = localStorage.getItem(storageKey);
      if (!raw) return defaults();
      const stored = JSON.parse(raw) as Record<string, number>;
      // fixed columns always use the code default (they are not user-resizable)
      const merged = { ...defaults() };
      for (const d of defs) if (!d.fixed && typeof stored[d.key] === "number") merged[d.key] = stored[d.key];
      return merged;
    } catch {
      return defaults();
    }
  });

  const persist = useCallback(
    (w: Record<string, number>) => {
      try {
        localStorage.setItem(storageKey, JSON.stringify(w));
      } catch {
        /* ignore */
      }
    },
    [storageKey]
  );

  const clamp = useCallback(
    (key: string, w: number) => {
      const d = defs.find((x) => x.key === key);
      return Math.round(Math.max(d?.min ?? 60, Math.min(d?.max ?? 720, w)));
    },
    [defs]
  );

  const set = useCallback(
    (key: string, w: number, commit = false) => {
      setWidths((s) => {
        const next = { ...s, [key]: clamp(key, w) };
        if (commit) persist(next);
        return next;
      });
    },
    [clamp, persist]
  );

  const reset = useCallback(
    (key?: string) => {
      setWidths((s) => {
        const next = key ? { ...s, [key]: defaults()[key] } : defaults();
        persist(next);
        return next;
      });
    },
    [defaults, persist]
  );

  const commit = useCallback(() => setWidths((s) => (persist(s), s)), [persist]);

  return { widths, set, reset, commit };
}

/**
 * Drag handle placed at the right edge of a <th>.
 * Pointer: drag to resize, double-click to reset. Keyboard: ← → (16px), Shift for 64px, Home resets.
 */
export function ColumnResizer({
  colKey,
  label,
  width,
  onResize,
  onCommit,
  onReset,
}: {
  colKey: string;
  label: string;
  width: number;
  onResize: (key: string, w: number) => void;
  onCommit: () => void;
  onReset: (key: string) => void;
}) {
  const start = useRef<{ x: number; w: number } | null>(null);
  const [active, setActive] = useState(false);

  useEffect(() => {
    if (!active) return;
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
    return () => {
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
    };
  }, [active]);

  return (
    <div
      role="separator"
      aria-orientation="vertical"
      aria-label={`Resize ${label} column`}
      aria-valuenow={width}
      aria-valuemin={60}
      aria-valuemax={720}
      tabIndex={0}
      onPointerDown={(e) => {
        if (e.button !== 0) return;
        e.preventDefault();
        (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
        start.current = { x: e.clientX, w: width };
        setActive(true);
      }}
      onPointerMove={(e) => {
        if (!start.current) return;
        onResize(colKey, start.current.w + (e.clientX - start.current.x));
      }}
      onPointerUp={(e) => {
        if (!start.current) return;
        (e.currentTarget as HTMLElement).releasePointerCapture(e.pointerId);
        start.current = null;
        setActive(false);
        onCommit();
      }}
      onPointerCancel={() => {
        start.current = null;
        setActive(false);
      }}
      onDoubleClick={() => onReset(colKey)}
      onKeyDown={(e) => {
        const step = e.shiftKey ? 64 : 16;
        if (e.key === "ArrowLeft") {
          e.preventDefault();
          onResize(colKey, width - step);
          onCommit();
        } else if (e.key === "ArrowRight") {
          e.preventDefault();
          onResize(colKey, width + step);
          onCommit();
        } else if (e.key === "Home") {
          e.preventDefault();
          onReset(colKey);
        }
      }}
      className={cn(
        // kept fully inside the <th> (which is overflow:hidden); the visible line sits on the right edge
        "absolute top-0 right-0 h-full w-2 cursor-col-resize z-[1] group/resizer flex justify-end touch-none",
        "focus-visible:outline-none"
      )}
    >
      <span
        aria-hidden
        className={cn(
          "block w-px h-full bg-line transition-colors",
          "group-hover/resizer:w-[3px] group-hover/resizer:bg-primary group-focus-visible/resizer:w-[3px] group-focus-visible/resizer:bg-primary",
          active && "w-[3px] bg-primary"
        )}
      />
    </div>
  );
}
