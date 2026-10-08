import { forwardRef, useId } from "react";
import { ChevronDown, Loader2, AlertCircle } from "lucide-react";
import { cn } from "@/utils/cn";

/* ------------------------------------------------------------------ Button
   Variants: primary (one per view) · secondary · ghost · danger · danger-outline · link */
type Variant = "primary" | "secondary" | "ghost" | "danger" | "danger-outline" | "link";
type Size = "sm" | "md" | "lg";

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  loading?: boolean;
  icon?: React.ReactNode;
  iconRight?: React.ReactNode;
  /** icon-only buttons must still provide aria-label */
  square?: boolean;
}

const variantCls: Record<Variant, string> = {
  primary:
    "bg-primary text-white hover:bg-primary-hover border border-transparent shadow-1 dark:text-fg-inverse",
  secondary:
    "bg-surface text-fg border border-line-strong hover:bg-surface-2 shadow-1",
  ghost: "bg-transparent text-fg-2 hover:bg-surface-3 hover:text-fg border border-transparent",
  danger: "bg-danger text-white hover:bg-danger-hover border border-transparent dark:text-fg-inverse",
  "danger-outline":
    "bg-surface text-danger border border-line-strong hover:bg-danger-soft hover:border-danger",
  link: "bg-transparent text-primary-text underline-offset-2 hover:underline border border-transparent px-0",
};

const sizeCls: Record<Size, string> = {
  sm: "h-8 px-3 text-sm gap-1.5 rounded-sm",
  md: "h-9 px-3.5 text-base gap-2 rounded-sm",
  lg: "h-11 px-4 text-base gap-2 rounded-md",
};
const squareCls: Record<Size, string> = { sm: "w-8 px-0", md: "w-9 px-0", lg: "w-11 px-0" };

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = "secondary", size = "md", loading, icon, iconRight, square, className, children, disabled, type = "button", ...rest },
  ref
) {
  return (
    <button
      ref={ref}
      type={type}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      className={cn(
        "inline-flex items-center justify-center font-medium whitespace-nowrap select-none",
        "transition-colors duration-[var(--dur-fast)] disabled:opacity-50 disabled:cursor-not-allowed",
        variantCls[variant],
        sizeCls[size],
        square && squareCls[size],
        className
      )}
      {...rest}
    >
      {loading ? <Loader2 className="size-4 animate-spin" aria-hidden /> : icon}
      {children}
      {iconRight}
    </button>
  );
});

/* ------------------------------------------------------------------- Badge */
export function Badge({
  children,
  tone = "neutral",
  className,
}: {
  children: React.ReactNode;
  tone?: "neutral" | "info" | "success" | "warning" | "danger" | "brand";
  className?: string;
}) {
  const tones = {
    neutral: "bg-surface-3 text-fg-2",
    info: "bg-primary-soft text-primary-text",
    success: "bg-success-soft text-success",
    warning: "bg-warning-bg text-warning",
    danger: "bg-danger-soft text-danger",
    brand: "bg-brand-soft text-brand",
  };
  return (
    <span
      className={cn(
        "inline-flex items-center h-5 px-1.5 rounded-xs text-2xs font-medium leading-none whitespace-nowrap",
        tones[tone],
        className
      )}
    >
      {children}
    </span>
  );
}

/* -------------------------------------------------------------------- Field */
export interface FieldProps {
  label: React.ReactNode;
  htmlFor?: string;
  hint?: React.ReactNode;
  error?: string;
  required?: boolean;
  optional?: boolean;
  children: React.ReactNode;
  className?: string;
  /** render label on the side for dense horizontal layouts */
  labelAside?: React.ReactNode;
}

/** Field: visible label + hint + error wired with aria-describedby by the input itself */
export function Field({ label, htmlFor, hint, error, required, optional, children, className, labelAside }: FieldProps) {
  return (
    <div className={cn("flex flex-col gap-1.5 min-w-0", className)}>
      <div className="flex items-center justify-between gap-2">
        <label htmlFor={htmlFor} className="text-sm font-medium text-fg leading-5">
          {label}
          {required && (
            <span className="text-danger ml-0.5" aria-hidden>
              *
            </span>
          )}
          {optional && <span className="text-fg-3 font-normal ml-1">(optional)</span>}
        </label>
        {labelAside}
      </div>
      {children}
      {error ? (
        <p id={htmlFor ? `${htmlFor}-error` : undefined} className="text-xs text-danger flex items-start gap-1" role="alert">
          <AlertCircle className="size-3.5 mt-0.5 shrink-0" aria-hidden />
          <span>{error}</span>
        </p>
      ) : hint ? (
        <p id={htmlFor ? `${htmlFor}-hint` : undefined} className="text-xs text-fg-3">
          {hint}
        </p>
      ) : null}
    </div>
  );
}

/* -------------------------------------------------------------------- Input */
const controlBase =
  "w-full min-w-0 h-9 px-3 text-base bg-surface text-fg border rounded-sm placeholder:text-fg-3 " +
  "transition-colors duration-[var(--dur-fast)] hover:border-line-strong " +
  "focus-visible:outline-none focus-visible:border-primary focus-visible:ring-2 focus-visible:ring-primary/30 " +
  "disabled:bg-surface-2 disabled:text-fg-3 disabled:cursor-not-allowed read-only:bg-surface-2";

export interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  invalid?: boolean;
  leading?: React.ReactNode;
  trailing?: React.ReactNode;
  mono?: boolean;
}

export const Input = forwardRef<HTMLInputElement, InputProps>(function Input(
  { invalid, leading, trailing, className, mono, id, ...rest },
  ref
) {
  const describedBy = [rest["aria-describedby"], invalid && id ? `${id}-error` : id ? `${id}-hint` : null]
    .filter(Boolean)
    .join(" ") || undefined;
  return (
    <div className={cn("relative flex items-center min-w-0", className)}>
      {leading && (
        <span className="absolute left-3 text-fg-3 pointer-events-none flex items-center" aria-hidden>
          {leading}
        </span>
      )}
      <input
        ref={ref}
        id={id}
        aria-invalid={invalid || undefined}
        aria-describedby={describedBy}
        className={cn(
          controlBase,
          leading && "pl-9",
          trailing && "pr-9",
          mono && "font-mono text-sm",
          invalid ? "border-danger focus-visible:border-danger focus-visible:ring-danger/25" : "border-line"
        )}
        {...rest}
      />
      {trailing && <span className="absolute right-2 flex items-center">{trailing}</span>}
    </div>
  );
});

export interface TextareaProps extends React.TextareaHTMLAttributes<HTMLTextAreaElement> {
  invalid?: boolean;
}
export const Textarea = forwardRef<HTMLTextAreaElement, TextareaProps>(function Textarea(
  { invalid, className, id, ...rest },
  ref
) {
  return (
    <textarea
      ref={ref}
      id={id}
      aria-invalid={invalid || undefined}
      aria-describedby={invalid && id ? `${id}-error` : id ? `${id}-hint` : undefined}
      className={cn(controlBase, "h-auto min-h-[88px] py-2 resize-y", invalid ? "border-danger" : "border-line", className)}
      {...rest}
    />
  );
});

/* ------------------------------------------------------------------- Select */
export interface SelectProps extends React.SelectHTMLAttributes<HTMLSelectElement> {
  invalid?: boolean;
  options: { value: string; label: string; disabled?: boolean }[];
  placeholder?: string;
}
export const Select = forwardRef<HTMLSelectElement, SelectProps>(function Select(
  { invalid, options, placeholder, className, id, ...rest },
  ref
) {
  return (
    <div className={cn("relative min-w-0", className)}>
      <select
        ref={ref}
        id={id}
        aria-invalid={invalid || undefined}
        aria-describedby={invalid && id ? `${id}-error` : id ? `${id}-hint` : undefined}
        className={cn(controlBase, "appearance-none pr-9 cursor-pointer", invalid ? "border-danger" : "border-line")}
        {...rest}
      >
        {placeholder && (
          <option value="" disabled>
            {placeholder}
          </option>
        )}
        {options.map((o) => (
          <option key={o.value} value={o.value} disabled={o.disabled}>
            {o.label}
          </option>
        ))}
      </select>
      <ChevronDown className="size-4 text-fg-3 absolute right-3 top-1/2 -translate-y-1/2 pointer-events-none" aria-hidden />
    </div>
  );
});

/* ------------------------------------------------------------------- Toggle */
export function Toggle({
  checked,
  onChange,
  label,
  description,
  disabled,
  id,
  size = "md",
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  label?: React.ReactNode;
  description?: React.ReactNode;
  disabled?: boolean;
  id?: string;
  size?: "sm" | "md";
}) {
  const auto = useId();
  const sid = id ?? auto;
  const dim = size === "sm" ? "w-9 h-5" : "w-11 h-6";
  const knob = size === "sm" ? "size-4 translate-x-0.5" : "size-5 translate-x-0.5";
  const on = size === "sm" ? "translate-x-[18px]" : "translate-x-[22px]";
  return (
    <div className="flex items-start gap-3 min-w-0">
      <button
        id={sid}
        type="button"
        role="switch"
        aria-checked={checked}
        aria-labelledby={label ? `${sid}-label` : undefined}
        aria-describedby={description ? `${sid}-desc` : undefined}
        disabled={disabled}
        onClick={() => onChange(!checked)}
        className={cn(
          "relative shrink-0 rounded-full transition-colors duration-[var(--dur-base)] mt-0.5",
          dim,
          checked ? "bg-success" : "bg-line-strong",
          disabled && "opacity-50 cursor-not-allowed"
        )}
      >
        <span
          aria-hidden
          className={cn(
            "absolute top-0.5 left-0 rounded-full bg-white shadow-1 transition-transform duration-[var(--dur-base)]",
            knob,
            checked && on
          )}
        />
      </button>
      {(label || description) && (
        <span className="min-w-0 flex flex-col">
          {label && (
            <label id={`${sid}-label`} htmlFor={sid} className="text-base font-medium text-fg cursor-pointer leading-6">
              {label}
            </label>
          )}
          {description && (
            <span id={`${sid}-desc`} className="text-sm text-fg-3">
              {description}
            </span>
          )}
        </span>
      )}
    </div>
  );
}

