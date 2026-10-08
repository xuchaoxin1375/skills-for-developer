import {
  useEffect,
  useId,
  useRef,
  useState,
  type ReactNode,
  type SelectHTMLAttributes,
} from "react";
import { createPortal } from "react-dom";
import { ChevronsUpDown, CircleAlert, Info, LoaderCircle } from "lucide-react";
import { Link } from "@/lib/route";
import { cn } from "@/utils/cn";

export interface FieldControlProps {
  id: string;
  "aria-describedby"?: string;
  "aria-invalid"?: true;
  "aria-required"?: true;
}

/**
 * 表单字段：可见标签 + 辅助说明 + 行内错误
 * 通过 render-prop 把 id / aria-* 注入控件，保证标签、提示、错误与控件的语义关联。
 */
export function Field({
  label,
  hint,
  error,
  required,
  optional,
  className,
  name,
  children,
}: {
  label: ReactNode;
  hint?: ReactNode;
  error?: string;
  required?: boolean;
  optional?: boolean;
  className?: string;
  name?: string;
  children: (p: FieldControlProps) => ReactNode;
}) {
  const id = useId();
  const hintId = `${id}-hint`;
  const errId = `${id}-err`;
  const describedBy = [hint ? hintId : "", error ? errId : ""].filter(Boolean).join(" ") || undefined;
  return (
    <div className={cn("field", className)} data-field={name}>
      <label htmlFor={id} className="label">
        {label}
        {required && (
          <span aria-hidden="true" className="ml-1 text-danger">
            *
          </span>
        )}
        {optional && <span className="ml-2 font-normal text-muted">Optional</span>}
      </label>
      {children({
        id,
        "aria-describedby": describedBy,
        "aria-invalid": error ? true : undefined,
        "aria-required": required ? true : undefined,
      })}
      {hint && (
        <p id={hintId} className="hint">
          {hint}
        </p>
      )}
      {error && (
        <p id={errId} className="error-text" role="alert">
          <CircleAlert size={14} aria-hidden="true" />
          <span>{error}</span>
        </p>
      )}
    </div>
  );
}

export function Select({ className, children, ...props }: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <div className="relative min-w-0">
      <select {...props} className={cn("select", className)}>
        {children}
      </select>
      <ChevronsUpDown
        size={16}
        aria-hidden="true"
        className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-muted"
      />
    </div>
  );
}

export function Switch({
  checked,
  onChange,
  disabled,
  ...aria
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  disabled?: boolean;
  id?: string;
  "aria-label"?: string;
  "aria-labelledby"?: string;
  "aria-describedby"?: string;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      disabled={disabled}
      className="switch"
      onClick={() => onChange(!checked)}
      {...aria}
    />
  );
}

export function Spinner({ size = 16 }: { size?: number }) {
  return <LoaderCircle size={size} className="spin" aria-hidden="true" />;
}

/** 悬停 + 聚焦都可触发的说明提示（不只依赖 hover），Esc 可关闭 */
export function InfoTip({ text }: { text: string }) {
  const id = useId();
  const ref = useRef<HTMLButtonElement>(null);
  const [pos, setPos] = useState<{ x: number; y: number } | null>(null);

  const show = () => {
    const r = ref.current?.getBoundingClientRect();
    if (r) setPos({ x: r.left + r.width / 2, y: r.bottom + 8 });
  };
  const hide = () => setPos(null);

  useEffect(() => {
    if (!pos) return;
    const k = (e: KeyboardEvent) => e.key === "Escape" && hide();
    window.addEventListener("keydown", k);
    window.addEventListener("scroll", hide, true);
    return () => {
      window.removeEventListener("keydown", k);
      window.removeEventListener("scroll", hide, true);
    };
  }, [pos]);

  const vw = typeof window === "undefined" ? 1024 : document.documentElement.clientWidth;
  return (
    <>
      <button
        ref={ref}
        type="button"
        aria-label="More information"
        aria-describedby={pos ? id : undefined}
        className="inline-flex size-6 flex-none items-center justify-center rounded-full border-0 bg-transparent text-muted hover:text-fg"
        onMouseEnter={show}
        onMouseLeave={hide}
        onFocus={show}
        onBlur={hide}
      >
        <Info size={14} aria-hidden="true" />
      </button>
      {pos &&
        // 通过 portal 渲染到 body：容器查询的 layout containment 会改变 fixed 的包含块
        createPortal(
          <span
            role="tooltip"
            id={id}
            className="tip"
            style={{ left: Math.min(Math.max(pos.x, 148), Math.max(vw - 148, 148)), top: pos.y, transform: "translateX(-50%)" }}
          >
            {text}
          </span>,
          document.body,
        )}
    </>
  );
}

export function Breadcrumbs({ items }: { items: { label: string; to?: string }[] }) {
  return (
    <nav aria-label="Breadcrumb" className="mb-3">
      <ol className="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm text-muted">
        {items.map((it, i) => (
          <li key={it.label} className="flex items-center gap-2">
            {it.to ? (
              <Link to={it.to} className="link text-muted hover:text-fg">
                {it.label}
              </Link>
            ) : (
              <span aria-current="page" className="font-medium text-fg">
                {it.label}
              </span>
            )}
            {i < items.length - 1 && <span aria-hidden="true">/</span>}
          </li>
        ))}
      </ol>
    </nav>
  );
}

export function PageHeader({
  title,
  description,
  actions,
}: {
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <div className="page-head">
      <div className="min-w-0 flex-1 basis-80">
        <h1 className="break-words text-xl font-semibold sm:text-2xl">{title}</h1>
        {description && <p className="mt-2 text-muted">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-3">{actions}</div>}
    </div>
  );
}
