import {
  Activity,
  Bot,
  Boxes,
  ChartPie,
  ClipboardList,
  Clock,
  Database,
  Lock,
  LogIn,
  Mail,
  Network,
  Shield,
  Wrench,
  Zap,
  type LucideIcon,
} from "lucide-react";

export interface NavChild {
  label: string;
  to: string;
  sub?: string;
}
export interface NavItem {
  id: string;
  label: string;
  icon: LucideIcon;
  to?: string;
  badge?: string;
  children?: NavChild[];
}

export const NAV: NavItem[] = [
  { id: "overview", label: "Overview", icon: ClipboardList, to: "/dashboard/overview" },
  {
    id: "recents",
    label: "Recents",
    icon: Clock,
    children: [
      { label: "Records", sub: "myexample.com / DNS", to: "/dashboard/dns" },
      { label: "goodpayway.shop", sub: "Domains", to: "/dashboard/sites" },
      { label: "Email Security", sub: "goodhjw.top / Email", to: "/dashboard/p/email" },
      { label: "DMARC Management", sub: "goodhjw.top / Email", to: "/dashboard/p/dmarc" },
    ],
  },
  { id: "ai", label: "AI Crawl Control", icon: Bot, to: "/dashboard/p/ai-crawl-control" },
  { id: "analytics", label: "Analytics", icon: ChartPie, to: "/dashboard/p/analytics" },
  { id: "observability", label: "Observability", icon: Activity, to: "/dashboard/p/observability", badge: "New" },
  {
    id: "dns",
    label: "DNS",
    icon: Network,
    children: [
      { label: "Records", to: "/dashboard/dns" },
      { label: "Analytics", to: "/dashboard/p/dns-analytics" },
      { label: "Settings", to: "/dashboard/p/dns-settings" },
    ],
  },
  { id: "email", label: "Email", icon: Mail, to: "/dashboard/p/email" },
  { id: "ssl", label: "SSL/TLS", icon: Lock, to: "/dashboard/settings" },
  { id: "security", label: "Security", icon: Shield, to: "/dashboard/p/security" },
  { id: "access", label: "Access", icon: LogIn, to: "/dashboard/p/access" },
  { id: "speed", label: "Speed", icon: Zap, to: "/dashboard/p/speed" },
  { id: "caching", label: "Caching", icon: Database, to: "/dashboard/p/caching" },
  { id: "workers", label: "Workers Routes", icon: Boxes, to: "/dashboard/p/workers" },
  { id: "rules", label: "Rules", icon: Wrench, to: "/dashboard/p/rules" },
];

export const PAGE_TITLES: Record<string, string> = Object.fromEntries(
  NAV.flatMap((n) => [
    ...(n.to ? [[n.to.split("/").pop() as string, n.label]] : []),
    ...(n.children ?? []).map((c) => [c.to.split("/").pop() as string, `${n.label} · ${c.label}`]),
  ]),
);

/** 子路由（如 /dns/new）仍视为父级列表页处于激活状态 */
export function isActivePath(to: string, path: string): boolean {
  return path === to || path.startsWith(to + "/");
}
