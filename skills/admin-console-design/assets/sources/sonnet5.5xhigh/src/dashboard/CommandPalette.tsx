import { useEffect, useId, useMemo, useState, type KeyboardEvent } from "react";
import { CornerDownLeft, Search, type LucideIcon } from "lucide-react";
import { Modal } from "@/ui/Modal";

export interface Command {
  id: string;
  label: string;
  group: string;
  icon: LucideIcon;
  keywords?: string;
  run: () => void;
}

function Body({ commands, onClose }: { commands: Command[]; onClose: () => void }) {
  const [q, setQ] = useState("");
  const [idx, setIdx] = useState(0);
  const listId = useId();

  const items = useMemo(() => {
    const needle = q.trim().toLowerCase();
    return commands.filter((c) => `${c.label} ${c.group} ${c.keywords ?? ""}`.toLowerCase().includes(needle));
  }, [q, commands]);

  useEffect(() => setIdx(0), [q]);
  useEffect(() => {
    document.getElementById(`${listId}-${idx}`)?.scrollIntoView({ block: "nearest" });
  }, [idx, listId]);

  const run = (c: Command) => {
    onClose();
    c.run();
  };
  const onKey = (e: KeyboardEvent) => {
    if (!items.length) return;
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setIdx((i) => (i + 1) % items.length);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setIdx((i) => (i - 1 + items.length) % items.length);
    } else if (e.key === "Enter") {
      e.preventDefault();
      run(items[idx]);
    }
  };

  return (
    <div>
      <div className="flex items-center gap-3 border-b border-line p-4">
        <Search size={18} aria-hidden="true" className="flex-none text-muted" />
        <input
          data-autofocus
          type="text"
          role="combobox"
          aria-expanded="true"
          aria-controls={listId}
          aria-autocomplete="list"
          aria-activedescendant={items[idx] ? `${listId}-${idx}` : undefined}
          aria-label="Search pages and actions"
          placeholder="Search pages and actions…"
          autoComplete="off"
          spellCheck={false}
          className="input"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={onKey}
        />
      </div>
      <ul id={listId} role="listbox" aria-label="Results" className="max-h-80 overflow-auto p-2">
        {items.length === 0 && <li className="px-3 py-6 text-center text-muted">No results for “{q}”.</li>}
        {items.map((c, i) => (
          <li
            key={c.id}
            id={`${listId}-${i}`}
            role="option"
            aria-selected={i === idx}
            className="flex min-h-10 cursor-pointer items-center gap-3 rounded-md px-3 py-2 aria-selected:bg-active"
            onMouseMove={() => setIdx(i)}
            onClick={() => run(c)}
          >
            <c.icon size={16} aria-hidden="true" className="flex-none text-muted" />
            <span className="min-w-0 flex-1 truncate">{c.label}</span>
            <span className="flex-none text-xs text-muted">{c.group}</span>
          </li>
        ))}
      </ul>
      <p className="flex flex-wrap items-center gap-x-4 gap-y-1 border-t border-line px-4 py-3 text-xs text-muted">
        <span>
          <kbd className="kbd">↑</kbd> <kbd className="kbd">↓</kbd> to navigate
        </span>
        <span className="inline-flex items-center gap-1">
          <kbd className="kbd">
            <CornerDownLeft size={12} aria-label="Enter" />
          </kbd>
          to select
        </span>
        <span>
          <kbd className="kbd">Esc</kbd> to close
        </span>
      </p>
    </div>
  );
}

export function CommandPalette({ open, onClose, commands }: { open: boolean; onClose: () => void; commands: Command[] }) {
  return (
    <Modal open={open} onClose={onClose} label="Quick search" kind="palette">
      <Body commands={commands} onClose={onClose} />
    </Modal>
  );
}
