import { useCallback, useEffect, useRef, useState, type PointerEvent as RPointerEvent } from "react";
import { ChevronDown, Cloud, PanelLeftClose, PanelLeftOpen, Search, Settings, Undo2, X } from "lucide-react";
import { Link } from "@/lib/route";
import { usePersisted, type Layout } from "@/lib/hooks";
import { Modal } from "@/ui/Modal";
import { NAV, isActivePath, type NavItem } from "./nav";

/* ==========================================================================
   侧边栏状态机（桌面端）

   pinned   : 用户的"固定"偏好（expanded | collapsed），持久化到 localStorage
   hover    : 指针悬停意图（进入延迟 120ms，离开延迟 250ms，触屏不触发）
   kbFocus  : 键盘焦点进入（:focus-visible）—— 与悬停等价，保证键盘用户同样可用
   forced   : 轻触 / 中等宽度下的显式"临时展开"，点击外部或 Esc 关闭
   suppressed: 刚点击"收起"时抑制再次悬停展开，直到指针离开一次

   rail     = 折叠态（icon rail）：wide+collapsed，或 medium
   peek     = rail 下的临时展开（覆盖式，不挤压内容区）
   ========================================================================== */

export type SidebarAction = "pin-expanded" | "pin-collapsed" | "peek-on" | "peek-off";

export function useSidebar(layout: Layout) {
  const [pinned, setPinned] = usePersisted<"expanded" | "collapsed">("nimbus.sidebar", "expanded", ["expanded", "collapsed"] as const);
  const [hover, setHover] = useState(false);
  const [kbFocus, setKbFocus] = useState(false);
  const [forced, setForced] = useState(false);
  const [suppressed, setSuppressed] = useState(false);
  const [drawer, setDrawer] = useState(false);
  const enterT = useRef(0);
  const leaveT = useRef(0);
  const inside = useRef(false);
  const rootRef = useRef<HTMLDivElement>(null);

  const rail = layout === "medium" || (layout === "wide" && pinned === "collapsed");
  const peek = rail && ((!suppressed && (hover || kbFocus)) || forced);
  const expanded = layout === "wide" ? pinned === "expanded" || peek : layout === "medium" ? peek : false;
  const slotWidth = layout === "wide" ? (pinned === "expanded" ? 240 : 56) : layout === "medium" ? 56 : 0;
  const overlay = expanded && slotWidth < 240;

  useEffect(() => {
    if (layout !== "narrow") setDrawer(false);
    setForced(false);
  }, [layout]);

  useEffect(() => {
    if (!forced) return;
    const down = (e: PointerEvent) => {
      if (!rootRef.current?.contains(e.target as Node)) setForced(false);
    };
    const key = (e: KeyboardEvent) => e.key === "Escape" && setForced(false);
    document.addEventListener("pointerdown", down);
    document.addEventListener("keydown", key);
    return () => {
      document.removeEventListener("pointerdown", down);
      document.removeEventListener("keydown", key);
    };
  }, [forced]);

  useEffect(
    () => () => {
      window.clearTimeout(enterT.current);
      window.clearTimeout(leaveT.current);
    },
    [],
  );

  const onPointerEnter = (e: RPointerEvent) => {
    inside.current = true;
    if (e.pointerType === "touch" || !rail) return;
    window.clearTimeout(leaveT.current);
    if (hover || suppressed) return;
    window.clearTimeout(enterT.current);
    enterT.current = window.setTimeout(() => setHover(true), 120);
  };
  const onPointerLeave = (e: RPointerEvent) => {
    inside.current = false;
    if (e.pointerType === "touch") return;
    window.clearTimeout(enterT.current);
    setSuppressed(false);
    window.clearTimeout(leaveT.current);
    leaveT.current = window.setTimeout(() => setHover(false), 250);
  };
  const onFocus = (e: React.FocusEvent<HTMLElement>) => {
    if ((e.target as HTMLElement).matches(":focus-visible")) setKbFocus(true);
  };
  const onBlur = (e: React.FocusEvent<HTMLElement>) => {
    if (!e.currentTarget.contains(e.relatedTarget as Node | null)) setKbFocus(false);
  };

  const toggle = useCallback(() => {
    if (layout === "wide") {
      setPinned(pinned === "expanded" ? "collapsed" : "expanded");
      window.clearTimeout(enterT.current);
      setHover(false);
      setKbFocus(false);
      setForced(false);
      // 收起后若指针仍停在侧边栏上，抑制再次悬停展开，直到指针离开
      setSuppressed(inside.current);
    } else if (layout === "medium") setForced((f) => !f);
    else setDrawer((d) => !d);
  }, [layout, pinned, setPinned]);

  const remote = useCallback(
    (a: SidebarAction) => {
      window.clearTimeout(enterT.current);
      if (a === "pin-expanded" || a === "pin-collapsed") {
        setPinned(a === "pin-expanded" ? "expanded" : "collapsed");
        setHover(false);
        setForced(false);
        setSuppressed(false);
      } else setHover(a === "peek-on");
    },
    [setPinned],
  );

  /** 底部切换按钮当前的语义：true = 点击会"收起"，false = 点击会"展开" */
  const toggleIsCollapse = layout === "wide" ? pinned === "expanded" : forced;

  return {
    pinned,
    toggleIsCollapse,
    peek,
    expanded,
    overlay,
    slotWidth,
    drawer,
    setDrawer,
    forced,
    setForced,
    toggle,
    remote,
    rootRef,
    handlers: { onPointerEnter, onPointerLeave, onFocus, onBlur },
  };
}
export type SidebarApi = ReturnType<typeof useSidebar>;

