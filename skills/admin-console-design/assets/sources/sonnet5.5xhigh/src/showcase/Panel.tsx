import type { ReactNode } from "react";
import { cn } from "@/utils/cn";

/**
 * 可收起的侧边面板：
 * - 宽屏（inflow）：占位式，宽度平滑过渡到 0，收起后 inert（不可聚焦）
 * - 窄屏：覆盖式抽屉 + 遮罩，Esc / 点击遮罩关闭
 * 父容器需要 position: relative
 */
export function Panel({
  open,
  onClose,
  inflow,
  width = 320,
  label,
  children,
}: {
  open: boolean;
  onClose: () => void;
  inflow: boolean;
  width?: number;
  label: string;
  children: ReactNode;
}) {
  if (inflow) {
    return (
      <aside
        aria-label={label}
        inert={!open}
        className="flex-none overflow-hidden bg-surface transition-[width] duration-200 ease-out"
        style={{ width: open ? width : 0, borderRight: open ? "1px solid var(--border)" : "0" }}
      >
        <div style={{ width }} className="h-full overflow-y-auto">
          {children}
        </div>
      </aside>
    );
  }
  return (
    <>
      {open && <button type="button" tabIndex={-1} aria-label="关闭面板" className="absolute inset-0 z-20 cursor-default border-0 bg-scrim" onClick={onClose} />}
      <aside
        aria-label={label}
        inert={!open}
        onKeyDown={(e) => e.key === "Escape" && onClose()}
        className={cn(
          "absolute inset-y-0 left-0 z-30 overflow-y-auto border-r border-line bg-surface shadow-lg transition-transform duration-200 ease-out",
          open ? "translate-x-0" : "-translate-x-full",
        )}
        style={{ width: `min(${width}px, calc(100% - 48px))` }}
      >
        {children}
      </aside>
    </>
  );
}
