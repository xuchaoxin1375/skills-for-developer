import { createContext, useCallback, useContext, useMemo, useRef, useState, type ReactNode } from "react";
import { CircleAlert, CircleCheck, Info, X } from "lucide-react";

interface ToastInput {
  title: string;
  tone?: "ok" | "info" | "danger";
  action?: { label: string; run: () => void };
}
interface ToastItem extends ToastInput {
  id: number;
}

const Ctx = createContext<{ push: (t: ToastInput) => void }>({ push: () => {} });
export const useToast = () => useContext(Ctx);

/** 常驻 aria-live 区域：保证屏幕阅读器能播报新通知；带"撤销"的通知停留更久 */
export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);
  const idRef = useRef(0);

  const dismiss = useCallback((id: number) => setItems((l) => l.filter((t) => t.id !== id)), []);
  const push = useCallback(
    (t: ToastInput) => {
      const id = ++idRef.current;
      setItems((l) => [...l.slice(-2), { ...t, id }]);
      window.setTimeout(() => dismiss(id), t.action ? 8000 : 5000);
    },
    [dismiss],
  );
  const value = useMemo(() => ({ push }), [push]);

  return (
    <Ctx.Provider value={value}>
      {children}
      <div className="toasts" role="region" aria-label="Notifications" aria-live="polite">
        {items.map((t) => {
          const Icon = t.tone === "danger" ? CircleAlert : t.tone === "info" ? Info : CircleCheck;
          return (
            <div key={t.id} className="toast">
              <Icon
                size={16}
                aria-hidden="true"
                className={t.tone === "danger" ? "mt-1 flex-none text-danger" : t.tone === "info" ? "mt-1 flex-none text-link" : "mt-1 flex-none text-ok"}
              />
              <p className="min-w-0 flex-1 break-words font-medium">{t.title}</p>
              {t.action && (
                <button
                  type="button"
                  className="link flex-none font-semibold"
                  onClick={() => {
                    t.action?.run();
                    dismiss(t.id);
                  }}
                >
                  {t.action.label}
                </button>
              )}
              <button type="button" aria-label="Dismiss notification" className="btn btn-ghost btn-icon -my-1" onClick={() => dismiss(t.id)}>
                <X size={16} aria-hidden="true" />
              </button>
            </div>
          );
        })}
      </div>
    </Ctx.Provider>
  );
}