/* ---------------------------------------------------------------------- */

function Item({ item, path, expanded, open, onToggleGroup, onNavigate }: {
  item: NavItem;
  path: string;
  expanded: boolean;
  open: boolean;
  onToggleGroup: (id: string) => void;
  onNavigate: () => void;
}) {
  const Icon = item.icon;
  if (!item.children) {
    const active = isActivePath(item.to!, path);
    return (
      <li>
        <Link to={item.to!} className="sb-item" aria-current={active ? "page" : undefined} onClick={onNavigate}>
          <span className="sb-ico">
            <Icon size={18} aria-hidden="true" />
          </span>
          <span className="sb-label">{item.label}</span>
          {item.badge && <span className="badge badge-info sb-fade flex-none">{item.badge}</span>}
        </Link>
      </li>
    );
  }
  const childActive = item.id !== "recents" && item.children.some((c) => isActivePath(c.to, path));
  const visibleOpen = expanded && open;
  return (
    <li>
      <button
        type="button"
        className="sb-item"
        data-active={childActive && !visibleOpen ? "true" : undefined}
        aria-expanded={visibleOpen}
        aria-controls={`sub-${item.id}`}
        onClick={() => onToggleGroup(item.id)}
      >
        <span className="sb-ico">
          <Icon size={18} aria-hidden="true" />
        </span>
        <span className="sb-label">{item.label}</span>
        <ChevronDown
          size={16}
          aria-hidden="true"
          className="sb-fade flex-none text-muted transition-transform duration-200"
          style={{ transform: visibleOpen ? "rotate(180deg)" : undefined }}
        />
      </button>
      <div id={`sub-${item.id}`} className="sb-sub" data-open={visibleOpen}>
        <ul>
          {item.children.map((c) => (
            <li key={c.label + c.to}>
              <Link
                to={c.to}
                className="sb-sub-link"
                aria-current={item.id !== "recents" && isActivePath(c.to, path) ? "page" : undefined}
                onClick={onNavigate}
              >
                {c.label}
                {c.sub && <small>{c.sub}</small>}
              </Link>
            </li>
          ))}
        </ul>
      </div>
    </li>
  );
}