/* ----------------------------------------------------------------- Checkbox */
export function Checkbox({
  checked,
  indeterminate,
  onChange,
  label,
  ariaLabel,
  id,
  disabled,
}: {
  checked: boolean;
  indeterminate?: boolean;
  onChange: (v: boolean) => void;
  label?: React.ReactNode;
  ariaLabel?: string;
  id?: string;
  disabled?: boolean;
}) {
  const auto = useId();
  const cid = id ?? auto;
  return (
    <label htmlFor={cid} className={cn("inline-flex items-center gap-2 cursor-pointer select-none", disabled && "opacity-50 cursor-not-allowed")}>
      {/* 24px hit target wrapper around a 16px box */}
      <span className="relative inline-flex items-center justify-center size-6 shrink-0">
        <input
          id={cid}
          type="checkbox"
          aria-label={ariaLabel}
          checked={checked}
          disabled={disabled}
          ref={(el) => {
            if (el) el.indeterminate = !!indeterminate;
          }}
          onChange={(e) => onChange(e.target.checked)}
          className="peer appearance-none size-4 rounded-xs border border-line-strong bg-surface checked:bg-primary checked:border-primary indeterminate:bg-primary indeterminate:border-primary transition-colors cursor-pointer disabled:cursor-not-allowed"
        />
        <svg
          aria-hidden
          viewBox="0 0 16 16"
          className="absolute size-4 pointer-events-none text-white opacity-0 peer-checked:opacity-100 peer-indeterminate:opacity-100"
        >
          {indeterminate ? (
            <path d="M4 8h8" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
          ) : (
            <path d="M3.5 8.5l3 3 6-6" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
          )}
        </svg>
      </span>
      {label && <span className="text-base text-fg">{label}</span>}
    </label>
  );
}

/* --------------------------------------------------------------- RadioCard */
export function RadioCards<T extends string>({
  name,
  value,
  onChange,
  options,
  columns = 2,
}: {
  name: string;
  value: T;
  onChange: (v: T) => void;
  options: { value: T; label: string; description?: string; icon?: React.ReactNode; badge?: React.ReactNode }[];
  columns?: 1 | 2 | 3;
}) {
  const col = { 1: "grid-cols-1", 2: "grid-cols-1 sm:grid-cols-2", 3: "grid-cols-1 sm:grid-cols-2 lg:grid-cols-3" }[columns];
  return (
    <div role="radiogroup" className={cn("grid gap-3", col)}>
      {options.map((o) => {
        const active = o.value === value;
        return (
          <label
            key={o.value}
            className={cn(
              "relative flex gap-3 p-3 rounded-md border cursor-pointer transition-colors min-w-0",
              "has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-primary has-[:focus-visible]:outline-offset-2",
              active ? "border-primary bg-primary-soft/60" : "border-line hover:border-line-strong bg-surface"
            )}
          >
            <input
              type="radio"
              name={name}
              value={o.value}
              checked={active}
              onChange={() => onChange(o.value)}
              className="sr-only"
            />
            <span
              aria-hidden
              className={cn(
                "mt-1 size-4 shrink-0 rounded-full border-2 flex items-center justify-center",
                active ? "border-primary" : "border-line-strong"
              )}
            >
              {active && <span className="size-2 rounded-full bg-primary" />}
            </span>
            <span className="min-w-0 flex-1">
              <span className="flex items-center gap-2 text-base font-medium text-fg">
                {o.icon}
                <span className="truncate">{o.label}</span>
                {o.badge}
              </span>
              {o.description && <span className="block text-sm text-fg-3 mt-0.5">{o.description}</span>}
            </span>
          </label>
        );
      })}
    </div>
  );
}

/* --------------------------------------------------------- Segmented ctrl */
export function Segmented<T extends string>({
  value,
  onChange,
  options,
  ariaLabel,
  size = "md",
}: {
  value: T;
  onChange: (v: T) => void;
  options: { value: T; label: React.ReactNode; title?: string }[];
  ariaLabel: string;
  size?: "sm" | "md";
}) {
  return (
    <div role="radiogroup" aria-label={ariaLabel} className="inline-flex p-0.5 rounded-sm bg-surface-3 border border-line gap-0.5 max-w-full overflow-x-auto">
      {options.map((o) => {
        const active = o.value === value;
        return (
          <button
            key={o.value}
            type="button"
            role="radio"
            aria-checked={active}
            title={o.title}
            onClick={() => onChange(o.value)}
            className={cn(
              "inline-flex items-center justify-center gap-1.5 rounded-xs font-medium whitespace-nowrap transition-colors",
              size === "sm" ? "h-7 px-2 text-xs min-w-7" : "h-8 px-3 text-sm min-w-8",
              active ? "bg-surface text-fg shadow-1" : "text-fg-2 hover:text-fg"
            )}
          >
            {o.label}
          </button>
        );
      })}
    </div>
  );
}

/* ------------------------------------------------------------------- Divider */
export function Divider({ className }: { className?: string }) {
  return <hr className={cn("border-0 border-t border-line", className)} />;
}
