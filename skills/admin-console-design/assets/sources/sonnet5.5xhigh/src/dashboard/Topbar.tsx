import { useState } from "react";
import { ChevronsUpDown, CircleUser, LifeBuoy, Menu, Monitor, Moon, Sparkles, Star, Sun } from "lucide-react";
import { Link } from "@/lib/route";
import { useTheme, type ThemePref } from "@/lib/theme";
import { Popover } from "@/ui/Popover";
import { useToast } from "@/ui/Toast";
import { DOMAIN, useData } from "./data";

const THEMES: { v: ThemePref; label: string; Icon: typeof Sun }[] = [
  { v: "system", label: "System", Icon: Monitor },
  { v: "light", label: "Light", Icon: Sun },
  { v: "dark", label: "Dark", Icon: Moon },
];

export function Topbar({ narrow, drawerOpen, onMenu }: { narrow: boolean; drawerOpen: boolean; onMenu: () => void }) {
  const { pref, setPref } = useTheme();
  const { sites } = useData();
  const { push } = useToast();
  const [fav, setFav] = useState(false);

  return (
    <header className="topbar">
      {narrow && (
        <button type="button" className="btn btn-ghost btn-icon" aria-label="Open navigation menu" aria-expanded={drawerOpen} onClick={onMenu}>
          <Menu size={18} aria-hidden="true" />
        </button>
      )}
      <button
        type="button"
        className="btn btn-ghost btn-icon max-sm:hidden"
        aria-label={fav ? "Remove from favorites" : "Add to favorites"}
        aria-pressed={fav}
        onClick={() => setFav((f) => !f)}
      >
        <Star size={16} aria-hidden="true" fill={fav ? "currentColor" : "none"} className={fav ? "text-brand" : ""} />
      </button>

      <div className="min-w-0 flex-1 sm:flex-none">
        <Popover
          label="Switch domain"
          width={288}
          renderTrigger={(p) => (
            <button type="button" className="btn btn-ghost min-w-0 px-2" {...p}>
              <span className="min-w-0 truncate font-semibold">{DOMAIN}</span>
              <span className="badge flex-none max-[480px]:hidden">free</span>
              <ChevronsUpDown size={14} aria-hidden="true" className="flex-none text-muted" />
            </button>
          )}
        >
          {({ close }) => (
            <div>
              <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted">Domains</p>
              <ul className="grid gap-1">
                {sites.map((s) => (
                  <li key={s.id}>
                    <Link to="/dashboard/dns" onClick={close} className="flex min-h-9 items-center justify-between gap-3 rounded-md px-2 py-1 text-fg no-underline hover:bg-hover">
                      <span className="truncate">{s.name}</span>
                      <span className={s.status === "Active" ? "badge badge-ok" : "badge badge-warn"}>{s.status}</span>
                    </Link>
                  </li>
                ))}
              </ul>
              <div className="mt-2 border-t border-line pt-2">
                <Link to="/dashboard/sites" onClick={close} className="link">
                  View all domains
                </Link>
              </div>
            </div>
          )}
        </Popover>
      </div>

      <div className="ml-auto flex flex-none items-center gap-1">
        <button type="button" className="btn btn-ghost max-sm:hidden" onClick={() => push({ title: "The AI assistant is not part of this prototype.", tone: "info" })}>
          <Sparkles size={16} aria-hidden="true" />
          <span className="max-md:sr-only">Ask AI</span>
        </button>
        <button type="button" className="btn btn-ghost max-[480px]:hidden" onClick={() => push({ title: "Support chat is not part of this prototype.", tone: "info" })}>
          <LifeBuoy size={16} aria-hidden="true" />
          <span className="max-md:sr-only">Support</span>
        </button>
        <Popover
          label="Account menu"
          align="right"
          width={264}
          renderTrigger={(p) => (
            <button type="button" className="btn btn-ghost btn-icon" aria-label="Account menu" {...p}>
              <CircleUser size={20} aria-hidden="true" />
            </button>
          )}
        >
          {({ close }) => (
            <div className="grid gap-3">
              <div className="min-w-0">
                <p className="truncate font-semibold">B@gardengateway.com</p>
                <p className="text-xs text-muted">Account owner</p>
              </div>
              <div>
                <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted">Appearance</p>
                <div className="seg w-full" role="group" aria-label="Theme">
                  {THEMES.map(({ v, label, Icon }) => (
                    <button key={v} type="button" className="flex-1" aria-pressed={pref === v} onClick={() => setPref(v)}>
                      <Icon size={14} aria-hidden="true" />
                      {label}
                    </button>
                  ))}
                </div>
              </div>
              <div className="grid gap-1 border-t border-line pt-3">
                <Link to="/dashboard/p/profile" onClick={close} className="flex min-h-9 items-center rounded-md px-2 text-fg no-underline hover:bg-hover">
                  My profile
                </Link>
                <button
                  type="button"
                  className="flex min-h-9 items-center rounded-md border-0 bg-transparent px-2 text-left text-fg hover:bg-hover"
                  onClick={() => {
                    close();
                    push({ title: "Signing out is disabled in this prototype.", tone: "info" });
                  }}
                >
                  Log out
                </button>
              </div>
            </div>
          )}
        </Popover>
      </div>
    </header>
  );
}
