import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  AlertTriangle,
  ArrowDown,
  ArrowUp,
  ArrowUpDown,
  BookOpen,
  CheckCircle2,
  Cloud,
  Download,
  Filter,
  Plus,
  Search,
  SlidersHorizontal,
  Trash2,
  Upload,
  X,
} from "lucide-react";
import { cn } from "@/utils/cn";
import { Badge, Button, Checkbox, Input, Segmented, Select, Textarea, Toggle } from "@/components/ui/primitives";
import { Alert, Card, CollapsibleCard, EmptyState, InfoTip, PageHeader } from "@/components/ui/layout";
import { Dialog, Popover, Tooltip, useToast } from "@/components/ui/overlays";
import { INITIAL_RECORDS, RECORD_TYPES, ZONE, displayName, toFqdn, ttlLabel, type DnsRecord, type RecordFormValues } from "@/data/records";
import { useDebounced, useLocalStorage } from "@/lib/hooks";
import { useRouter } from "@/lib/router";
import { ColumnResizer, useColumnWidths, type ColumnDef } from "@/components/ui/table";
import { DnsRecordForm } from "./DnsRecordForm";

type SortKey = "name" | "type" | "content"; // sortable columns
type ColKey = "proxy" | "ttl" | "comment" | "details";
type EditMode = "inline" | "dialog";

/** Column model: default widths + resize bounds. "fixed" columns have no drag handle. */
const COLUMN_DEFS: (ColumnDef & { label: string; optional?: ColKey })[] = [
  { key: "select", label: "Select", width: 48, fixed: true },
  { key: "warn", label: "Warnings", width: 32, fixed: true },
  { key: "name", label: "Name", width: 240, min: 140, max: 520 },
  { key: "type", label: "Type", width: 90, min: 70, max: 160 },
  { key: "content", label: "Content", width: 300, min: 160, max: 720 },
  { key: "proxy", label: "Proxy status", width: 140, min: 110, max: 220, optional: "proxy" },
  { key: "ttl", label: "TTL", width: 90, min: 70, max: 160, optional: "ttl" },
  { key: "comment", label: "Comment", width: 180, min: 100, max: 400, optional: "comment" },
  { key: "details", label: "Details", width: 120, min: 90, max: 240, optional: "details" },
  { key: "actions", label: "Actions", width: 88, fixed: true },
];
interface FilterRow {
  id: number;
  field: "name" | "type" | "content" | "comment";
  op: "contains" | "equals" | "startsWith";
  value: string;
}

const FIELD_OPTS = [
  { value: "name", label: "Name" },
  { value: "type", label: "Type" },
  { value: "content", label: "Content" },
  { value: "comment", label: "Comment" },
];
const OP_OPTS = [
  { value: "contains", label: "contains" },
  { value: "equals", label: "equals" },
  { value: "startsWith", label: "starts with" },
];

function matches(r: DnsRecord, f: FilterRow) {
  const hay = String(r[f.field] ?? "").toLowerCase();
  const v = f.value.trim().toLowerCase();
  if (!v) return true;
  return f.op === "contains" ? hay.includes(v) : f.op === "equals" ? hay === v : hay.startsWith(v);
}