function NavContent({ api, path, expanded, onSearch, drawer }: { api: SidebarApi; path: string; expanded: boolean; onSearch: () => void; drawer?: boolean }) {
  const [openGroups, setOpenGroups] = useState<Set<string>>(() => new Set(["dns"]));

  // 路由变化时自动展开包含当前页的分组
  useEffect(() => {
    const g = NAV.find((n) => n.id !== "recents" && n.children?.some((c) => isActivePath(c.to, path)));
    if (g) setOpenGroups((s) => (s.has(g.id) ? s : new Set(s).add(g.id)));
  }, [path]);

  const onNavigate = () => {
    api.setForced(false);
    api.setDrawer(false);
  };
  const onToggleGroup = (id: string) => {
    setOpenGroups((s) => {
      const n = new Set(s);
      // 折叠态下点击分组：先展开侧边栏并确保该分组为打开状态
      if (!expanded) n.add(id);
      else if (n.has(id)) n.delete(id);
      else n.add(id);
      return n;
    });
    if (!expanded) api.setForced(true);
  };

  const wide = !drawer;
  const toggleLabel = api.toggleIsCollapse ? "Collapse sidebar" : "Expand sidebar";
  const ToggleIcon = toggleLabel === "Collapse sidebar" ? PanelLeftClose : PanelLeftOpen;

  return (
    <>
      <div className="sb-head">
        <Link to="/dashboard/overview" className="flex flex-none items-center gap-3 rounded-md" aria-label="Nimbus home" onClick={onNavigate}>
          <Cloud size={24} fill="currentColor" aria-hidden="true" className="text-brand" />
          <span className="sb-fade text-base font-bold tracking-wide">NIMBUS</span>
        </Link>
        {drawer && (
          <button type="button" className="btn btn-ghost btn-icon ml-auto" aria-label="Close navigation menu" onClick={() => api.setDrawer(false)}>
            <X size={18} aria-hidden="true" />
          </button>
        )}
      </div>
      <div className="sb-scroll">
        <ul>
          <li>
            <button type="button" className="sb-item" onClick={onSearch} aria-keyshortcuts="Control+K">
              <span className="sb-ico">
                <Search size={18} aria-hidden="true" />
              </span>
              <span className="sb-label">Quick search…</span>
              <kbd className="kbd sb-fade">Ctrl K</kbd>
            </button>
          </li>
          <li>
            <Link to="/dashboard/sites" className="sb-item" data-tone="muted" onClick={onNavigate}>
              <span className="sb-ico">
                <Undo2 size={18} aria-hidden="true" />
              </span>
              <span className="sb-label">Back to Domains</span>
            </Link>
          </li>
        </ul>
        <div className="sb-sep" role="separator" />
        <ul className="grid gap-1">
          {NAV.map((n) => (
            <Item key={n.id} item={n} path={path} expanded={expanded} open={openGroups.has(n.id)} onToggleGroup={onToggleGroup} onNavigate={onNavigate} />
          ))}
        </ul>
      </div>
      <div className="sb-foot">
        <ul className="grid gap-1">
          <li>
            <Link to="/dashboard/p/configurations" className="sb-item" aria-current={path.endsWith("/p/configurations") ? "page" : undefined} onClick={onNavigate}>
              <span className="sb-ico">
                <Settings size={18} aria-hidden="true" />
              </span>
              <span className="sb-label">Configurations</span>
            </Link>
          </li>
          {wide && (
            <li>
              <button type="button" className="sb-item" onClick={api.toggle} aria-keyshortcuts="[">
                <span className="sb-ico">
                  <ToggleIcon size={18} aria-hidden="true" />
                </span>
                <span className="sb-label">{toggleLabel}</span>
                <kbd className="kbd sb-fade">[</kbd>
              </button>
            </li>
          )}
        </ul>
      </div>
    </>
  );
}

/** 桌面 / 平板：in-flow 占位槽 + 绝对定位的侧边栏（展开时覆盖内容而不推动内容） */
export function Sidebar({ api, path, onSearch }: { api: SidebarApi; path: string; onSearch: () => void }) {
  return (
    <div ref={api.rootRef} className="sb-slot" style={{ width: api.slotWidth }}>
      <nav
        className="sb"
        aria-label="Primary"
        data-expanded={api.expanded}
        data-overlay={api.overlay}
        data-peek={api.peek}
        {...api.handlers}
      >
        <NavContent api={api} path={path} expanded={api.expanded} onSearch={onSearch} />
      </nav>
    </div>
  );
}

/** 窄屏：汉堡按钮触发的模态抽屉（焦点陷阱 / Esc / 点击遮罩关闭） */
export function DrawerSidebar({ api, path, onSearch }: { api: SidebarApi; path: string; onSearch: () => void }) {
  return (
    <Modal open={api.drawer} onClose={() => api.setDrawer(false)} label="Navigation menu" kind="drawer">
      <nav className="sb sb-static" aria-label="Primary" data-expanded="true">
        <NavContent
          api={api}
          path={path}
          expanded
          drawer
          onSearch={() => {
            api.setDrawer(false);
            window.setTimeout(onSearch, 200);
          }}
        />
      </nav>
    </Modal>
  );
}
