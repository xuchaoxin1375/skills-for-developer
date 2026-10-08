import type { LucideIcon } from "lucide-react";
import {
  LayoutDashboard,
  History,
  BookOpen,
  Ruler,
  Network,
  Mail,
  Lock,
  Shield,
  LogIn,
  Zap,
  Database,
  Code2,
  Pickaxe,
  GitBranch,
  Globe,
  Settings,
  FormInput,
  Bot,
} from "lucide-react";

export interface NavItem {
  id: string;
  label: string;
  icon?: LucideIcon;
  path?: string;
  children?: { id: string; label: string; path: string; badge?: string }[];
  badge?: string;
  /** separate group visually */
  group?: "top" | "main" | "bottom";
  /** hidden inside the responsive-lab iframe to prevent recursion */
  hideInFrame?: boolean;
}

export const NAV: NavItem[] = [
  { id: "overview", label: "Overview", icon: LayoutDashboard, path: "/", group: "top" },
  { id: "recents", label: "Recents", icon: History, group: "top" },
  {
    id: "guide",
    label: "Design Guide",
    icon: BookOpen,
    group: "top",
    children: [
      { id: "guide-readme", label: "Document map", path: "/guide/readme" },
      { id: "guide-principles", label: "Principles", path: "/guide/principles" },
      { id: "guide-tokens", label: "Tokens & visuals", path: "/guide/tokens" },
      { id: "guide-shell", label: "Shell & sidebar", path: "/guide/shell" },
      { id: "guide-forms", label: "Forms", path: "/guide/forms" },
      { id: "guide-tables", label: "Tables & lists", path: "/guide/tables" },
      { id: "guide-responsive", label: "Responsive", path: "/guide/responsive" },
      { id: "guide-a11y", label: "Accessibility", path: "/guide/accessibility" },
      { id: "guide-deploy", label: "Deploy & usage", path: "/guide/deployment" },
    ],
  },
  { id: "lab", label: "Responsive Lab", icon: Ruler, path: "/lab", group: "top", hideInFrame: true, badge: "Demo" },

  {
    id: "dns",
    label: "DNS",
    icon: Network,
    children: [
      { id: "dns-records", label: "Records", path: "/dns/records" },
      { id: "dns-analytics", label: "Analytics", path: "/dns/analytics" },
      { id: "dns-settings", label: "Settings", path: "/dns/settings" },
    ],
  },
  {
    id: "forms",
    label: "Form Patterns",
    icon: FormInput,
    badge: "New",
    children: [
      { id: "forms-create", label: "Create (long form)", path: "/forms/create" },
      { id: "forms-wizard", label: "Wizard (stepper)", path: "/forms/wizard" },
    ],
  },
  { id: "ai", label: "AI Crawl Control", icon: Bot, path: "/placeholder/ai" },
  { id: "email", label: "Email", icon: Mail, children: [{ id: "email-routing", label: "Email Routing", path: "/placeholder/email" }] },
  { id: "ssl", label: "SSL/TLS", icon: Lock, children: [{ id: "ssl-overview", label: "Overview", path: "/placeholder/ssl" }, { id: "ssl-edge", label: "Edge Certificates", path: "/placeholder/ssl-edge" }] },
  { id: "security", label: "Security", icon: Shield, children: [{ id: "sec-overview", label: "Overview", path: "/placeholder/security" }, { id: "sec-waf", label: "WAF", path: "/placeholder/waf" }] },
  { id: "access", label: "Access", icon: LogIn, path: "/placeholder/access" },
  { id: "speed", label: "Speed", icon: Zap, path: "/placeholder/speed" },
  { id: "caching", label: "Caching", icon: Database, path: "/placeholder/caching" },
  { id: "workers", label: "Workers Routes", icon: Code2, path: "/placeholder/workers" },
  { id: "rules", label: "Rules", icon: Pickaxe, path: "/placeholder/rules" },
  { id: "network", label: "Network", icon: GitBranch, path: "/placeholder/network" },
  { id: "traffic", label: "Traffic", icon: Globe, path: "/placeholder/traffic" },

  { id: "settings", label: "Settings", icon: Settings, path: "/settings", group: "bottom" },
];

export interface RecentItem {
  label: string;
  crumbs: string[];
  path: string;
}

export const RECENTS: RecentItem[] = [
  { label: "Records", crumbs: ["myexample.com", "DNS"], path: "/dns/records" },
  { label: "Create (long form)", crumbs: ["Form Patterns"], path: "/forms/create" },
  { label: "Shell & sidebar", crumbs: ["Design Guide"], path: "/guide/shell" },
  { label: "Settings", crumbs: ["myexample.com"], path: "/settings" },
];

/** Resolve which top-level item/child is active for a path. */
export function findActive(path: string): { itemId: string | null; childId: string | null } {
  for (const it of NAV) {
    if (it.path && (it.path === path || (it.path !== "/" && path.startsWith(it.path + "/")))) {
      return { itemId: it.id, childId: null };
    }
    for (const c of it.children ?? []) {
      if (c.path === path || path.startsWith(c.path + "/")) return { itemId: it.id, childId: c.id };
    }
  }
  return { itemId: null, childId: null };
}

export function flatNav(): { label: string; path: string; group: string }[] {
  const out: { label: string; path: string; group: string }[] = [];
  for (const it of NAV) {
    if (it.path) out.push({ label: it.label, path: it.path, group: "Pages" });
    for (const c of it.children ?? []) out.push({ label: `${it.label} / ${c.label}`, path: c.path, group: "Pages" });
  }
  return out;
}
