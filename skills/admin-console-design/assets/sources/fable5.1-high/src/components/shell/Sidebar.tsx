import { useEffect, useMemo, useRef, useState } from "react";
import { ArrowLeft, ChevronDown, PanelLeftClose, PanelLeftOpen, Search, X } from "lucide-react";
import { cn } from "@/utils/cn";
import { NAV, RECENTS, findActive, type NavItem } from "@/data/nav";
import { useRouter, Link } from "@/lib/router";
import { useShell } from "./ShellContext";
import { Badge } from "@/components/ui/primitives";
import { Kbd } from "@/components/ui/layout";

const RAIL = "var(--sidebar-rail)"; // 56px
const WIDE = "var(--sidebar-expanded)"; // 264px

/**
 * Text labels in the rail: fade in slightly after the width animation starts,
 * and become `visibility:hidden` when collapsed so nothing can leak, be focused or be read out.
 */
const labelCls = (expanded: boolean) =>
  cn(
    "transition-[opacity,visibility] duration-[var(--dur-base)]",
    expanded ? "opacity-100 visible delay-75" : "opacity-0 invisible"
  );

/* ---------------------------------------------------------- row primitive */
function Row({
  icon,
  label,
  active,
  expanded,
  trailing,
  depth = 0,
  ...rest
}: {
  icon?: React.ReactNode;
  label: React.ReactNode;
  active?: boolean;
  expanded: boolean;
  trailing?: React.ReactNode;
  depth?: 0 | 1;
} & React.HTMLAttributes<HTMLElement> & { as?: "a" | "button"; href?: string; type?: "button" }) {
  const { as = "a", className, ...attrs } = rest as any;
  const Tag: any = as;
  return (
    <Tag
      {...attrs}
      aria-current={active && as === "a" ? "page" : undefined}
      className={cn(
        "group/row relative flex items-center h-9 w-full rounded-sm text-left select-none transition-colors duration-[var(--dur-fast)]",
        "text-fg-2 hover:bg-surface-3 hover:text-fg",
        active && "bg-surface-3 text-fg font-medium",
        depth === 1 ? "pl-[50px] pr-2 h-8" : "pl-[10px] pr-2",
        className
      )}
    >
      {icon && (
        <span className={cn("flex items-center justify-center size-9 shrink-0 [&>svg]:size-[18px]", active ? "text-fg" : "text-fg-3 group-hover/row:text-fg-2")} aria-hidden>
          {icon}
        </span>
      )}
      <span className={cn("flex items-center gap-2 min-w-0 flex-1 ml-1 text-base whitespace-nowrap", labelCls(expanded))}>{label}</span>
      {trailing && <span className={cn("shrink-0 text-fg-3", labelCls(expanded))}>{trailing}</span>}
      {active && depth === 0 && <span aria-hidden className="absolute left-0 top-2 bottom-2 w-[3px] rounded-r bg-brand" />}
    </Tag>
  );
}

/* ----------------------------------------------------------- group item */
function NavGroup({ item, expanded, activeChild, open, onToggle }: { item: NavItem; expanded: boolean; activeChild: string | null; open: boolean; onToggle: () => void }) {
  const { navigate } = useRouter();
  const Icon = item.icon!;
  const isActive = !!activeChild;
  const first = item.children![0].path;

  // Single persistent <button> across rail/peek so the actionable DOM node and
  // semantic kind never change (avoids losing pointerdown->click activation).
  // Rail behavior adjustment: rail group is a button (navigates to first child),
  // matching the existing Recents pattern; expanded behavior stays accordion.
  // Only props change with `expanded`, so React updates the same element in place.
  const row = (
    <Row
      as="button"
      type="button"
      icon={<Icon />}
      label={
        <>
          <span className="truncate">{item.label}</span>
          {item.badge && <Badge tone="info">{item.badge}</Badge>}
        </>
      }
      active={expanded ? isActive && !open : isActive}
      expanded={expanded}
      aria-expanded={expanded ? open : undefined}
      aria-controls={`nav-${item.id}`}
      aria-label={expanded ? undefined : item.label}
      onClick={expanded ? onToggle : () => navigate(first)}
      trailing={<ChevronDown className={cn("size-4 transition-transform duration-[var(--dur-base)]", open && "rotate-180")} />}
    />
  );

  return (
    <li>
      {row}
      <div
        id={`nav-${item.id}`}
        className={cn(
          "grid transition-[grid-template-rows,opacity,visibility] duration-[var(--dur-base)] ease-[var(--ease-out)]",
          open && expanded ? "grid-rows-[1fr] opacity-100 visible" : "grid-rows-[0fr] opacity-0 invisible"
        )}
        aria-hidden={!(open && expanded)}
      >
        <ul className="overflow-hidden py-0.5 space-y-0.5">
          {item.children!.map((c) => (
            <li key={c.id}>
              <Row
                as="a"
                href={"#" + c.path}
                depth={1}
                active={activeChild === c.id}
                expanded={expanded}
                tabIndex={open && expanded ? 0 : -1}
                label={
                  <>
                    <span className="truncate">{c.label}</span>
                    {c.badge && <Badge tone="info">{c.badge}</Badge>}
                  </>
                }
              />
            </li>
          ))}
        </ul>
      </div>
    </li>
  );
}