export function DnsRecordsPage() {
  const { query } = useRouter();
  const { toast } = useToast();
  const [records, setRecords] = useLocalStorage<DnsRecord[]>("cfui.dns.records", INITIAL_RECORDS);
  const [search, setSearch] = useState(query.get("q") ?? "");
  const dq = useDebounced(search, 150);
  const [sort, setSort] = useState<{ key: SortKey; dir: "asc" | "desc" } | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [adding, setAdding] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState<string[] | null>(null);
  const [importOpen, setImportOpen] = useState(false);
  const [importText, setImportText] = useState("");
  const [bannerOpen, setBannerOpen] = useState(true);

  // filters: draft (in popover) vs applied
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [draft, setDraft] = useState<FilterRow[]>([{ id: 1, field: "name", op: "contains", value: "" }]);
  const [applied, setApplied] = useState<FilterRow[]>([]);

  const [displayOpen, setDisplayOpen] = useState(false);
  const [cols, setCols] = useLocalStorage<Record<ColKey, boolean>>("cfui.dns.cols", { proxy: true, ttl: true, comment: true, details: true });
  const [density, setDensity] = useLocalStorage<"comfortable" | "compact">("cfui.dns.density", "comfortable");
  const [editMode, setEditMode] = useLocalStorage<EditMode>("cfui.dns.editMode", "inline");

  // resizable columns
  const { widths, set: setWidth, reset: resetWidth, commit: commitWidths } = useColumnWidths("cfui.dns.widths", COLUMN_DEFS);
  const activeCols = useMemo(() => COLUMN_DEFS.filter((c) => !c.optional || cols[c.optional]), [cols]);
  const totalWidth = useMemo(() => activeCols.reduce((s, c) => s + (widths[c.key] ?? c.width), 0), [activeCols, widths]);

  // shadow on the sticky action column only when horizontally scrolled
  const scrollRef = useRef<HTMLDivElement>(null);
  const [scrolledX, setScrolledX] = useState(false);
  const onTableScroll = useCallback(() => {
    const el = scrollRef.current;
    if (!el) return;
    const overflow = el.scrollWidth - el.clientWidth - el.scrollLeft > 1;
    setScrolledX((s) => (s === overflow ? s : overflow));
  }, []);
  useEffect(() => {
    onTableScroll();
    const el = scrollRef.current;
    if (!el) return;
    const ro = new ResizeObserver(onTableScroll);
    ro.observe(el);
    return () => ro.disconnect();
  }, [onTableScroll, totalWidth]);

  const addBtn = useRef<HTMLButtonElement>(null);
  const searchRef = useRef<HTMLInputElement>(null);
  const editTrigger = useRef<HTMLElement | null>(null);

  const openEdit = useCallback((id: string) => {
    editTrigger.current = document.activeElement as HTMLElement;
    setEditingId(id);
    setAdding(false);
  }, []);
  const closeEdit = useCallback(() => {
    setEditingId(null);
    editTrigger.current?.focus?.();
  }, []);
  const editingRecord = useMemo(() => records.find((r) => r.id === editingId) ?? null, [records, editingId]);

  useEffect(() => {
    const q = query.get("q");
    if (q != null) setSearch(q);
  }, [query]);

  const visible = useMemo(() => {
    const s = dq.trim().toLowerCase();
    let out = records.filter((r) => (s ? [r.name, r.type, r.content, r.comment ?? ""].some((x) => x.toLowerCase().includes(s)) : true));
    out = out.filter((r) => applied.every((f) => matches(r, f)));
    if (sort) {
      const m = sort.dir === "asc" ? 1 : -1;
      out = [...out].sort((a, b) => a[sort.key].localeCompare(b[sort.key]) * m);
    }
    return out;
  }, [records, dq, applied, sort]);

  const allSelected = visible.length > 0 && visible.every((r) => selected.has(r.id));
  const someSelected = visible.some((r) => selected.has(r.id));

  const toggleSort = (key: SortKey) =>
    setSort((s) => (!s || s.key !== key ? { key, dir: "asc" } : s.dir === "asc" ? { key, dir: "desc" } : null));

  const save = useCallback(
    async (v: RecordFormValues, id?: string) => {
      await new Promise((r) => setTimeout(r, 350)); // simulate network latency
      const rec: DnsRecord = {
        id: id ?? `r${Date.now()}`,
        type: v.type,
        name: toFqdn(v.name),
        content: v.content,
        proxied: v.proxied,
        ttl: Number(v.ttl),
        priority: v.type === "MX" || v.type === "SRV" ? Number(v.priority) : undefined,
        comment: v.comment || undefined,
        updatedAt: new Date().toISOString().slice(0, 10),
      };
      setRecords((rs) => (id ? rs.map((r) => (r.id === id ? rec : r)) : [rec, ...rs]));
      toast({ tone: "success", title: id ? "Record saved" : "Record added", description: `${rec.type} ${rec.name} → ${rec.content}` });
      setAdding(false);
      setEditingId(null);
      if (!id) addBtn.current?.focus();
    },
    [setRecords, toast]
  );

  const doDelete = (ids: string[]) => {
    const removed = records.filter((r) => ids.includes(r.id));
    setRecords((rs) => rs.filter((r) => !ids.includes(r.id)));
    setSelected(new Set());
    setEditingId(null);
    setConfirmDelete(null);
    toast({
      tone: "info",
      title: `${removed.length} record${removed.length > 1 ? "s" : ""} deleted`,
      action: { label: "Undo", onClick: () => setRecords((rs) => [...removed, ...rs]) },
    });
  };

  const exportZone = () => {
    const lines = [`;; Zone file export for ${ZONE}`, `$ORIGIN ${ZONE}.`, ...records.map((r) => `${r.name}.\t${r.ttl === 1 ? 300 : r.ttl}\tIN\t${r.type}\t${r.priority != null ? r.priority + " " : ""}${r.content}`)];
    const blob = new Blob([lines.join("\n")], { type: "text/plain" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${ZONE}.txt`;
    a.click();
    URL.revokeObjectURL(url);
    toast({ tone: "success", title: "Export started", description: `${records.length} records exported to ${ZONE}.txt` });
  };

  const runImport = () => {
    const parsed: DnsRecord[] = [];
    importText.split("\n").forEach((line, i) => {
      const parts = line.trim().split(/\s+/);
      if (parts.length < 4 || line.trim().startsWith(";")) return;
      const [name, , , type, ...rest] = parts;
      if (!RECORD_TYPES.some((t) => t.value === type)) return;
      parsed.push({ id: `imp${Date.now()}${i}`, name: name.replace(/\.$/, ""), type: type as DnsRecord["type"], content: rest.join(" "), proxied: false, ttl: 1, updatedAt: new Date().toISOString().slice(0, 10) });
    });
    if (!parsed.length) {
      toast({ tone: "error", title: "Nothing imported", description: "No valid lines found. Expected: name TTL IN TYPE content" });
      return;
    }
    setRecords((rs) => [...parsed, ...rs]);
    setImportOpen(false);
    setImportText("");
    toast({ tone: "success", title: `${parsed.length} records imported` });
  };

  const rowPad = density === "compact" ? "py-1.5" : "py-2.5";
  const activeFilterCount = applied.filter((f) => f.value.trim()).length;

  const SortBtn = ({ k, children }: { k: SortKey; children: React.ReactNode }) => {
    const active = sort?.key === k;
    const Icon = !active ? ArrowUpDown : sort!.dir === "asc" ? ArrowUp : ArrowDown;
    return (
      <button
        type="button"
        onClick={() => toggleSort(k)}
        aria-sort={active ? (sort!.dir === "asc" ? "ascending" : "descending") : "none"}
        className="inline-flex items-center gap-1 h-6 -ml-1 px-1 rounded-xs font-medium text-fg hover:bg-surface-3"
      >
        {children}
        <Icon className={cn("size-3.5", active ? "text-fg" : "text-fg-3")} aria-hidden />
      </button>
    );
  };

  return (
    <>
      <PageHeader
        title={`DNS records for ${ZONE}`}
        description="Manage how the Internet finds your web content, verifies services, and routes traffic."
        actions={
          <>
            <Badge className="h-7 px-2 text-xs">DNS Setup: Full</Badge>
            <Button icon={<BookOpen className="size-4" />} onClick={() => (window.location.hash = "#/guide/tables")}>
              DNS documentation
            </Button>
          </>
        }
      />

      {bannerOpen && (
        <Alert tone="warning" className="mb-4" onDismiss={() => setBannerOpen(false)}>
          <strong>{ZONE}</strong> is <strong>pending</strong> until you complete the instructions on the <a href="#/">Overview page</a> and we are able to verify ownership. Learn more about{" "}
          <a href="#/guide/readme">pending domains</a>.
        </Alert>
      )}

      <CollapsibleCard
        className="mb-6"
        defaultOpen={false}
        title="Recommendations"
        meta={
          <span className="inline-flex items-center gap-1 text-xs text-fg-3">
            <CheckCircle2 className="size-3.5 text-success" aria-hidden /> All set
          </span>
        }
      >
        <EmptyState icon={<CheckCircle2 />} title="No recommendations" description="We'll suggest fixes here when records look misconfigured (e.g. missing SPF or exposed origin)." />
      </CollapsibleCard>

      {/* toolbar: search grows, actions wrap onto next line on narrow */}
      <div className="flex flex-col lg:flex-row lg:items-center gap-3 mb-4">
        <div className="flex-1 min-w-0 lg:max-w-[520px]">
          <Input
            ref={searchRef}
            aria-label="Search DNS records"
            placeholder="Search DNS records"
            leading={<Search className="size-4" />}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            trailing={search ? <Button variant="ghost" size="sm" square aria-label="Clear search" onClick={() => { setSearch(""); searchRef.current?.focus(); }} icon={<X className="size-4" />} /> : undefined}
          />
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Popover
            open={filtersOpen}
            onOpenChange={setFiltersOpen}
            width={560}
            label="Filters"
            trigger={
              <Button icon={<Filter className="size-4" />}>
                Filters
                {activeFilterCount > 0 && <Badge tone="info">{activeFilterCount}</Badge>}
              </Button>
            }
          >
            <form
              className="p-4"
              onSubmit={(e) => {
                e.preventDefault();
                setApplied(draft.filter((d) => d.value.trim()));
                setFiltersOpen(false);
              }}
            >
              <div className="flex items-center justify-between mb-3">
                <h3 className="text-base font-semibold text-fg">Filters</h3>
                <Button variant="ghost" size="sm" square aria-label="Close filters" onClick={() => setFiltersOpen(false)} icon={<X className="size-4" />} />
              </div>
              <div className="space-y-2">
                {draft.map((f, i) => (
                  <div key={f.id} className="grid grid-cols-[1fr_auto] sm:grid-cols-[120px_130px_1fr_auto] gap-2 items-center">
                    <Select aria-label={`Filter ${i + 1} field`} value={f.field} onChange={(e) => setDraft((d) => d.map((x) => (x.id === f.id ? { ...x, field: e.target.value as FilterRow["field"] } : x)))} options={FIELD_OPTS} className="col-span-1" />
                    <Select aria-label={`Filter ${i + 1} operator`} value={f.op} onChange={(e) => setDraft((d) => d.map((x) => (x.id === f.id ? { ...x, op: e.target.value as FilterRow["op"] } : x)))} options={OP_OPTS} className="row-start-2 sm:row-start-auto" />
                    <Input aria-label={`Filter ${i + 1} value`} placeholder={f.field === "name" ? "hostname" : f.field === "type" ? "A, TXT…" : "value"} value={f.value} onChange={(e) => setDraft((d) => d.map((x) => (x.id === f.id ? { ...x, value: e.target.value } : x)))} className="row-start-2 sm:row-start-auto col-span-1" />
                    <Button variant="ghost" size="md" square aria-label="Remove filter" disabled={draft.length === 1} onClick={() => setDraft((d) => d.filter((x) => x.id !== f.id))} icon={<Trash2 className="size-4" />} className="row-start-1 sm:row-start-auto" />
                  </div>
                ))}
              </div>
              <div className="flex items-center justify-between gap-3 mt-3 pt-3 border-t border-line">
                <Button variant="ghost" size="sm" icon={<Plus className="size-4" />} onClick={() => setDraft((d) => [...d, { id: Date.now(), field: "name", op: "contains", value: "" }])}>
                  Add filter
                </Button>
                <div className="flex items-center gap-3">
                  <span className="hidden sm:inline text-xs text-fg-3">Press Enter to apply</span>
                  {applied.length > 0 && (
                    <Button variant="ghost" size="sm" onClick={() => { setApplied([]); setDraft([{ id: Date.now(), field: "name", op: "contains", value: "" }]); }}>
                      Clear
                    </Button>
                  )}
                  <Button variant="primary" size="sm" type="submit" disabled={!draft.some((d) => d.value.trim())}>
                    Apply
                  </Button>
                </div>
              </div>
            </form>
          </Popover>

          <Popover open={displayOpen} onOpenChange={setDisplayOpen} width={300} label="Display options" trigger={<Button icon={<SlidersHorizontal className="size-4" />}>Display options</Button>}>
            <div className="p-4 space-y-4">
              <div>
                <p className="text-sm font-semibold text-fg mb-2">Columns</p>
                <div className="space-y-2">
                  {(["proxy", "ttl", "comment", "details"] as ColKey[]).map((c) => (
                    <Checkbox key={c} checked={cols[c]} onChange={(v) => setCols((s) => ({ ...s, [c]: v }))} label={{ proxy: "Proxy status", ttl: "TTL", comment: "Comment", details: "Details" }[c]} />
                  ))}
                </div>
              </div>
              <div>
                <p className="text-sm font-semibold text-fg mb-2">Density</p>
                <Toggle size="sm" checked={density === "compact"} onChange={(v) => setDensity(v ? "compact" : "comfortable")} label="Compact rows" />
              </div>
              <div>
                <p className="text-sm font-semibold text-fg mb-2">Edit records in</p>
                <Segmented
                  ariaLabel="Edit mode"
                  size="sm"
                  value={editMode}
                  onChange={(m) => { setEditMode(m); setEditingId(null); }}
                  options={[
                    { value: "inline", label: "Expanded row", title: "Row expands into a form; table stays visible" },
                    { value: "dialog", label: "Dialog", title: "Form opens in a modal dialog" },
                  ]}
                />
              </div>
              <div className="pt-1 border-t border-line">
                <Button size="sm" variant="ghost" onClick={() => resetWidth()}>Reset column widths</Button>
              </div>
            </div>
          </Popover>

          <Button icon={<Upload className="size-4" />} onClick={() => setImportOpen(true)}>
            Import
          </Button>
          <Button icon={<Download className="size-4" />} onClick={exportZone}>
            Export
          </Button>
          <Button ref={addBtn} variant="primary" icon={<Plus className="size-4" />} onClick={() => { setAdding(true); setEditingId(null); }} aria-expanded={adding} disabled={adding}>
            Add record
          </Button>
        </div>
      </div>

      {applied.length > 0 && (
        <div className="flex flex-wrap items-center gap-2 mb-3 text-sm">
          <span className="text-fg-3">Active filters:</span>
          {applied.map((f) => (
            <span key={f.id} className="inline-flex items-center gap-1 h-7 pl-2.5 pr-1 rounded-full bg-primary-soft text-primary-text">
              {FIELD_OPTS.find((o) => o.value === f.field)?.label} {OP_OPTS.find((o) => o.value === f.op)?.label} “{f.value}”
              <button type="button" aria-label="Remove filter" onClick={() => setApplied((a) => a.filter((x) => x.id !== f.id))} className="size-5 inline-flex items-center justify-center rounded-full hover:bg-primary/15">
                <X className="size-3" />
              </button>
            </span>
          ))}
        </div>
      )}

      {adding && (
        <Card className="mb-4 border-primary/40">
          <div className="px-4 sm:px-5 py-4 border-b border-line flex items-center justify-between">
            <h2 className="text-lg font-semibold text-fg">Add record</h2>
            <Button variant="ghost" size="sm" square aria-label="Cancel" onClick={() => setAdding(false)} icon={<X className="size-4" />} />
          </div>
          <div className="px-4 sm:px-5 py-4">
            <DnsRecordForm idPrefix="add" existing={records} onCancel={() => { setAdding(false); addBtn.current?.focus(); }} onSave={(v) => save(v)} />
          </div>
        </Card>
      )}

      <Card>
        <div className="px-4 sm:px-5 py-3 border-b border-line text-sm text-fg-2 flex flex-wrap items-center justify-between gap-2">
          <span>
            You have used <strong className="text-fg">{records.length} of 200</strong> available DNS records for this domain.
          </span>
          {(dq || applied.length > 0) && <span className="text-fg-3">{visible.length} match{visible.length === 1 ? "" : "es"}</span>}
        </div>

        {visible.length === 0 ? (
          <EmptyState
            icon={<Search />}
            title={records.length === 0 ? "No DNS records yet" : "No records match"}
            description={records.length === 0 ? "Add your first record to start routing traffic." : "Try a different search term or clear the active filters."}
            action={
              records.length === 0 ? (
                <Button variant="primary" icon={<Plus className="size-4" />} onClick={() => setAdding(true)}>Add record</Button>
              ) : (
                <Button onClick={() => { setSearch(""); setApplied([]); }}>Clear search & filters</Button>
              )
            }
          />
        ) : (
          <>
            {/* ≥ sm: table with horizontal scroll contained in the card */}
            <div className="hidden sm:block overflow-x-auto relative" ref={scrollRef} onScroll={onTableScroll}>
              <table className="text-base border-collapse" style={{ tableLayout: "fixed", width: "100%", minWidth: totalWidth }}>
                <caption className="sr-only">DNS records. Drag column edges or use arrow keys on the handles to resize.</caption>
                <colgroup>
                  {activeCols.map((c) => (
                    <col key={c.key} style={{ width: widths[c.key] }} />
                  ))}
                </colgroup>
                <thead>
                  <tr className="bg-surface-2 text-sm text-fg">
                    {activeCols.map((c) => {
                      const isLast = c.key === "actions";
                      let inner: React.ReactNode;
                      if (c.key === "select")
                        inner = <Checkbox ariaLabel="Select all records" checked={allSelected} indeterminate={!allSelected && someSelected} onChange={(v) => setSelected(v ? new Set(visible.map((r) => r.id)) : new Set())} />;
                      else if (c.key === "warn") inner = <span className="sr-only">Warnings</span>;
                      else if (c.key === "name")
                        inner = (
                          <>
                            <SortBtn k="name">Name</SortBtn> <InfoTip text="The hostname (domain or subdomain) this record applies to." />
                          </>
                        );
                      else if (c.key === "type") inner = <SortBtn k="type">Type</SortBtn>;
                      else if (c.key === "content") inner = <SortBtn k="content">Content</SortBtn>;
                      else if (isLast) inner = <span className="sr-only">Actions</span>;
                      else inner = c.label;
                      return (
                        <th
                          key={c.key}
                          scope="col"
                          className={cn(
                            "relative py-2 text-left font-medium whitespace-nowrap overflow-hidden",
                            c.key === "warn" ? "px-1" : "px-3",
                            isLast && "sticky right-0 z-[2] bg-surface-2 text-right border-l border-line"
                          )}
                        >
                          {inner}
                          {!c.fixed && <ColumnResizer colKey={c.key} label={c.label} width={widths[c.key]} onResize={setWidth} onCommit={commitWidths} onReset={resetWidth} />}
                        </th>
                      );
                    })}
                  </tr>
                </thead>
                <tbody>
                  {visible.map((r) => {
                    const dn = displayName(r.name);
                    const editing = editMode === "inline" && editingId === r.id;
                    if (editing) {
                      return (
                        <tr key={r.id} className="border-t border-line bg-primary-soft/30">
                          <td colSpan={activeCols.length} className="px-4 sm:px-5 py-4">
                            <DnsRecordForm idPrefix={`edit-${r.id}`} initial={r} existing={records} editingId={r.id} onCancel={closeEdit} onSave={(v) => save(v, r.id)} onDelete={() => setConfirmDelete([r.id])} />
                          </td>
                        </tr>
                      );
                    }
                    const isSel = selected.has(r.id);
                    // solid backgrounds (no alpha) so the sticky action cell can inherit them opaquely
                    const rowBg = isSel ? "bg-primary-soft" : "bg-surface hover:bg-surface-2";
                    const cell = (key: string): React.ReactNode => {
                      switch (key) {
                        case "select":
                          return <Checkbox ariaLabel={`Select ${r.type} ${r.name}`} checked={isSel} onChange={(v) => setSelected((s) => { const n = new Set(s); v ? n.add(r.id) : n.delete(r.id); return n; })} />;
                        case "warn":
                          return r.warning ? (
                            <Tooltip content={r.warning}>
                              <button type="button" aria-label="Warning" className="inline-flex size-6 items-center justify-center text-warning"><AlertTriangle className="size-4" /></button>
                            </Tooltip>
                          ) : null;
                        case "name":
                          return (
                            <span className="block truncate" title={r.name}>
                              <span className="text-fg">{dn.sub}</span>
                              <span className={dn.sub ? "text-fg-3" : "text-fg"}>{dn.zone}</span>
                            </span>
                          );
                        case "type":
                          return r.type;
                        case "content":
                          return <span className="block truncate font-mono text-sm" title={r.content}>{r.content}</span>;
                        case "proxy":
                          return RECORD_TYPES.find((t) => t.value === r.type)?.proxyable ? (
                            <span className="inline-flex items-center gap-1.5 truncate max-w-full">
                              <Cloud className={cn("size-4 shrink-0", r.proxied ? "text-brand fill-brand/20" : "text-fg-3")} aria-hidden />
                              {r.proxied ? "Proxied" : "DNS only"}
                            </span>
                          ) : (
                            <span className="text-fg-2">DNS only</span>
                          );
                        case "ttl":
                          return <span className="text-fg-2">{ttlLabel(r.ttl)}</span>;
                        case "comment":
                          return <span className="block truncate text-fg-2">{r.comment ?? "—"}</span>;
                        case "details":
                          return r.priority != null ? <Badge className="h-6 px-2 text-xs">Priority {r.priority}</Badge> : <span className="text-fg-3">—</span>;
                        case "actions":
                          return (
                            <Button variant="ghost" size="sm" onClick={() => openEdit(r.id)} aria-label={`Edit ${r.type} ${r.name}`} aria-expanded={editMode === "inline" ? editingId === r.id : undefined}>
                              Edit
                            </Button>
                          );
                      }
                      return null;
                    };
                    return (
                      <tr key={r.id} className={cn("border-t border-line transition-colors", rowBg)}>
                        {activeCols.map((c) => {
                          const isLast = c.key === "actions";
                          return (
                            <td
                              key={c.key}
                              className={cn(
                                "whitespace-nowrap overflow-hidden",
                                c.key === "warn" ? "px-1" : "px-3",
                                rowPad,
                                isLast && cn("sticky right-0 z-[1] text-right bg-inherit border-l", scrolledX ? "border-line shadow-[-6px_0_8px_-6px_rgba(0,0,0,0.18)]" : "border-transparent")
                              )}
                            >
                              {cell(c.key)}
                            </td>
                          );
                        })}
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            {/* < sm: card list – no horizontal scroll, labels inline */}
            <ul className="sm:hidden divide-y divide-line">
              {visible.map((r) => {
                const dn = displayName(r.name);
                const editing = editMode === "inline" && editingId === r.id;
                return (
                  <li key={r.id} className={cn("px-4 py-3", editing && "bg-primary-soft/30")}>
                    {editing ? (
                      <DnsRecordForm idPrefix={`m-edit-${r.id}`} initial={r} existing={records} editingId={r.id} onCancel={closeEdit} onSave={(v) => save(v, r.id)} onDelete={() => setConfirmDelete([r.id])} />
                    ) : (
                      <div className="flex items-start gap-3">
                        <Checkbox ariaLabel={`Select ${r.type} ${r.name}`} checked={selected.has(r.id)} onChange={(v) => setSelected((s) => { const n = new Set(s); v ? n.add(r.id) : n.delete(r.id); return n; })} />
                        <div className="min-w-0 flex-1">
                          <div className="flex items-center gap-2 min-w-0">
                            <Badge>{r.type}</Badge>
                            <span className="truncate text-base"><span className="text-fg">{dn.sub}</span><span className={dn.sub ? "text-fg-3" : "text-fg"}>{dn.zone}</span></span>
                            {r.warning && <AlertTriangle className="size-4 text-warning shrink-0" aria-label="Warning" />}
                          </div>
                          <p className="font-mono text-sm text-fg-2 break-all mt-1">{r.content}</p>
                          <p className="text-xs text-fg-3 mt-1 flex flex-wrap gap-x-3">
                            <span>{r.proxied ? "Proxied" : "DNS only"}</span>
                            <span>TTL {ttlLabel(r.ttl)}</span>
                            {r.priority != null && <span>Priority {r.priority}</span>}
                          </p>
                        </div>
                        <Button variant="ghost" size="sm" onClick={() => openEdit(r.id)} aria-label={`Edit ${r.type} ${r.name}`}>Edit</Button>
                      </div>
                    )}
                  </li>
                );
              })}
            </ul>
          </>
        )}

        <div className="px-4 sm:px-5 py-3 border-t border-line text-sm text-fg-2">
          Showing {visible.length ? 1 : 0}–{visible.length} of {visible.length}
        </div>
      </Card>

      {/* floating bulk-action bar: appears only when selection exists */}
      {selected.size > 0 && (
        <div role="region" aria-label="Bulk actions" className="fixed bottom-4 left-1/2 -translate-x-1/2 z-40 w-[calc(100%_-_32px)] max-w-[520px] anim-slide-up">
          <div className="flex items-center gap-2 px-3 py-2 rounded-md bg-fg text-fg-inverse shadow-3">
            <span className="text-sm font-medium flex-1 min-w-0 truncate">{selected.size} selected</span>
            <Button size="sm" variant="ghost" className="text-fg-inverse hover:bg-white/10 hover:text-fg-inverse" onClick={() => setSelected(new Set())}>
              Clear
            </Button>
            <Button size="sm" variant="danger" icon={<Trash2 className="size-4" />} onClick={() => setConfirmDelete([...selected])}>
              Delete
            </Button>
          </div>
        </div>
      )}

      <Dialog
        open={!!confirmDelete}
        onClose={() => setConfirmDelete(null)}
        tone="danger"
        size="sm"
        title={`Delete ${confirmDelete?.length === 1 ? "record" : `${confirmDelete?.length} records`}?`}
        description="Deleting DNS records can take your services offline. Resolvers may cache old answers for up to the TTL."
        footer={
          <>
            <Button onClick={() => setConfirmDelete(null)}>Cancel</Button>
            <Button variant="danger" data-autofocus onClick={() => confirmDelete && doDelete(confirmDelete)}>
              Delete
            </Button>
          </>
        }
      >
        <ul className="text-sm font-mono text-fg-2 space-y-1 max-h-40 overflow-auto">
          {records.filter((r) => confirmDelete?.includes(r.id)).map((r) => (
            <li key={r.id} className="truncate">{r.type} {r.name} → {r.content}</li>
          ))}
        </ul>
      </Dialog>

      {/* dialog edit mode: same form, modal container; focus returns to the Edit button on close */}
      {editMode === "dialog" && editingRecord && (
        <Dialog
          open
          onClose={closeEdit}
          size="lg"
          title={`Edit ${editingRecord.type} record`}
          description={editingRecord.name}
        >
          <div className="pb-3">
            <DnsRecordForm idPrefix={`dlg-${editingRecord.id}`} initial={editingRecord} existing={records} editingId={editingRecord.id} onCancel={closeEdit} onSave={(v) => save(v, editingRecord.id)} onDelete={() => setConfirmDelete([editingRecord.id])} />
          </div>
        </Dialog>
      )}

      <Dialog
        open={importOpen}
        onClose={() => setImportOpen(false)}
        title="Import DNS records"
        description="Paste BIND zone-file lines. One record per line: name TTL IN TYPE content."
        footer={
          <>
            <Button onClick={() => setImportOpen(false)}>Cancel</Button>
            <Button variant="primary" onClick={runImport} disabled={!importText.trim()}>Import</Button>
          </>
        }
      >
        <Textarea aria-label="Zone file content" rows={6} value={importText} onChange={(e) => setImportText(e.target.value)} placeholder={`api.${ZONE}.\t300\tIN\tA\t203.0.113.10`} className="font-mono text-sm" />
        <p className="text-xs text-fg-3 mt-2">Pasting is allowed everywhere. Imported records are added as DNS-only with Auto TTL.</p>
      </Dialog>
    </>
  );
}
