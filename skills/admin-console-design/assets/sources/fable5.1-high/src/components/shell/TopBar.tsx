import { useState } from "react";
import { Bell, ChevronsUpDown, HelpCircle, Menu as MenuIcon, Monitor, Moon, Sparkles, Star, Sun, User, LogOut, Settings, Check, Search } from "lucide-react";
import { cn } from "@/utils/cn";
import { useTheme, type ThemePref } from "@/lib/theme";
import { useShell } from "./ShellContext";
import { Badge, Button } from "@/components/ui/primitives";
import { Menu, Popover, Tooltip } from "@/components/ui/overlays";
import { ZONE } from "@/data/records";
import { useRouter } from "@/lib/router";

function CloudLogo({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 48 24" className={className} aria-hidden>
      <path d="M33.5 20H9.2a5.7 5.7 0 0 1-.9-11.3A8.8 8.8 0 0 1 25 6.5a6.3 6.3 0 0 1 8.7 5.8c0 .3 0 .6-.1.9A3.4 3.4 0 0 1 33.5 20Z" fill="#f6821f" />
      <path d="M38.2 20h-3.6a4.7 4.7 0 0 0 .3-1.8 5 5 0 0 0-1.4-3.5 5.6 5.6 0 0 1 4.7-1.7 3.5 3.5 0 1 1 0 7Z" fill="#fbad41" />
    </svg>
  );
}

const ZONES = [
  { name: "myexample.com", plan: "Free", status: "Pending" },
  { name: "goodpayway.shop", plan: "Pro", status: "Active" },
  { name: "goodhjw.top", plan: "Free", status: "Active" },
];

export function TopBar() {
  const { setMobileOpen, setPaletteOpen, isFrame } = useShell();
  const { pref, setPref, resolved } = useTheme();
  const { navigate } = useRouter();
  const [fav, setFav] = useState(false);
  const [zoneOpen, setZoneOpen] = useState(false);
  const [zone, setZone] = useState(ZONE);

  const themeIcon = pref === "system" ? <Monitor className="size-4" /> : resolved === "dark" ? <Moon className="size-4" /> : <Sun className="size-4" />;
  const themeItem = (v: ThemePref, label: string, icon: React.ReactNode) => ({
    label,
    icon: pref === v ? <Check /> : icon,
    onSelect: () => setPref(v),
  });

  return (
    <header className="sticky top-0 z-50 h-[var(--topbar-h)] bg-surface border-b border-line flex items-center gap-1 px-2 sm:px-3" role="banner">
      <a href="#main" className="sr-only-focusable fixed left-2 top-2 z-[100] bg-primary text-white px-3 py-2 rounded-sm text-sm">
        Skip to main content
      </a>

      <button type="button" aria-label="Open navigation" onClick={() => setMobileOpen(true)} className="md:hidden inline-flex items-center justify-center size-10 rounded-sm text-fg-2 hover:bg-surface-3">
        <MenuIcon className="size-5" />
      </button>

      <a href="#/" className="flex items-center h-10 px-1.5 rounded-sm shrink-0" aria-label="Home">
        <CloudLogo className="h-6 w-12" />
      </a>

      <div className="hidden sm:block h-6 w-px bg-line mx-1" aria-hidden />

      {/* zone breadcrumb / switcher */}
      <div className="flex items-center min-w-0 gap-0.5">
        <Tooltip content={fav ? "Remove from favorites" : "Add to favorites"}>
          <button
            type="button"
            aria-pressed={fav}
            aria-label="Favorite"
            onClick={() => setFav((f) => !f)}
            className="hidden sm:inline-flex items-center justify-center size-8 rounded-sm text-fg-3 hover:text-fg hover:bg-surface-3"
          >
            <Star className={cn("size-4", fav && "fill-brand text-brand")} />
          </button>
        </Tooltip>
        <Popover
          open={zoneOpen}
          onOpenChange={setZoneOpen}
          width={320}
          label="Switch domain"
          trigger={
            <button type="button" className="flex items-center gap-2 h-9 px-2 rounded-sm hover:bg-surface-3 min-w-0 max-w-[60vw] sm:max-w-none">
              <span className="text-base font-medium text-fg truncate">{zone}</span>
              <Badge className="hidden sm:inline-flex">free</Badge>
              <ChevronsUpDown className="size-3.5 text-fg-3 shrink-0" aria-hidden />
            </button>
          }
        >
          <div className="p-2">
            <div className="relative mb-2">
              <Search className="size-4 text-fg-3 absolute left-3 top-1/2 -translate-y-1/2" aria-hidden />
              <input aria-label="Search domains" placeholder="Search domains" className="w-full h-9 pl-9 pr-3 rounded-sm border border-line bg-surface text-base placeholder:text-fg-3 focus-visible:border-primary" />
            </div>
            <ul role="listbox" aria-label="Domains">
              {ZONES.map((z) => (
                <li key={z.name}>
                  <button
                    type="button"
                    role="option"
                    aria-selected={z.name === zone}
                    onClick={() => {
                      setZone(z.name);
                      setZoneOpen(false);
                    }}
                    className={cn("w-full flex items-center justify-between gap-2 h-10 px-2.5 rounded-xs text-left hover:bg-surface-2", z.name === zone && "bg-surface-2")}
                  >
                    <span className="min-w-0">
                      <span className="block text-base text-fg truncate">{z.name}</span>
                      <span className="block text-2xs text-fg-3">{z.plan} · {z.status}</span>
                    </span>
                    {z.name === zone && <Check className="size-4 text-primary-text shrink-0" aria-hidden />}
                  </button>
                </li>
              ))}
            </ul>
          </div>
        </Popover>
      </div>

      <div className="flex-1" />

      {/* right actions */}
      <div className="flex items-center gap-0.5">
        <Button variant="ghost" size="sm" className="hidden lg:inline-flex" icon={<Sparkles className="size-4" />} onClick={() => setPaletteOpen(true)}>
          Ask AI
        </Button>
        <Button variant="ghost" size="sm" className="hidden lg:inline-flex" icon={<HelpCircle className="size-4" />} onClick={() => navigate("/guide/readme")}>
          Support
        </Button>
        <Tooltip content="Notifications">
          <Button variant="ghost" size="sm" square aria-label="Notifications" icon={<Bell className="size-4" />} className="relative">
            <span className="absolute top-1.5 right-1.5 size-1.5 rounded-full bg-brand" aria-hidden />
          </Button>
        </Tooltip>
        <Menu
          label="Theme"
          trigger={<Button variant="ghost" size="sm" square aria-label={`Theme: ${pref}`} icon={themeIcon} />}
          items={[themeItem("light", "Light", <Sun />), themeItem("dark", "Dark", <Moon />), themeItem("system", "System (default)", <Monitor />)]}
        />
        <Menu
          label="Account"
          trigger={
            <button type="button" aria-label="Account menu" className="inline-flex items-center justify-center size-9 rounded-sm hover:bg-surface-3">
              <span className="size-7 rounded-full bg-primary-soft text-primary-text flex items-center justify-center text-xs font-semibold">B</span>
            </button>
          }
          items={[
            { label: "b@gardengateway.com", icon: <User />, disabled: true },
            { separator: true, label: "" },
            { label: "Account settings", icon: <Settings />, onSelect: () => navigate("/settings") },
            { label: "Sign out", icon: <LogOut />, danger: true },
          ]}
        />
      </div>
      {isFrame && <span className="sr-only">Preview frame</span>}
    </header>
  );
}
