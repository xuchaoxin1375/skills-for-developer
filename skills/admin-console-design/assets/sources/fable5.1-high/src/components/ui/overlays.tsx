import {
  cloneElement,
  createContext,
  useCallback,
  useContext,
  useEffect,
  useId,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { createPortal } from "react-dom";
import { CheckCircle2, AlertTriangle, Info, X, XCircle } from "lucide-react";
import { cn } from "@/utils/cn";
import { useClickOutside, useEscape } from "@/lib/hooks";
import { Button } from "./primitives";

/* ---------------------------------------------------------------- Tooltip */
type Side = "top" | "bottom" | "left" | "right";

export function Tooltip({
  content,
  children,
  side = "top",
  delay = 250,
  disabled,
}: {
  content: React.ReactNode;
  children: React.ReactElement<any>;
  side?: Side;
  delay?: number;
  disabled?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [pos, setPos] = useState<{ top: number; left: number } | null>(null);
  const anchor = useRef<HTMLElement | null>(null);
  const tip = useRef<HTMLDivElement | null>(null);
  const timer = useRef<number | null>(null);
  const id = useId();

  const show = () => {
    if (disabled) return;
    if (timer.current) window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => setOpen(true), delay);
  };
  const hide = () => {
    if (timer.current) window.clearTimeout(timer.current);
    setOpen(false);
  };

  useLayoutEffect(() => {
    if (!open || !anchor.current || !tip.current) return;
    const a = anchor.current.getBoundingClientRect();
    const t = tip.current.getBoundingClientRect();
    const gap = 8;
    let top = 0;
    let left = 0;
    if (side === "top") {
      top = a.top - t.height - gap;
      left = a.left + a.width / 2 - t.width / 2;
    } else if (side === "bottom") {
      top = a.bottom + gap;
      left = a.left + a.width / 2 - t.width / 2;
    } else if (side === "right") {
      top = a.top + a.height / 2 - t.height / 2;
      left = a.right + gap;
    } else {
      top = a.top + a.height / 2 - t.height / 2;
      left = a.left - t.width - gap;
    }
    // clamp into viewport
    left = Math.max(8, Math.min(left, window.innerWidth - t.width - 8));
    top = Math.max(8, Math.min(top, window.innerHeight - t.height - 8));
    setPos({ top, left });
  }, [open, side]);

  useEscape(hide, open);

  const child = cloneElement(children, {
    ref: (el: HTMLElement | null) => {
      anchor.current = el;
      const r = children.props.ref; // React 19: ref is a regular prop
      if (typeof r === "function") r(el);
      else if (r) r.current = el;
    },
    onMouseEnter: (e: any) => {
      children.props.onMouseEnter?.(e);
      show();
    },
    onMouseLeave: (e: any) => {
      children.props.onMouseLeave?.(e);
      hide();
    },
    onFocus: (e: any) => {
      children.props.onFocus?.(e);
      show();
    },
    onBlur: (e: any) => {
      children.props.onBlur?.(e);
      hide();
    },
    "aria-describedby": open ? id : children.props["aria-describedby"],
  });

  return (
    <>
      {child}
      {open &&
        createPortal(
          <div
            ref={tip}
            id={id}
            role="tooltip"
            style={pos ? { top: pos.top, left: pos.left } : { top: -9999, left: -9999 }}
            className="fixed z-[80] max-w-[280px] px-2.5 py-1.5 rounded-sm bg-fg text-fg-inverse text-xs leading-[18px] shadow-2 anim-fade pointer-events-none"
          >
            {content}
          </div>,
          document.body
        )}
    </>
  );
}

/* ---------------------------------------------------------------- Popover */
export function Popover({
  open,
  onOpenChange,
  trigger,
  children,
  align = "start",
  width = 360,
  label,
  className,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  trigger: React.ReactElement<any>;
  children: React.ReactNode;
  align?: "start" | "end";
  width?: number | string;
  label?: string;
  className?: string;
}) {
  const anchor = useRef<HTMLElement | null>(null);
  const panel = useRef<HTMLDivElement | null>(null);
  const [pos, setPos] = useState<{ top: number; left: number; width: number } | null>(null);

  const place = useCallback(() => {
    if (!anchor.current) return;
    const a = anchor.current.getBoundingClientRect();
    const vw = window.innerWidth;
    const desired = typeof width === "number" ? width : 360;
    const w = Math.min(desired, vw - 16);
    let left = align === "start" ? a.left : a.right - w;
    left = Math.max(8, Math.min(left, vw - w - 8));
    setPos({ top: a.bottom + 6, left, width: w });
  }, [align, width]);

  useLayoutEffect(() => {
    if (open) place();
  }, [open, place]);

  useEffect(() => {
    if (!open) return;
    const onScroll = () => place();
    window.addEventListener("resize", onScroll);
    window.addEventListener("scroll", onScroll, true);
    return () => {
      window.removeEventListener("resize", onScroll);
      window.removeEventListener("scroll", onScroll, true);
    };
  }, [open, place]);

  const outsideRefs = useMemo(() => [anchor, panel], []);
  useClickOutside(outsideRefs, () => onOpenChange(false), open);
  useEscape(() => {
    onOpenChange(false);
    anchor.current?.focus();
  }, open);

  // focus first focusable inside panel on open
  useEffect(() => {
    if (!open || !panel.current) return;
    const el = panel.current.querySelector<HTMLElement>("input,select,button,textarea,[tabindex]:not([tabindex='-1'])");
    el?.focus();
  }, [open]);

  const trig = cloneElement(trigger, {
    ref: (el: HTMLElement | null) => {
      anchor.current = el;
    },
    "aria-expanded": open,
    "aria-haspopup": "dialog",
    onClick: (e: any) => {
      trigger.props.onClick?.(e);
      onOpenChange(!open);
    },
  });

  return (
    <>
      {trig}
      {open &&
        pos &&
        createPortal(
          <div
            ref={panel}
            role="dialog"
            aria-label={label}
            style={{ top: pos.top, left: pos.left, width: pos.width, maxHeight: `calc(100vh - ${pos.top + 12}px)` }}
            className={cn(
              "fixed z-[70] bg-surface border border-line rounded-md shadow-3 anim-pop overflow-auto",
              className
            )}
          >
            {children}
          </div>,
          document.body
        )}
    </>
  );
}

/* ------------------------------------------------------------------ Dialog */
export function Dialog({
  open,
  onClose,
  title,
  description,
  children,
  footer,
  size = "md",
  tone = "default",
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  description?: React.ReactNode;
  children?: React.ReactNode;
  footer?: React.ReactNode;
  size?: "sm" | "md" | "lg";
  tone?: "default" | "danger";
}) {
  const panel = useRef<HTMLDivElement | null>(null);
  const titleId = useId();
  const descId = useId();
  const lastActive = useRef<HTMLElement | null>(null);

  useEscape(onClose, open);

  useEffect(() => {
    if (!open) return;
    lastActive.current = document.activeElement as HTMLElement;
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    // focus first focusable or the panel
    requestAnimationFrame(() => {
      const el = panel.current?.querySelector<HTMLElement>(
        "[data-autofocus],input,select,textarea,button:not([data-close])"
      );
      (el ?? panel.current)?.focus();
    });
    const trap = (e: KeyboardEvent) => {
      if (e.key !== "Tab" || !panel.current) return;
      const f = Array.from(
        panel.current.querySelectorAll<HTMLElement>(
          "a[href],button:not([disabled]),input:not([disabled]),select:not([disabled]),textarea:not([disabled]),[tabindex]:not([tabindex='-1'])"
        )
      );
      if (!f.length) return;
      const first = f[0];
      const last = f[f.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", trap);
    return () => {
      document.removeEventListener("keydown", trap);
      document.body.style.overflow = prevOverflow;
      lastActive.current?.focus?.();
    };
  }, [open]);

  if (!open) return null;
  const w = { sm: "max-w-[420px]", md: "max-w-[560px]", lg: "max-w-[760px]" }[size];

  return createPortal(
    <div className="fixed inset-0 z-[90] flex items-end sm:items-center justify-center p-0 sm:p-6">
      <div className="absolute inset-0 bg-[var(--c-overlay)] anim-fade" onClick={onClose} aria-hidden />
      <div
        ref={panel}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={description ? descId : undefined}
        tabIndex={-1}
        className={cn(
          "relative w-full bg-surface border border-line shadow-3 rounded-t-lg sm:rounded-lg anim-slide-up flex flex-col max-h-[92vh]",
          w
        )}
      >
        <div className="flex items-start gap-3 px-5 pt-5 pb-3">
          {tone === "danger" && (
            <span className="shrink-0 size-9 rounded-full bg-danger-soft text-danger flex items-center justify-center">
              <AlertTriangle className="size-5" aria-hidden />
            </span>
          )}
          <div className="min-w-0 flex-1">
            <h2 id={titleId} className="text-lg font-semibold text-fg">
              {title}
            </h2>
            {description && (
              <p id={descId} className="text-sm text-fg-2 mt-1">
                {description}
              </p>
            )}
          </div>
          <Button variant="ghost" size="sm" square aria-label="Close" onClick={onClose} data-close icon={<X className="size-4" />} />
        </div>
        {children && <div className="px-5 py-2 overflow-y-auto">{children}</div>}
        {footer && (
          <div className="px-5 py-4 mt-2 border-t border-line flex flex-col-reverse sm:flex-row sm:justify-end gap-2">{footer}</div>
        )}
      </div>
    </div>,
    document.body
  );
}

/* ------------------------------------------------------------------- Toast */
type ToastTone = "success" | "error" | "info" | "warning";
interface ToastItem {
  id: number;
  title: string;
  description?: string;
  tone: ToastTone;
  action?: { label: string; onClick: () => void };
}
interface ToastCtx {
  toast: (t: Omit<ToastItem, "id">) => void;
}
const TCtx = createContext<ToastCtx | null>(null);

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);
  const timers = useRef(new Map<number, number>());

  const dismiss = useCallback((id: number) => {
    setItems((s) => s.filter((t) => t.id !== id));
    const tm = timers.current.get(id);
    if (tm) window.clearTimeout(tm);
    timers.current.delete(id);
  }, []);

  const toast = useCallback(
    (t: Omit<ToastItem, "id">) => {
      const id = Date.now() + Math.random();
      setItems((s) => [...s.slice(-3), { ...t, id }]);
      const tm = window.setTimeout(() => dismiss(id), t.tone === "error" ? 8000 : 5000);
      timers.current.set(id, tm);
    },
    [dismiss]
  );

  const value = useMemo(() => ({ toast }), [toast]);
  const Icon = { success: CheckCircle2, error: XCircle, info: Info, warning: AlertTriangle };
  const color = { success: "text-success", error: "text-danger", info: "text-primary-text", warning: "text-warning" };

  return (
    <TCtx.Provider value={value}>
      {children}
      {createPortal(
        <div
          className="fixed z-[100] bottom-4 left-4 right-4 sm:left-auto sm:right-6 sm:bottom-6 flex flex-col gap-2 sm:w-[380px] pointer-events-none"
          role="region"
          aria-label="Notifications"
        >
          {items.map((t) => {
            const I = Icon[t.tone];
            return (
              <div
                key={t.id}
                role={t.tone === "error" ? "alert" : "status"}
                className="pointer-events-auto flex items-start gap-3 p-3 pr-2 rounded-md bg-surface border border-line shadow-3 anim-slide-up"
              >
                <I className={cn("size-5 shrink-0 mt-0.5", color[t.tone])} aria-hidden />
                <div className="min-w-0 flex-1">
                  <p className="text-base font-medium text-fg">{t.title}</p>
                  {t.description && <p className="text-sm text-fg-2 mt-0.5 break-words">{t.description}</p>}
                  {t.action && (
                    <button
                      type="button"
                      className="mt-1.5 text-sm font-medium text-primary-text hover:underline"
                      onClick={() => {
                        t.action!.onClick();
                        dismiss(t.id);
                      }}
                    >
                      {t.action.label}
                    </button>
                  )}
                </div>
                <Button variant="ghost" size="sm" square aria-label="Dismiss" onClick={() => dismiss(t.id)} icon={<X className="size-4" />} />
              </div>
            );
          })}
        </div>,
        document.body
      )}
    </TCtx.Provider>
  );
}

export function useToast() {
  const v = useContext(TCtx);
  if (!v) throw new Error("useToast outside ToastProvider");
  return v;
}

/* -------------------------------------------------------------------- Menu */
export interface MenuItem {
  label: string;
  icon?: React.ReactNode;
  onSelect?: () => void;
  danger?: boolean;
  disabled?: boolean;
  separator?: boolean;
  shortcut?: string;
}

export function Menu({
  trigger,
  items,
  align = "end",
  label,
}: {
  trigger: React.ReactElement<any>;
  items: MenuItem[];
  align?: "start" | "end";
  label: string;
}) {
  const [open, setOpen] = useState(false);
  const listRef = useRef<HTMLDivElement>(null);

  const onKey = (e: React.KeyboardEvent) => {
    const btns = Array.from(listRef.current?.querySelectorAll<HTMLButtonElement>("button:not([disabled])") ?? []);
    const i = btns.indexOf(document.activeElement as HTMLButtonElement);
    if (e.key === "ArrowDown") {
      e.preventDefault();
      btns[(i + 1) % btns.length]?.focus();
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      btns[(i - 1 + btns.length) % btns.length]?.focus();
    } else if (e.key === "Home") {
      btns[0]?.focus();
    } else if (e.key === "End") {
      btns[btns.length - 1]?.focus();
    }
  };

  return (
    <Popover open={open} onOpenChange={setOpen} trigger={trigger} align={align} width={220} label={label} className="p-1">
      <div ref={listRef} role="menu" aria-label={label} onKeyDown={onKey}>
        {items.map((it, idx) =>
          it.separator ? (
            <div key={idx} role="separator" className="my-1 border-t border-line" />
          ) : (
            <button
              key={idx}
              role="menuitem"
              type="button"
              disabled={it.disabled}
              onClick={() => {
                it.onSelect?.();
                setOpen(false);
              }}
              className={cn(
                "w-full flex items-center gap-2.5 h-9 px-2.5 rounded-xs text-base text-left transition-colors",
                it.danger ? "text-danger hover:bg-danger-soft" : "text-fg hover:bg-surface-2",
                it.disabled && "opacity-50 cursor-not-allowed"
              )}
            >
              {it.icon && <span className="text-fg-3 [&>svg]:size-4">{it.icon}</span>}
              <span className="flex-1 truncate">{it.label}</span>
              {it.shortcut && <kbd className="text-2xs text-fg-3 font-sans">{it.shortcut}</kbd>}
            </button>
          )
        )}
      </div>
    </Popover>
  );
}
