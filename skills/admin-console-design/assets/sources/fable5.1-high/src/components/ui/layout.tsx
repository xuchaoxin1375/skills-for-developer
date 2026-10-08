import { useState } from "react";
import { AlertTriangle, CheckCircle2, ChevronDown, Info, XCircle, HelpCircle, X } from "lucide-react";
import { cn } from "@/utils/cn";
import { Tooltip } from "./overlays";
import { Button } from "./primitives";

/* -------------------------------------------------------------------- Card */
export function Card({
  children,
  className,
  as: Tag = "section",
  ...rest
}: React.HTMLAttributes<HTMLElement> & { as?: "section" | "div" | "article" | "form" }) {
  return (
    <Tag className={cn("bg-surface border border-line rounded-md shadow-1 min-w-0", className)} {...rest}>
      {children}
    </Tag>
  );
}

export function CardHeader({
  title,
  description,
  actions,
  className,
  titleAs: TitleTag = "h2",
}: {
  title: React.ReactNode;
  description?: React.ReactNode;
  actions?: React.ReactNode;
  className?: string;
  titleAs?: "h2" | "h3";
}) {
  return (
    <div className={cn("flex flex-wrap items-start justify-between gap-3 px-4 sm:px-5 py-4", className)}>
      <div className="min-w-0 flex-1">
        <TitleTag className="text-lg font-semibold text-fg">{title}</TitleTag>
        {description && <p className="text-sm text-fg-2 mt-0.5">{description}</p>}
      </div>
      {actions && <div className="flex items-center gap-2 shrink-0">{actions}</div>}
    </div>
  );
}

export function CardBody({ children, className }: { children: React.ReactNode; className?: string }) {
  return <div className={cn("px-4 sm:px-5 py-4", className)}>{children}</div>;
}

/** Settings-card footer: Cloudflare puts helper text left and Save right. */
export function CardFooter({ children, className, note }: { children?: React.ReactNode; className?: string; note?: React.ReactNode }) {
  return (
    <div
      className={cn(
        "flex flex-col-reverse sm:flex-row sm:items-center sm:justify-between gap-3 px-4 sm:px-5 py-3 border-t border-line bg-surface-2/60 rounded-b-md",
        className
      )}
    >
      <div className="text-sm text-fg-3 min-w-0">{note}</div>
      <div className="flex items-center gap-2 justify-end shrink-0">{children}</div>
    </div>
  );
}

/** Collapsible card, e.g. "Recommendations" */
export function CollapsibleCard({
  title,
  meta,
  children,
  defaultOpen = true,
  className,
}: {
  title: React.ReactNode;
  meta?: React.ReactNode;
  children: React.ReactNode;
  defaultOpen?: boolean;
  className?: string;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <Card className={className}>
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
        className={cn(
          "w-full flex items-center justify-between gap-3 px-4 sm:px-5 h-12 text-left hover:bg-surface-2 transition-colors rounded-md",
          open && "rounded-b-none border-b border-line"
        )}
      >
        <span className="flex items-center gap-2 min-w-0">
          <span className="text-base font-medium text-fg truncate">{title}</span>
          {meta}
        </span>
        <ChevronDown className={cn("size-4 text-fg-3 transition-transform duration-[var(--dur-base)]", open && "rotate-180")} aria-hidden />
      </button>
      <div
        className={cn("grid transition-[grid-template-rows] duration-[var(--dur-base)] ease-[var(--ease-out)]", open ? "grid-rows-[1fr]" : "grid-rows-[0fr]")}
      >
        <div className="overflow-hidden">{children}</div>
      </div>
    </Card>
  );
}

