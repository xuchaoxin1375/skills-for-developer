import { useEffect, useRef, useState, type ReactNode } from "react";
import { cn } from "@/utils/cn";

/**
 * 基于原生 <dialog> 的模态层：
 * - 免费获得：焦点陷阱、Esc 关闭、背景 inert、关闭后焦点回到触发元素
 * - 带进入 / 退出动画（尊重 prefers-reduced-motion）
 * - 带 data-autofocus 的元素在打开时获得初始焦点（破坏性确认默认聚焦"取消"）
 */
export function Modal({
  open,
  onClose,
  label,
  kind = "dialog",
  className,
  children,
}: {
  open: boolean;
  onClose: () => void;
  label: string;
  kind?: "dialog" | "palette" | "drawer";
  className?: string;
  children: ReactNode;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const downOnBackdrop = useRef(false);
  const openRef = useRef(open);
  openRef.current = open;
  const [render, setRender] = useState(open);

  useEffect(() => {
    if (open) {
      setRender(true);
      return;
    }
    const t = window.setTimeout(() => setRender(false), 170);
    return () => window.clearTimeout(t);
  }, [open]);

  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    if (render && open) {
      delete d.dataset.closing;
      if (!d.open) {
        d.showModal();
        d.querySelector<HTMLElement>("[data-autofocus]")?.focus();
      }
    } else if (render && !open) {
      if (d.open) d.dataset.closing = "1";
    } else if (!render && d.open) {
      d.close();
      delete d.dataset.closing;
    }
  }, [render, open]);

  return (
    <dialog
      ref={ref}
      className={cn("modal", className)}
      data-kind={kind}
      aria-label={label}
      onCancel={(e) => {
        e.preventDefault();
        onClose();
      }}
      // 浏览器可能绕过 cancel 直接关闭（如连续按 Esc）：同步父级状态，避免"状态仍为打开"
      onClose={() => {
        if (openRef.current) onClose();
      }}
      onPointerDown={(e) => {
        downOnBackdrop.current = e.target === ref.current;
      }}
      onClick={(e) => {
        if (downOnBackdrop.current && e.target === ref.current) onClose();
      }}
    >
      {render ? children : null}
    </dialog>
  );
}

export function ConfirmDialog({
  open,
  title,
  children,
  confirmLabel = "Confirm",
  cancelLabel = "Cancel",
  danger,
  onConfirm,
  onCancel,
}: {
  open: boolean;
  title: string;
  children: ReactNode;
  confirmLabel?: string;
  cancelLabel?: string;
  danger?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  return (
    <Modal open={open} onClose={onCancel} label={title}>
      <div className="p-6">
        <h2 className="text-xl font-semibold">{title}</h2>
        <div className="mt-3 text-muted">{children}</div>
      </div>
      <div className="flex flex-wrap justify-end gap-3 border-t border-line px-6 py-4">
        <button type="button" className="btn" data-autofocus onClick={onCancel}>
          {cancelLabel}
        </button>
        <button type="button" className={cn("btn", danger ? "btn-danger" : "btn-primary")} onClick={onConfirm}>
          {confirmLabel}
        </button>
      </div>
    </Modal>
  );
}