/* --------------------------------------------------------------- content */
export function SidebarContent({ expanded, onNavigate }: { expanded: boolean; onNavigate?: () => void }) {
  const { path, navigate } = useRouter();
  const { isFrame, setPaletteOpen, pinned, setPinned, collapseNow, isMobile } = useShell();
  const active = useMemo(() => findActive(path), [path]);
  const [openIds, setOpenIds] = useState<Set<string>>(() => new Set(active.itemId ? [active.itemId] : []));
  const [recentsOpen, setRecentsOpen] = useState(true);

  // auto-open the group that contains the active route
  useEffect(() => {
    if (active.itemId) setOpenIds((s) => (s.has(active.itemId!) ? s : new Set(s).add(active.itemId!)));
  }, [active.itemId]);

  const toggle = (id: string) =>
    setOpenIds((s) => {
      const n = new Set(s);
      n.has(id) ? n.delete(id) : n.add(id);
      return n;
    });

  const items = NAV.filter((n) => !(isFrame && n.hideInFrame));
  const top = items.filter((n) => n.group === "top");
  const main = items.filter((n) => !n.group || n.group === "main");
  const bottom = items.filter((n) => n.group === "bottom");

  const renderItem = (item: NavItem) => {
    if (item.id === "recents") {
      const Icon = item.icon!;
      return (
        <li key={item.id}>
          <Row
            as="button"
            type="button"
            icon={<Icon />}
            label={item.label}
            expanded={expanded}
            aria-expanded={expanded ? recentsOpen : undefined}
            aria-controls="nav-recents"
            onClick={() => (expanded ? setRecentsOpen((o) => !o) : navigate(RECENTS[0].path))}
            aria-label={expanded ? undefined : "Recents"}
            trailing={<ChevronDown className={cn("size-4 transition-transform duration-[var(--dur-base)]", recentsOpen && "rotate-180")} />}
          />
          <div
            id="nav-recents"
            aria-hidden={!(recentsOpen && expanded)}
            className={cn("grid transition-[grid-template-rows,opacity,visibility] duration-[var(--dur-base)]", recentsOpen && expanded ? "grid-rows-[1fr] opacity-100 visible" : "grid-rows-[0fr] opacity-0 invisible")}
          >
            <ul className="overflow-hidden py-0.5">
              {RECENTS.map((r) => (
                <li key={r.path + r.label}>
                  <Link
                    to={r.path}
                    tabIndex={recentsOpen && expanded ? 0 : -1}
                    onClick={onNavigate}
                    className="flex flex-col justify-center pl-[50px] pr-2 py-1.5 rounded-sm hover:bg-surface-3 min-w-0"
                  >
                    <span className="text-base text-fg truncate leading-5">{r.label}</span>
                    <span className="text-2xs text-fg-3 truncate">{r.crumbs.join(" / ")}</span>
                  </Link>
                </li>
              ))}
            </ul>
          </div>
        </li>
      );
    }
    if (item.children?.length) {
      return <NavGroup key={item.id} item={item} expanded={expanded} activeChild={active.itemId === item.id ? active.childId : null} open={openIds.has(item.id)} onToggle={() => toggle(item.id)} />;
    }
    const Icon = item.icon!;
    return (
      <li key={item.id}>
        <Row
          as="a"
          href={"#" + item.path}
          icon={<Icon />}
          aria-label={expanded ? undefined : item.label}
          label={
            <>
              <span className="truncate">{item.label}</span>
              {item.badge && <Badge tone="info">{item.badge}</Badge>}
            </>
          }
          active={active.itemId === item.id}
          expanded={expanded}
          onClick={onNavigate}
        />
      </li>
    );
  };

  return (
    <div className="flex flex-col h-full w-[var(--sidebar-expanded)]">
      {/* utility rows: outer padding stays px-0 so rail/peek icon x never shifts */}
      <div className={cn("pt-2 space-y-1 px-0")}>
        <button
          type="button"
          onClick={() => setPaletteOpen(true)}
          aria-label="Quick search (Ctrl K)"
          className={cn(
            "flex items-center h-9 w-full rounded-sm text-fg-3 transition-colors duration-[var(--dur-fast)]",
            expanded ? "bg-surface border border-line hover:border-line-strong pl-[9px] pr-2" : "hover:bg-surface-3 pl-[10px] pr-2"
          )}
        >
          <span className="flex items-center justify-center size-9 shrink-0" aria-hidden>
            <Search className="size-[18px]" />
          </span>
          <span className={cn("flex-1 text-left text-base whitespace-nowrap", labelCls(expanded))}>
            Quick search…
          </span>
          <span className={labelCls(expanded)}>
            <Kbd>Ctrl K</Kbd>
          </span>
        </button>
        <Row as="a" href="#/" icon={<ArrowLeft />} label="Back to Domains" expanded={expanded} aria-label={expanded ? undefined : "Back to Domains"} className="bg-surface-2/70" onClick={onNavigate} />
      </div>

      <div className={cn("my-2 border-t border-line mx-[16px]")} />

      {/* scrollable nav: outer padding stays px-0 so rail/peek icon x never shifts */}
      <nav aria-label="Primary" className={cn("flex-1 min-h-0 overflow-y-auto overflow-x-hidden overscroll-contain pb-2 px-0")}>
        <ul className="space-y-0.5">{top.map(renderItem)}</ul>
        <div className={cn("my-2 border-t border-line", expanded ? "mx-2" : "mx-[16px]")} />
        <ul className="space-y-0.5">{main.map(renderItem)}</ul>
      </nav>

      {/* bottom: outer padding stays px-0 so rail/peek icon x never shifts */}
      <div className={cn("py-2 border-t border-line space-y-0.5 px-0")}>
        <ul>{bottom.map(renderItem)}</ul>
        {!isMobile && (
          <button
            type="button"
            aria-pressed={pinned}
            aria-label={pinned ? "Collapse sidebar" : "Keep sidebar expanded"}
            title={pinned ? "Collapse sidebar ( [ )" : "Keep sidebar expanded ( [ )"}
            onClick={() => {
              if (pinned) collapseNow();
              setPinned(!pinned);
            }}
            className="flex items-center h-9 w-full rounded-sm text-fg-3 hover:bg-surface-3 hover:text-fg pl-[10px] pr-2 transition-colors"
          >
            <span className="flex items-center justify-center size-9 shrink-0" aria-hidden>
              {pinned ? <PanelLeftClose className="size-[18px]" /> : <PanelLeftOpen className="size-[18px]" />}
            </span>
            <span className={cn("ml-1 text-sm whitespace-nowrap", labelCls(expanded))}>
              {pinned ? "Collapse" : "Keep expanded"}
            </span>
            <span className={cn("ml-auto", labelCls(expanded))}>
              <Kbd>[</Kbd>
            </span>
          </button>
        )}
      </div>
    </div>
  );
}

/* ---------------------------------------------------------------- desktop */
export function DesktopSidebar() {
  const { pinned, expanded, peek, onSidebarEnter, onSidebarLeave, onSidebarFocusIn, onSidebarFocusOut, onSidebarPointerDown, onSidebarPointerUp, dismissPeek } = useShell();
  const panel = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!peek) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      e.preventDefault();
      const active = document.activeElement as HTMLElement | null;
      const inPanel = !!active && !!panel.current?.contains(active);
      dismissPeek();
      // Keep focus on a visible, stable sidebar control instead of BODY.
      // suppressFocus (set in dismissPeek) ensures this retained/programmatic
      // focus does not immediately reopen peek; it clears on full focus-out.
      if (inPanel && active) {
        const inSubmenu = !!active.closest?.('[id^="nav-"] ul, [id^="nav-"]');
        // Submenu child links become aria-hidden/tabIndex -1 in rail; move those.
        const willHide = inSubmenu || active.tabIndex === -1 || active.getAttribute?.("aria-hidden") === "true";
        if (willHide) {
          const stable =
            panel.current?.querySelector<HTMLElement>('button[aria-label^="Quick search"]') ??
            panel.current?.querySelector<HTMLElement>("a[href], button:not([tabindex='-1'])");
          stable?.focus();
        }
        // otherwise keep focus where it is (already a visible rail control)
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [peek, dismissPeek]);

  return (
    <aside
      className="hidden md:block shrink-0 transition-[width] duration-[var(--dur-slow)] ease-[var(--ease-out)]"
      style={{ width: pinned ? WIDE : RAIL }}
      aria-label="Sidebar"
    >
      <div
        ref={panel}
        data-state={pinned ? "pinned" : peek ? "peek" : "rail"}
        onMouseEnter={onSidebarEnter}
        onMouseLeave={onSidebarLeave}
        onFocusCapture={onSidebarFocusIn}
        onBlurCapture={(e) => onSidebarFocusOut(e.relatedTarget, panel.current)}
        onPointerDown={onSidebarPointerDown}
        onPointerUp={() => onSidebarPointerUp(panel.current)}
        style={{ width: expanded ? WIDE : RAIL }}
        className={cn(
          "fixed left-0 top-[var(--topbar-h)] bottom-0 bg-surface border-r border-line overflow-hidden",
          "transition-[width,box-shadow] duration-[var(--dur-slow)] ease-[var(--ease-out)]",
          peek ? "z-40 shadow-3" : "z-20"
        )}
      >
        <SidebarContent expanded={expanded} />
      </div>
    </aside>
  );
}

