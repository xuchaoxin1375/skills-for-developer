import { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { ArrowRight, CornerDownLeft, FileText, Search, Network } from "lucide-react";
import { cn } from "@/utils/cn";
import { flatNav } from "@/data/nav";
import { INITIAL_RECORDS } from "@/data/records";
import { useRouter } from "@/lib/router";
import { useShell } from "./ShellContext";
import { Kbd } from "@/components/ui/layout";

interface Item {
  label: string;
  sub?: string;
  path: string;
  group: string;
  icon: React.ReactNode;
}

export function CommandPalette() {
  const { paletteOpen, setPaletteOpen } = useShell();
  const { navigate } = useRouter();
  const [q, setQ] = useState("");
  const [idx, setIdx] = useState(0);
  const input = useRef<HTMLInputElement>(null);
  const list = useRef<HTMLUListElement>(null);

  const all = useMemo<Item[]>(
    () => [
      ...flatNav().map((n) => ({ ...n, icon: <FileText /> })),
      ...INITIAL_RECORDS.map((r) => ({ label: `${r.type} ${r.name}`, sub: r.content, path: `/dns/records?q=${encodeURIComponent(r.name)}`, group: "DNS records", icon: <Network /> })),
    ],
    []
  );

  const results = useMemo(() => {
    const s = q.trim().toLowerCase();
    const pool = s ? all.filter((i) => i.label.toLowerCase().includes(s) || i.sub?.toLowerCase().includes(s)) : all.slice(0, 10);
    return pool.slice(0, 12);
  }, [q, all]);

  useEffect(() => {
    if (paletteOpen) {
      setQ("");
      setIdx(0);
      requestAnimationFrame(() => input.current?.focus());
      const prev = document.body.style.overflow;
      document.body.style.overflow = "hidden";
      return () => {
        document.body.style.overflow = prev;
      };
    }
  }, [paletteOpen]);

  useEffect(() => setIdx(0), [q]);

  useEffect(() => {
    const el = list.current?.children[idx] as HTMLElement | undefined;
    el?.scrollIntoView({ block: "nearest" });
  }, [idx]);

  if (!paletteOpen) return null;

  const go = (it: Item) => {
    navigate(it.path);
    setPaletteOpen(false);
  };

  const onKey = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setIdx((i) => Math.min(i + 1, results.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setIdx((i) => Math.max(i - 1, 0));
    } else if (e.key === "Enter" && results[idx]) {
      e.preventDefault();
      go(results[idx]);
    } else if (e.key === "Escape") {
      setPaletteOpen(false);
    }
  };

  let lastGroup = "";
  return createPortal(
    <div className="fixed inset-0 z-[90] flex items-start justify-center p-3 sm:pt-[12vh]">
      <div className="absolute inset-0 bg-[var(--c-overlay)] anim-fade" onClick={() => setPaletteOpen(false)} aria-hidden />
      <div role="dialog" aria-modal="true" aria-label="Quick search" className="relative w-full max-w-[640px] bg-surface border border-line rounded-lg shadow-3 anim-pop overflow-hidden" onKeyDown={onKey}>
        <div className="flex items-center gap-3 px-4 h-14 border-b border-line">
          <Search className="size-5 text-fg-3 shrink-0" aria-hidden />
          <input
            ref={input}
            role="combobox"
            aria-expanded
            aria-controls="palette-list"
            aria-activedescendant={results[idx] ? `palette-opt-${idx}` : undefined}
            aria-autocomplete="list"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search pages, DNS records, or ask AI…"
            className="flex-1 min-w-0 bg-transparent text-lg text-fg placeholder:text-fg-3 outline-none"
          />
          <Kbd>Esc</Kbd>
        </div>
        <ul id="palette-list" ref={list} role="listbox" className="max-h-[min(60vh,420px)] overflow-y-auto p-2">
          {results.length === 0 && <li className="px-3 py-8 text-center text-fg-3 text-base">No results for “{q}”.</li>}
          {results.map((it, i) => {
            const showGroup = it.group !== lastGroup;
            lastGroup = it.group;
            return (
              <li key={it.path + it.label} id={`palette-opt-${i}`} role="option" aria-selected={i === idx}>
                {showGroup && <div className="px-2 pt-2 pb-1 text-2xs font-semibold uppercase tracking-wide text-fg-3">{it.group}</div>}
                <button
                  type="button"
                  tabIndex={-1}
                  onMouseMove={() => setIdx(i)}
                  onClick={() => go(it)}
                  className={cn("w-full flex items-center gap-3 h-11 px-2.5 rounded-sm text-left", i === idx ? "bg-primary-soft text-fg" : "text-fg hover:bg-surface-2")}
                >
                  <span className="text-fg-3 [&>svg]:size-4 shrink-0">{it.icon}</span>
                  <span className="flex-1 min-w-0">
                    <span className="block text-base truncate">{it.label}</span>
                    {it.sub && <span className="block text-xs text-fg-3 truncate font-mono">{it.sub}</span>}
                  </span>
                  {i === idx ? <CornerDownLeft className="size-4 text-fg-3" aria-hidden /> : <ArrowRight className="size-4 text-transparent" aria-hidden />}
                </button>
              </li>
            );
          })}
        </ul>
        <div className="flex items-center gap-4 px-4 h-10 border-t border-line text-xs text-fg-3 bg-surface-2/60">
          <span className="flex items-center gap-1"><Kbd>↑</Kbd><Kbd>↓</Kbd> navigate</span>
          <span className="flex items-center gap-1"><Kbd>↵</Kbd> open</span>
          <span className="hidden sm:flex items-center gap-1"><Kbd>[</Kbd> toggle sidebar</span>
        </div>
      </div>
    </div>,
    document.body
  );
}
