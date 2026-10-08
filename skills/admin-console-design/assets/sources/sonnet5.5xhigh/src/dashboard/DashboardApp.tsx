import { useEffect, useMemo, useRef, useState } from "react";
import { ClipboardList, FileText, Funnel, Lock, PanelLeft, Plus, Sun } from "lucide-react";
import { Link, navigate, type Route } from "@/lib/route";
import { isEditable, useLayout } from "@/lib/hooks";
import { postToParent, type ToFrame } from "@/lib/bridge";
import { setTheme, useTheme } from "@/lib/theme";
import { ToastProvider } from "@/ui/Toast";
import { DataProvider } from "./data";
import { DrawerSidebar, Sidebar, useSidebar } from "./Sidebar";
import { Topbar } from "./Topbar";
import { CommandPalette, type Command } from "./CommandPalette";
import { DnsRecords } from "./pages/DnsRecords";
import { RecordForm } from "./pages/RecordForm";
import { SettingsPage } from "./pages/Settings";
import { AddSiteWizard } from "./pages/AddSite";
import { Overview, Placeholder, SitesPage } from "./pages/Misc";
import { LegacyShell } from "./Legacy";

/** 来自展示壳（父窗口）的通用指令：主题 / 路由。仅接受 window.parent 的消息 */
function useParentCommands() {
  useEffect(() => {
    const on = (e: MessageEvent<ToFrame>) => {
      if (e.source !== window.parent || !e.data) return;
      if (e.data.type === "nimbus:theme") setTheme(e.data.value, false);
      else if (e.data.type === "nimbus:navigate") navigate(e.data.to, { force: true });
    };
    window.addEventListener("message", on);
    postToParent({ type: "nimbus:ready" });
    return () => window.removeEventListener("message", on);
  }, []);
}

export default function DashboardApp({ route }: { route: Route }) {
  useParentCommands();
  const variant = route.params.get("variant") === "legacy" ? "legacy" : "cf";
  return (
    <ToastProvider>
      <DataProvider>{variant === "legacy" ? <LegacyShell route={route} /> : <Shell route={route} />}</DataProvider>
    </ToastProvider>
  );
}