/* ----------------------------------------------------------------- mobile */
export function MobileDrawer() {
  const { mobileOpen, setMobileOpen } = useShell();
  const panel = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!mobileOpen) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setMobileOpen(false);
    document.addEventListener("keydown", onKey);
    requestAnimationFrame(() => panel.current?.querySelector<HTMLElement>("button")?.focus());
    return () => {
      document.body.style.overflow = prev;
      document.removeEventListener("keydown", onKey);
    };
  }, [mobileOpen, setMobileOpen]);

  if (!mobileOpen) return null;
  return (
    <div className="md:hidden fixed inset-0 z-[60]">
      <div className="absolute inset-0 bg-[var(--c-overlay)] anim-fade" onClick={() => setMobileOpen(false)} aria-hidden />
      <div
        ref={panel}
        role="dialog"
        aria-modal="true"
        aria-label="Navigation"
        className="absolute left-0 top-0 bottom-0 w-[min(var(--sidebar-expanded),85vw)] bg-surface shadow-3 anim-slide-left overflow-hidden flex flex-col"
      >
        <div className="flex items-center justify-between h-[var(--topbar-h)] px-3 border-b border-line shrink-0">
          <span className="font-semibold text-fg">Navigation</span>
          <button type="button" aria-label="Close navigation" onClick={() => setMobileOpen(false)} className="size-9 inline-flex items-center justify-center rounded-sm hover:bg-surface-3">
            <X className="size-5" />
          </button>
        </div>
        <div className="flex-1 min-h-0 overflow-hidden [&>div]:w-full">
          <SidebarContent expanded onNavigate={() => setMobileOpen(false)} />
        </div>
      </div>
    </div>
  );
}