/* ------------------------------------------------------------------- Alert */
export function Alert({
  tone = "info",
  children,
  title,
  onDismiss,
  className,
  actions,
}: {
  tone?: "info" | "warning" | "success" | "danger";
  children: React.ReactNode;
  title?: React.ReactNode;
  onDismiss?: () => void;
  className?: string;
  actions?: React.ReactNode;
}) {
  const map = {
    info: { Icon: Info, cls: "bg-info-bg border-info-border text-fg", icon: "text-primary-text" },
    warning: { Icon: AlertTriangle, cls: "bg-warning-bg border-warning-border text-fg", icon: "text-warning" },
    success: { Icon: CheckCircle2, cls: "bg-success-soft border-success/30 text-fg", icon: "text-success" },
    danger: { Icon: XCircle, cls: "bg-danger-soft border-danger/30 text-fg", icon: "text-danger" },
  }[tone];
  return (
    <div role={tone === "danger" ? "alert" : "status"} className={cn("flex gap-3 border rounded-md px-4 py-3 text-base", map.cls, className)}>
      <map.Icon className={cn("size-5 shrink-0 mt-0.5", map.icon)} aria-hidden />
      <div className="min-w-0 flex-1">
        {title && <p className="font-medium">{title}</p>}
        <div className={cn("text-fg-2 [&_a]:text-fg [&_a]:underline [&_a]:underline-offset-2", title && "mt-0.5")}>{children}</div>
        {actions && <div className="mt-2 flex flex-wrap gap-2">{actions}</div>}
      </div>
      {onDismiss && <Button variant="ghost" size="sm" square aria-label="Dismiss" onClick={onDismiss} icon={<X className="size-4" />} className="-mr-1 -mt-1" />}
    </div>
  );
}

/* -------------------------------------------------------------- PageHeader */
export function PageHeader({
  title,
  description,
  actions,
  meta,
  breadcrumb,
}: {
  title: React.ReactNode;
  description?: React.ReactNode;
  actions?: React.ReactNode;
  meta?: React.ReactNode;
  breadcrumb?: React.ReactNode;
}) {
  return (
    <header className="mb-6">
      {breadcrumb && <div className="mb-2 text-sm text-fg-3">{breadcrumb}</div>}
      <div className="flex flex-col lg:flex-row lg:items-start lg:justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
            <h1 className="text-2xl font-semibold text-fg tracking-tight break-words">{title}</h1>
            {meta}
          </div>
          {description && <p className="text-base text-fg-2 mt-1 max-w-[72ch]">{description}</p>}
        </div>
        {actions && <div className="flex flex-wrap items-center gap-2 shrink-0">{actions}</div>}
      </div>
    </header>
  );
}

/* -------------------------------------------------------------- InfoTip */
export function InfoTip({ text, label = "More information" }: { text: string; label?: string }) {
  return (
    <Tooltip content={text}>
      <button type="button" aria-label={label} className="inline-flex items-center justify-center size-6 -m-1 rounded-xs text-fg-3 hover:text-fg align-middle">
        <HelpCircle className="size-3.5" aria-hidden />
      </button>
    </Tooltip>
  );
}

/* -------------------------------------------------------------- EmptyState */
export function EmptyState({
  icon,
  title,
  description,
  action,
  className,
}: {
  icon?: React.ReactNode;
  title: string;
  description?: string;
  action?: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("flex flex-col items-center justify-center text-center px-6 py-10", className)}>
      {icon && <div className="text-fg-3 mb-3 [&>svg]:size-8">{icon}</div>}
      <p className="text-base font-medium text-fg">{title}</p>
      {description && <p className="text-sm text-fg-3 mt-1 max-w-[42ch]">{description}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

/* ----------------------------------------------------------------- Stat */
export function Stat({ label, value, delta, hint }: { label: string; value: string; delta?: { value: string; up: boolean }; hint?: string }) {
  return (
    <div className="min-w-0">
      <p className="text-sm text-fg-3 flex items-center gap-1">
        {label}
        {hint && <InfoTip text={hint} />}
      </p>
      <p className="text-xl font-semibold text-fg mt-1 tabular-nums truncate">{value}</p>
      {delta && (
        <p className={cn("text-xs mt-0.5", delta.up ? "text-success" : "text-danger")}>
          {delta.up ? "▲" : "▼"} {delta.value} vs. previous period
        </p>
      )}
    </div>
  );
}

/* --------------------------------------------------------------- Kbd */
export function Kbd({ children }: { children: React.ReactNode }) {
  return (
    <kbd className="inline-flex items-center h-5 px-1.5 rounded-xs border border-line bg-surface-2 text-2xs font-sans text-fg-3">
      {children}
    </kbd>
  );
}