function Shell({ route }: { route: Route }) {
  const layout = useLayout();
  const sb = useSidebar(layout);
  const { resolved } = useTheme();
  const [searchOpen, setSearchOpen] = useState(false);
  const mainRef = useRef<HTMLElement>(null);
  const firstRender = useRef(true);
  const path = "/" + route.path.join("/");
  const parts = route.path.slice(1);

  // 路由切换：回到顶部并把焦点移到主内容区（键盘 / 读屏用户不会"丢失位置"）
  useEffect(() => {
    if (firstRender.current) {
      firstRender.current = false;
      return;
    }
    // 带 ?highlight 的跳转由列表页自行滚动到目标行，这里不再回顶
    if (!route.params.get("highlight")) window.scrollTo(0, 0);
    mainRef.current?.focus({ preventScroll: true });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [path]);

  // 全局快捷键：Ctrl/⌘ + K 打开快速搜索；[ 切换侧边栏（输入框内不触发）
  const toggle = sb.toggle;
  useEffect(() => {
    const on = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setSearchOpen(true);
      } else if (e.key === "[" && !e.ctrlKey && !e.metaKey && !e.altKey && !isEditable(e.target) && layout !== "narrow") {
        toggle();
      }
    };
    window.addEventListener("keydown", on);
    return () => window.removeEventListener("keydown", on);
  }, [toggle, layout]);

  // 与展示壳通信：接收侧边栏演示指令，上报当前状态
  const remote = sb.remote;
  useEffect(() => {
    const on = (e: MessageEvent<ToFrame>) => {
      if (e.source !== window.parent || e.data?.type !== "nimbus:sidebar") return;
      remote(e.data.action);
    };
    window.addEventListener("message", on);
    return () => window.removeEventListener("message", on);
  }, [remote]);

  // 宽度变化本身不触发上报 / 重渲染（只有布局档位、侧边栏状态、路由变化才上报），宽度扫描时零 React 开销
  useEffect(() => {
    postToParent({
      type: "nimbus:state",
      path,
      layout,
      pinned: sb.pinned,
      expanded: sb.expanded,
      peek: sb.peek,
      drawer: sb.drawer,
      width: window.innerWidth,
      variant: "cf",
    });
  }, [path, layout, sb.pinned, sb.expanded, sb.peek, sb.drawer]);

  const commands = useMemo<Command[]>(
    () => [
      { id: "ov", label: "Overview", group: "Page", icon: ClipboardList, run: () => navigate("/dashboard/overview") },
      { id: "dns", label: "DNS records", group: "Page", icon: FileText, keywords: "records list", run: () => navigate("/dashboard/dns") },
      { id: "add", label: "Add DNS record", group: "Action", icon: Plus, keywords: "new create form", run: () => navigate("/dashboard/dns/new") },
      { id: "ssl", label: "SSL/TLS settings", group: "Page", icon: Lock, keywords: "encryption https", run: () => navigate("/dashboard/settings") },
      { id: "site", label: "Add a site", group: "Action", icon: Plus, keywords: "wizard domain onboarding", run: () => navigate("/dashboard/sites/new") },
      { id: "sites", label: "All domains", group: "Page", icon: Funnel, run: () => navigate("/dashboard/sites") },
      { id: "sb", label: "Toggle sidebar", group: "Action", icon: PanelLeft, keywords: "collapse expand", run: () => toggle() },
      { id: "theme", label: resolved === "dark" ? "Switch to light theme" : "Switch to dark theme", group: "Action", icon: Sun, run: () => setTheme(resolved === "dark" ? "light" : "dark", true) },
    ],
    [resolved, toggle],
  );

  let page;
  const [a, b, c] = parts;
  if (!a || a === "overview") page = <Overview />;
  else if (a === "dns") page = b === "new" ? <RecordForm mode="add" /> : b === "edit" ? <RecordForm mode="edit" id={c} /> : <DnsRecords route={route} />;
  else if (a === "settings") page = <SettingsPage />;
  else if (a === "sites") page = b === "new" ? <AddSiteWizard /> : <SitesPage />;
  else page = <Placeholder slug={a === "p" ? b : a} />;

  return (
    <div className="app" data-layout={layout} lang="en">
      <a
        href="#main"
        className="btn btn-primary skip-link"
        onClick={(e) => {
          e.preventDefault();
          mainRef.current?.focus();
        }}
      >
        Skip to main content
      </a>
      {layout !== "narrow" && <Sidebar api={sb} path={path} onSearch={() => setSearchOpen(true)} />}
      <div className="app-main">
        <Topbar narrow={layout === "narrow"} drawerOpen={sb.drawer} onMenu={sb.toggle} />
        <main id="main" ref={mainRef} tabIndex={-1} className="page">
          <div key={path}>{page}</div>
        </main>
        <footer className="border-t border-line px-4 py-4 text-sm text-muted">
          <ul className="flex flex-wrap items-center justify-center gap-x-4 gap-y-1">
            {["Support", "System Status", "Careers", "Terms of Use", "Privacy Policy"].map((t) => (
              <li key={t}>
                <Link to={`/dashboard/p/${t.toLowerCase().replace(/\s+/g, "-")}`} className="link text-muted">
                  {t}
                </Link>
              </li>
            ))}
            <li>© 2026 Nimbus, Inc. (demo)</li>
          </ul>
        </footer>
      </div>
      {layout === "narrow" && <DrawerSidebar api={sb} path={path} onSearch={() => setSearchOpen(true)} />}
      <CommandPalette open={searchOpen} onClose={() => setSearchOpen(false)} commands={commands} />
    </div>
  );
}
