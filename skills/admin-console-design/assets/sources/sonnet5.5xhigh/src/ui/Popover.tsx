import {
  useCallback,
  useEffect,
  useId,
  useLayoutEffect,
  useRef,
  useState,
  type CSSProperties,
  type ReactNode,
  type RefObject,
} from "react";

export interface TriggerProps {
  ref: RefObject<HTMLButtonElement | null>;
  onClick: () => void;
  "aria-expanded": boolean;
  "aria-haspopup": "dialog";
  "aria-controls": string | undefined;
}

/**
 * 非模态浮层（筛选、显示选项、账户菜单）：
 * - Esc 关闭并把焦点还给触发按钮；点击外部 / Tab 离开自动关闭
 * - 打开后焦点移入第一个可操作控件
 * - 自动夹取到视口内，避免窄窗口下溢出；< 640px 时变为底部面板
 */
export function Popover({
  label,
  renderTrigger,
  children,
  align = "left",
  width = 320,
  onOpenChange,
}: {
  label: string;
  renderTrigger: (p: TriggerProps) => ReactNode;
  children: ReactNode | ((api: { close: () => void }) => ReactNode);
  align?: "left" | "right";
  width?: number;
  onOpenChange?: (open: boolean) => void;
}) {
  const [open, setOpenState] = useState(false);
  const id = useId();
  const wrap = useRef<HTMLDivElement>(null);
  const btn = useRef<HTMLButtonElement>(null);
  const panel = useRef<HTMLDivElement>(null);

  const setOpen = useCallback(
    (v: boolean) => {
      setOpenState(v);
      onOpenChange?.(v);
    },
    [onOpenChange],
  );
  const close = useCallback(() => {
    setOpen(false);
    btn.current?.focus();
  }, [setOpen]);

  useEffect(() => {
    if (!open) return;
    const onDown = (e: PointerEvent) => {
      if (!wrap.current?.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.stopPropagation();
        close();
      }
    };
    document.addEventListener("pointerdown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("pointerdown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open, close, setOpen]);

  useEffect(() => {
    if (!open) return;
    // 焦点优先级：显式标记 > 第一个表单控件 > 第一个可操作元素（避免落在“关闭”按钮上）
    const p = panel.current;
    const f =
      p?.querySelector<HTMLElement>("[data-autofocus]") ??
      p?.querySelector<HTMLElement>('input:not([type="hidden"]),select,textarea') ??
      p?.querySelector<HTMLElement>('button,[href],[tabindex]:not([tabindex="-1"])');
    (f ?? p)?.focus();
  }, [open]);

  useLayoutEffect(() => {
    if (!open) return;
    const clamp = () => {
      const el = panel.current;
      if (!el) return;
      el.style.translate = "0px 0px";
      if (window.matchMedia("(max-width: 639px)").matches) return;
      const r = el.getBoundingClientRect();
      const vw = document.documentElement.clientWidth;
      let dx = 0;
      if (r.right > vw - 8) dx = vw - 8 - r.right;
      if (r.left + dx < 8) dx = 8 - r.left;
      el.style.translate = `${dx}px 0px`;
    };
    clamp();
    window.addEventListener("resize", clamp);
    return () => window.removeEventListener("resize", clamp);
  }, [open]);

  return (
    <div ref={wrap} className="relative inline-flex max-w-full">
      {renderTrigger({
        ref: btn,
        onClick: () => setOpen(!open),
        "aria-expanded": open,
        "aria-haspopup": "dialog",
        "aria-controls": open ? id : undefined,
      })}
      {open && (
        <div
          ref={panel}
          id={id}
          role="dialog"
          aria-label={label}
          tabIndex={-1}
          className="pop"
          data-align={align}
          style={{ "--pop-w": `${width}px` } as CSSProperties}
          onBlur={(e) => {
            const next = e.relatedTarget as Node | null;
            if (next && !wrap.current?.contains(next)) setOpen(false);
          }}
        >
          {typeof children === "function" ? children({ close }) : children}
        </div>
      )}
    </div>
  );
}
