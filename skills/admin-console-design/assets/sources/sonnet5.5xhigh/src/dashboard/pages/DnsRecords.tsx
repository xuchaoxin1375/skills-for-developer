import { Fragment, useCallback, useDeferredValue, useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowDown,
  ArrowUp,
  ArrowUpDown,
  BookOpen,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  CircleCheck,
  Cloud,
  Download,
  ExternalLink,
  Funnel,
  Pencil,
  Plus,
  Search,
  SlidersHorizontal,
  Trash,
  TriangleAlert,
  Upload,
  X,
} from "lucide-react";
import { Link, setNavGuard, type Route } from "@/lib/route";
import { useBelow, usePersisted } from "@/lib/hooks";
import { ConfirmDialog, Modal } from "@/ui/Modal";
import { Popover } from "@/ui/Popover";
import { InfoTip, PageHeader, Select } from "@/ui/controls";
import { ResizeHandle, useColumnWidths, useScrollAffordance, type ColSpec } from "@/ui/columns";
import { useToast } from "@/ui/Toast";
import { cn } from "@/utils/cn";
import { DOMAIN, fqdn, ttlLabel, useData, type DnsRecord, type RecordType } from "../data";
import { RecordEditor } from "../RecordEditor";
import { PROXYABLE } from "../recordModel";

/* ------------------------------ 列定义 / 排序 / 筛选 ------------------------------ */

type SortKey = "name" | "type" | "content" | "proxy" | "ttl" | "comment" | "modified";
type ColId = "name" | "type" | "content" | "proxy" | "ttl" | "comment" | "details" | "modified";
interface ColDef extends ColSpec {
  id: ColId;
  label: string;
  sort?: SortKey;
  tip?: string;
  /** 可在「Display options」中隐藏 */
  hideable?: boolean;
}

const COLS: ColDef[] = [
  { id: "name", label: "Name", min: 120, def: 200, sort: "name", tip: "The hostname (domain or subdomain) this record applies to." },
  { id: "type", label: "Type", min: 64, def: 72, sort: "type" },
  { id: "content", label: "Content", min: 120, def: 240, sort: "content", tip: "The value the record points to, such as an IP address or target hostname." },
  { id: "proxy", label: "Proxy status", min: 104, def: 128, sort: "proxy", hideable: true },
  { id: "ttl", label: "TTL", min: 64, def: 72, sort: "ttl", hideable: true },
  { id: "comment", label: "Comment", min: 96, def: 136, sort: "comment", hideable: true },
  { id: "details", label: "Details", min: 88, def: 104, hideable: true },
  { id: "modified", label: "Modified", min: 104, def: 128, sort: "modified", hideable: true },
];
/** 固定列：勾选 44 + 状态 36 + 操作 144 */
const SEL_W = 44;
const STATUS_W = 36;
const ACT_W = 144;
const FIXED_EXTRA = SEL_W + STATUS_W + ACT_W;
const DEFAULT_VISIBLE: Record<ColId, boolean> = { name: true, type: true, content: true, proxy: true, ttl: true, comment: true, details: true, modified: false };

type FilterField = "name" | "type" | "content" | "proxy";
type FilterOp = "contains" | "equals" | "starts";
interface Filter {
  id: number;
  field: FilterField;
  op: FilterOp;
  value: string;
}
const FIELDS: { v: FilterField; label: string }[] = [
  { v: "name", label: "Name" },
  { v: "type", label: "Type" },
  { v: "content", label: "Content" },
  { v: "proxy", label: "Proxy status" },
];
const OPS: { v: FilterOp; label: string }[] = [
  { v: "contains", label: "contains" },
  { v: "equals", label: "equals" },
  { v: "starts", label: "starts with" },
];
const TYPES: RecordType[] = ["A", "AAAA", "CNAME", "MX", "TXT", "NS"];

let fseq = 0;
const blank = (): Filter => ({ id: ++fseq, field: "name", op: "contains", value: "" });

function matchFilter(r: DnsRecord, f: Filter) {
  const v = f.value.trim().toLowerCase();
  const target = (f.field === "name" ? fqdn(r.name) : f.field === "type" ? r.type : f.field === "content" ? r.content : r.proxied ? "proxied" : "dns only").toLowerCase();
  return f.op === "equals" ? target === v : f.op === "starts" ? target.startsWith(v) : target.includes(v);
}

function sortValue(r: DnsRecord, k: SortKey): string | number {
  switch (k) {
    case "name":
      return fqdn(r.name);
    case "proxy":
      return r.proxied ? 1 : 0;
    case "ttl":
      return r.ttl;
    case "modified":
      return r.modified ?? 0;
    default:
      return r[k];
  }
}

const fmtDate = (t?: number) => (t ? new Date(t).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" }) : "—");

/* ----------------------------------- 单元格 ----------------------------------- */

function NameCell({ name }: { name: string }) {
  return name === "@" ? (
    <span>{DOMAIN}</span>
  ) : (
    <>
      <span>{name}</span>
      <span className="text-muted">.{DOMAIN}</span>
    </>
  );
}

function ProxyCell({ proxied }: { proxied: boolean }) {
  return proxied ? (
    <span className="inline-flex items-center gap-2">
      <Cloud size={18} fill="currentColor" aria-hidden="true" className="text-brand" />
      Proxied
    </span>
  ) : (
    <span>DNS only</span>
  );
}

function PendingIcon() {
  return (
    <span role="img" aria-label="Warning: domain is pending, this record is not active yet" title="Domain is pending: this record is not active yet" className="inline-flex text-warn-fg">
      <TriangleAlert size={16} aria-hidden="true" />
    </span>
  );
}

function CellContent({ r, id }: { r: DnsRecord; id: ColId }) {
  switch (id) {
    case "name":
      return <NameCell name={r.name} />;
    case "type":
      return <>{r.type}</>;
    case "content":
      return <span className="mono">{r.content}</span>;
    case "proxy":
      return <ProxyCell proxied={r.proxied} />;
    case "ttl":
      return <>{ttlLabel(r.ttl)}</>;
    case "comment":
      return r.comment ? <>{r.comment}</> : <span className="text-muted">—</span>;
    case "details":
      return r.type === "MX" ? <span className="badge">Priority {r.priority ?? 10}</span> : <span className="text-muted">—</span>;
    case "modified":
      return <span className="whitespace-nowrap">{fmtDate(r.modified)}</span>;
  }
}

/* ---------------------------------- 筛选浮层 ---------------------------------- */

function FiltersPanel({ applied, onApply, close }: { applied: Filter[]; onApply: (f: Filter[]) => void; close: () => void }) {
  const [draft, setDraft] = useState<Filter[]>(() => (applied.length ? applied : [blank()]));
  const upd = (id: number, patch: Partial<Filter>) => setDraft((d) => d.map((f) => (f.id === id ? { ...f, ...patch } : f)));
  const apply = () => {
    onApply(draft.filter((f) => f.value.trim() !== ""));
    close();
  };
  return (
    <div
      onKeyDown={(e) => {
        if (e.key === "Enter" && (e.target as HTMLElement).tagName !== "BUTTON") {
          e.preventDefault();
          apply();
        }
      }}
    >
      <div className="mb-3 flex items-center justify-between gap-3">
        <h2 className="text-base font-semibold">Filters</h2>
        <button type="button" className="btn btn-ghost btn-icon" aria-label="Close filters" onClick={close}>
          <X size={16} aria-hidden="true" />
        </button>
      </div>
      <div className="grid gap-3">
        {draft.map((f, i) => (
          <div key={f.id} className="grid grid-cols-2 gap-2 sm:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_minmax(0,2fr)_auto]">
            <Select
              aria-label={`Filter ${i + 1} field`}
              value={f.field}
              onChange={(e) => upd(f.id, { field: e.target.value as FilterField, value: "", op: e.target.value === "type" || e.target.value === "proxy" ? "equals" : f.op })}
            >
              {FIELDS.map((o) => (
                <option key={o.v} value={o.v}>
                  {o.label}
                </option>
              ))}
            </Select>
            <Select aria-label={`Filter ${i + 1} operator`} value={f.op} disabled={f.field === "type" || f.field === "proxy"} onChange={(e) => upd(f.id, { op: e.target.value as FilterOp })}>
              {OPS.map((o) => (
                <option key={o.v} value={o.v}>
                  {o.label}
                </option>
              ))}
            </Select>
            <div className="col-span-2 sm:col-span-1">
              {f.field === "type" ? (
                <Select aria-label={`Filter ${i + 1} value`} value={f.value} onChange={(e) => upd(f.id, { value: e.target.value })}>
                  <option value="">Select type…</option>
                  {TYPES.map((t) => (
                    <option key={t} value={t}>
                      {t}
                    </option>
                  ))}
                </Select>
              ) : f.field === "proxy" ? (
                <Select aria-label={`Filter ${i + 1} value`} value={f.value} onChange={(e) => upd(f.id, { value: e.target.value })}>
                  <option value="">Select status…</option>
                  <option value="proxied">Proxied</option>
                  <option value="dns only">DNS only</option>
                </Select>
              ) : (
                <input
                  className="input"
                  aria-label={`Filter ${i + 1} value`}
                  placeholder={f.field === "name" ? "hostname" : "value"}
                  value={f.value}
                  onChange={(e) => upd(f.id, { value: e.target.value })}
                  spellCheck={false}
                  autoComplete="off"
                />
              )}
            </div>
            <button
              type="button"
              className="btn btn-ghost btn-icon col-span-2 justify-self-end sm:col-span-1"
              aria-label={`Remove filter ${i + 1}`}
              onClick={() => setDraft((d) => (d.length === 1 ? [blank()] : d.filter((x) => x.id !== f.id)))}
            >
              <Trash size={16} aria-hidden="true" />
            </button>
          </div>
        ))}
      </div>
      <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
        <button type="button" className="btn btn-ghost" disabled={draft.length >= 4} onClick={() => setDraft((d) => [...d, blank()])}>
          <Plus size={14} aria-hidden="true" />
          Add filter
        </button>
        <div className="flex flex-wrap items-center gap-3">
          <span className="hidden text-xs text-muted sm:inline">Press Enter to apply</span>
          <button type="button" className="btn btn-primary" onClick={apply}>
            Apply
          </button>
        </div>
      </div>
    </div>
  );
}

/* ---------------------------------- 导入弹窗 ---------------------------------- */

function ImportBody({ onClose }: { onClose: () => void }) {
  const { importRecords } = useData();
  const { push } = useToast();
  const [text, setText] = useState("");
  const [errors, setErrors] = useState<string[]>([]);
  const taRef = useRef<HTMLTextAreaElement>(null);

  const submit = () => {
    const out: Omit<DnsRecord, "id">[] = [];
    const errs: string[] = [];
    text.split(/\r?\n/).forEach((raw, i) => {
      const line = raw.trim();
      if (!line || line.startsWith(";") || line.startsWith("#")) return;
      const t = line.split(/\s+/);
      const type = (t[1] ?? "").toUpperCase() as RecordType;
      if (t.length < 3) return void errs.push(`Line ${i + 1}: expected “name type content”.`);
      if (!TYPES.includes(type)) return void errs.push(`Line ${i + 1}: unsupported record type “${t[1]}”.`);
      const name = t[0].endsWith(`.${DOMAIN}`) ? t[0].slice(0, -DOMAIN.length - 1) : t[0] === DOMAIN ? "@" : t[0];
      let priority: number | undefined;
      let content = t.slice(2).join(" ");
      if (type === "MX") {
        priority = Number(t[2]);
        content = t.slice(3).join(" ");
        if (!Number.isInteger(priority) || !content) return void errs.push(`Line ${i + 1}: MX needs “name MX priority server”.`);
      }
      out.push({ type, name, content, proxied: false, ttl: 0, comment: "Imported", priority });
    });
    if (!out.length && !errs.length) errs.push("Nothing to import. Paste at least one record.");
    setErrors(errs);
    if (errs.length) {
      taRef.current?.focus();
      return;
    }
    importRecords(out);
    push({ title: `${out.length} record${out.length > 1 ? "s" : ""} imported` });
    onClose();
  };

  return (
    <form
      noValidate
      onSubmit={(e) => {
        e.preventDefault();
        submit();
      }}
    >
      <div className="grid gap-3 p-6">
        <h2 className="text-xl font-semibold">Import DNS records</h2>
        <p className="text-muted">One record per line: name, type, content. Example: “blog CNAME example.net”.</p>
        <label htmlFor="import-text" className="label">
          Records
        </label>
        <textarea
          id="import-text"
          ref={taRef}
          data-autofocus
          className="textarea mono"
          rows={6}
          value={text}
          onChange={(e) => setText(e.target.value)}
          aria-invalid={errors.length ? true : undefined}
          aria-describedby={errors.length ? "import-errors" : undefined}
          spellCheck={false}
          placeholder={"blog CNAME example.net\n@ MX 20 mail2.example.net"}
        />
        {errors.length > 0 && (
          <ul id="import-errors" className="alert alert-danger grid gap-1" role="alert">
            {errors.map((e) => (
              <li key={e}>{e}</li>
            ))}
          </ul>
        )}
      </div>
      <div className="flex flex-wrap justify-end gap-3 border-t border-line px-6 py-4">
        <button type="button" className="btn" onClick={onClose}>
          Cancel
        </button>
        <button type="submit" className="btn btn-primary">
          Import
        </button>
      </div>
    </form>
  );
}

/* ------------------------------------ 页面 ------------------------------------ */

type EditMode = "inline" | "dialog";
const EDIT_MODES = ["inline", "dialog"] as const;

export function DnsRecords({ route }: { route: Route }) {
  const { records, removeRecords, restoreRecords, bulkUpdate, restoreSnapshots } = useData();
  const { push } = useToast();
  const highlight = route.params.get("highlight");

  // 视图状态
  const [query, setQuery] = useState("");
  const dq = useDeferredValue(query);
  const [filters, setFilters] = useState<Filter[]>([]);
  const [sort, setSort] = useState<{ key: SortKey; dir: "asc" | "desc" } | null>(null);
  const [visible, setVisible] = useState<Record<ColId, boolean>>(DEFAULT_VISIBLE);
  const [density, setDensity] = useState<"comfortable" | "compact">("comfortable");
  const [editMode, setEditMode] = usePersisted<EditMode>("nimbus.dns.edit", "inline", EDIT_MODES);
  const [recsOpen, setRecsOpen] = useState(true);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);

  // 选择 / 编辑 / 对话框
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [editing, setEditing] = useState<Set<string>>(new Set());
  const [dialogId, setDialogId] = useState<string | null>(null);
  const [confirm, setConfirm] = useState<string[] | null>(null);
  const [importOpen, setImportOpen] = useState(false);
  const [discard, setDiscard] = useState<{ run: () => void } | null>(null);
  const [flash, setFlash] = useState<string | null>(null);

  const wrapRef = useRef<HTMLDivElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const allRef = useRef<HTMLInputElement>(null);
  const lastClicked = useRef<string | null>(null);
  const dirty = useRef(new Set<string>());
  const scrolledFor = useRef<string | null>(null);

  const compact = useBelow(wrapRef, 700);
  useScrollAffordance(scrollRef, compact);
  const visibleCols = useMemo(() => COLS.filter((c) => visible[c.id]), [visible]);
  const colw = useColumnWidths("nimbus.dns.cols", COLS, visibleCols.map((c) => c.id), FIXED_EXTRA);

  // 对话框退出动画期间 confirm 已为 null，保留最近一次的数量避免文案闪烁成 “0”
  const lastCount = useRef(1);
  if (confirm) lastCount.current = confirm.length;
  const nConfirm = confirm ? confirm.length : lastCount.current;

  /* ---------- 数据管线：搜索 → 筛选 → 排序 → 分页 ---------- */
  const rows = useMemo(() => {
    const q = dq.trim().toLowerCase();
    let list = records.filter((r) => {
      if (q && !`${fqdn(r.name)} ${r.type} ${r.content} ${r.comment}`.toLowerCase().includes(q)) return false;
      return filters.every((f) => matchFilter(r, f));
    });
    if (sort) {
      const dir = sort.dir === "asc" ? 1 : -1;
      list = [...list].sort((a, b) => {
        const av = sortValue(a, sort.key);
        const bv = sortValue(b, sort.key);
        return (typeof av === "number" && typeof bv === "number" ? av - bv : String(av).localeCompare(String(bv))) * dir;
      });
    }
    return list;
  }, [records, dq, filters, sort]);

  const pages = Math.max(1, Math.ceil(rows.length / pageSize));
  const cur = Math.min(page, pages);
  const startIdx = (cur - 1) * pageSize;
  const pageRows = rows.slice(startIdx, startIdx + pageSize);
  const pageIds = pageRows.map((r) => r.id);

  useEffect(() => setPage(1), [dq, filters, pageSize]);
  // 从表单页返回并带 ?highlight：翻到目标所在页（声明在“重置页码”之后，保证它后执行）
  useEffect(() => {
    if (!highlight) return;
    const i = rows.findIndex((r) => r.id === highlight);
    if (i >= 0) setPage(Math.floor(i / pageSize) + 1);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [highlight]);
  useEffect(() => {
    if (!highlight || scrolledFor.current === highlight) return;
    const el = [document.getElementById(`row-${highlight}`), document.getElementById(`card-${highlight}`)].find((x) => x && x.offsetParent !== null);
    if (el) {
      el.scrollIntoView({ block: "center" });
      scrolledFor.current = highlight;
    }
  }, [highlight, cur, pageRows.length, compact]);

  /* ---------- 选择 ---------- */
  const selRows = rows.filter((r) => selected.has(r.id));
  const pageSel = pageRows.filter((r) => selected.has(r.id)).length;
  const pageAll = pageRows.length > 0 && pageSel === pageRows.length;
  useEffect(() => {
    if (allRef.current) allRef.current.indeterminate = pageSel > 0 && !pageAll;
  }, [pageSel, pageAll]);

  const toggleRow = (id: string, shift: boolean) => {
    const n = new Set(selected);
    const on = !selected.has(id);
    const a = lastClicked.current ? pageIds.indexOf(lastClicked.current) : -1;
    const b = pageIds.indexOf(id);
    if (shift && a >= 0 && b >= 0) {
      for (let i = Math.min(a, b); i <= Math.max(a, b); i++) (on ? n.add(pageIds[i]) : n.delete(pageIds[i]));
    } else if (on) n.add(id);
    else n.delete(id);
    lastClicked.current = id;
    setSelected(n);
  };
  const togglePage = () => {
    const n = new Set(selected);
    pageIds.forEach((id) => (pageAll ? n.delete(id) : n.add(id)));
    setSelected(n);
  };

  /* ---------- 排序 ---------- */
  const toggleSort = (key: SortKey) => setSort((s) => (!s || s.key !== key ? { key, dir: "asc" } : s.dir === "asc" ? { key, dir: "desc" } : null));
  const sortIcon = (key: SortKey) => (sort?.key !== key ? ArrowUpDown : sort.dir === "asc" ? ArrowUp : ArrowDown);
  const ariaSort = (key: SortKey) => (sort?.key !== key ? undefined : sort.dir === "asc" ? ("ascending" as const) : ("descending" as const));

  /* ---------- 编辑：行内展开 / 弹窗；脏数据保护 ---------- */
  const reportDirty = useCallback((id: string, d: boolean) => {
    if (d) dirty.current.add(id);
    else dirty.current.delete(id);
  }, []);
  const focusEditBtn = (id: string) =>
    requestAnimationFrame(() => {
      for (const p of ["t", "c"]) {
        const el = document.getElementById(`editbtn-${p}-${id}`);
        if (el && el.offsetParent !== null) return void el.focus();
      }
    });
  const closeEditor = (id: string) => {
    setEditing((s) => {
      const n = new Set(s);
      n.delete(id);
      return n;
    });
    setDialogId((c) => (c === id ? null : c));
    dirty.current.delete(id);
    focusEditBtn(id);
  };
  const requestClose = (id: string) => (dirty.current.has(id) ? setDiscard({ run: () => closeEditor(id) }) : closeEditor(id));
  const openEdit = (id: string) => {
    if (editMode === "dialog") setDialogId(id);
    else if (editing.has(id)) requestClose(id);
    else setEditing((s) => new Set(s).add(id));
  };
  const onSaved = (id: string) => {
    closeEditor(id);
    setFlash(id);
    window.setTimeout(() => setFlash((f) => (f === id ? null : f)), 2600);
  };

  // 有未保存的行内 / 弹窗编辑时：拦截站内导航与关闭标签页
  useEffect(() => {
    setNavGuard((proceed) => {
      if (dirty.current.size === 0) return false;
      setDiscard({
        run: () => {
          dirty.current.clear();
          proceed();
        },
      });
      return true;
    });
    const before = (e: BeforeUnloadEvent) => {
      if (dirty.current.size) {
        e.preventDefault();
        e.returnValue = "";
      }
    };
    window.addEventListener("beforeunload", before);
    return () => {
      setNavGuard(null);
      window.removeEventListener("beforeunload", before);
    };
  }, []);

  /* ---------- 导出 / 删除 / 批量代理 ---------- */
  const exportRows = (list: DnsRecord[]) => {
    const body = list.map((r) => `${fqdn(r.name)}.\t${r.ttl || 300}\tIN\t${r.type}\t${r.type === "MX" ? `${r.priority ?? 10} ` : ""}${r.content}`).join("\n");
    const url = URL.createObjectURL(new Blob([`; Zone export for ${DOMAIN}\n${body}\n`], { type: "text/plain" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = `${DOMAIN}.zone.txt`;
    a.click();
    URL.revokeObjectURL(url);
    push({ title: `Exported ${list.length} record${list.length > 1 ? "s" : ""}`, tone: "info" });
  };

  const confirmDelete = () => {
    const ids = confirm ?? [];
    ids.forEach((id) => dirty.current.delete(id));
    const removed = removeRecords(ids);
    setSelected((s) => {
      const n = new Set(s);
      ids.forEach((id) => n.delete(id));
      return n;
    });
    setConfirm(null);
    push({ title: `${ids.length} record${ids.length > 1 ? "s" : ""} deleted`, action: { label: "Undo", run: () => restoreRecords(removed) } });
  };

  const bulkProxy = (on: boolean) => {
    const targets = selRows.filter((r) => PROXYABLE.includes(r.type) && r.proxied !== on);
    const skipped = selRows.filter((r) => !PROXYABLE.includes(r.type)).length;
    if (!targets.length) {
      push({ title: skipped ? `None of the selected records can be proxied (${skipped} skipped)` : `Selected records are already ${on ? "proxied" : "DNS only"}`, tone: "info" });
      return;
    }
    const prev = bulkUpdate(
      targets.map((r) => r.id),
      (r) => ({ proxied: on, ttl: on ? 0 : r.ttl }),
    );
    push({
      title: `${targets.length} record${targets.length > 1 ? "s" : ""} set to ${on ? "Proxied" : "DNS only"}${skipped ? ` · ${skipped} skipped (not proxyable)` : ""}`,
      action: { label: "Undo", run: () => restoreSnapshots(prev) },
    });
  };

  const hasCtl = query.trim() !== "" || filters.length > 0;
  const dialogRec = records.find((r) => r.id === dialogId);
  const from = rows.length === 0 ? 0 : startIdx + 1;
  const to = Math.min(startIdx + pageSize, rows.length);

  const rowActions = (r: DnsRecord, p: "t" | "c") => {
    const open = editMode === "inline" && editing.has(r.id);
    return (
      <div className="flex items-center justify-end gap-1">
        <button
          type="button"
          id={`editbtn-${p}-${r.id}`}
          className="btn btn-ghost"
          aria-label={`Edit ${r.type} record ${fqdn(r.name)}`}
          {...(editMode === "inline" ? { "aria-expanded": open, "aria-controls": open ? `edit-${r.id}` : undefined } : { "aria-haspopup": "dialog" as const })}
          onClick={() => openEdit(r.id)}
        >
          <Pencil size={14} aria-hidden="true" />
          Edit
        </button>
        <button type="button" className="btn btn-ghost btn-icon" aria-label={`Delete ${r.type} record ${fqdn(r.name)}`} onClick={() => setConfirm([r.id])}>
          <Trash size={16} aria-hidden="true" />
        </button>
      </div>
    );
  };

  const checkbox = (r: DnsRecord) => (
    <label className="hit">
      <input
        type="checkbox"
        className="checkbox"
        aria-label={`Select ${r.type} record ${fqdn(r.name)}`}
        checked={selected.has(r.id)}
        onClick={(e) => toggleRow(r.id, e.shiftKey)}
        onChange={() => {}}
      />
    </label>
  );

  return (
    <div>
      <PageHeader
        title={`DNS records for ${DOMAIN}`}
        description="Manage how the Internet finds your web content, verifies services, and routes traffic."
        actions={
          <>
            <span className="badge">DNS Setup: Full</span>
            <a className="btn" href="https://developers.cloudflare.com/dns/" target="_blank" rel="noreferrer noopener">
              <BookOpen size={16} aria-hidden="true" />
              DNS documentation
              <ExternalLink size={12} aria-hidden="true" className="text-muted" />
              <span className="sr-only">(opens in a new tab)</span>
            </a>
          </>
        }
      />

      <div className="alert alert-warn mt-6">
        <TriangleAlert size={16} aria-hidden="true" />
        <p>
          {DOMAIN} is <strong>pending</strong> until you complete the instructions on the <Link to="/dashboard/overview">Overview page</Link> and we are able to verify ownership.{" "}
          <Link to="/dashboard/p/pending-domains">Learn more about pending domains.</Link>
        </p>
      </div>

      <section className="card mt-6" aria-labelledby="rec-h">
        <div className="flex items-center justify-between gap-3 px-4 py-2">
          <h2 id="rec-h" className="flex flex-wrap items-center gap-2 text-base font-medium">
            Recommendations
            <span className="badge badge-ok">
              <CircleCheck size={12} aria-hidden="true" />
              All set
            </span>
          </h2>
          <button type="button" className="btn btn-ghost btn-icon" aria-expanded={recsOpen} aria-controls="rec-body" aria-label={recsOpen ? "Collapse recommendations" : "Expand recommendations"} onClick={() => setRecsOpen((o) => !o)}>
            <ChevronDown size={16} aria-hidden="true" className={cn("transition-transform duration-200", recsOpen && "rotate-180")} />
          </button>
        </div>
        {recsOpen && (
          <p id="rec-body" className="flex items-center justify-center gap-2 border-t border-line px-4 py-6 text-muted">
            <CircleCheck size={16} aria-hidden="true" />
            No recommendations
          </p>
        )}
      </section>

      {/* 工具栏：搜索 + 筛选 + 显示选项 + 导入导出 + 主操作 */}
      <div className="mt-6 flex flex-wrap items-center gap-3" role="group" aria-label="Record tools">
        <div className="relative min-w-0 flex-1 basis-56">
          <label htmlFor="dns-search" className="sr-only">
            Search DNS records
          </label>
          <Search size={16} aria-hidden="true" className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted" />
          <input id="dns-search" type="search" className="input pl-10" placeholder="Search DNS records" value={query} onChange={(e) => setQuery(e.target.value)} autoComplete="off" />
        </div>
        <Popover
          label="Filters"
          width={560}
          renderTrigger={(p) => (
            <button type="button" className="btn" {...p}>
              <Funnel size={16} aria-hidden="true" />
              Filters
              {filters.length > 0 && <span className="badge badge-info">{filters.length}</span>}
            </button>
          )}
        >
          {({ close }) => <FiltersPanel applied={filters} onApply={setFilters} close={close} />}
        </Popover>
        <Popover
          label="Display options"
          width={304}
          renderTrigger={(p) => (
            <button type="button" className="btn" {...p}>
              <SlidersHorizontal size={16} aria-hidden="true" />
              Display options
            </button>
          )}
        >
          {({ close }) => (
            <div className="grid gap-4">
              <div className="flex items-center justify-between gap-3">
                <h2 className="text-base font-semibold">Display options</h2>
                <button type="button" className="btn btn-ghost btn-icon" aria-label="Close display options" onClick={close}>
                  <X size={16} aria-hidden="true" />
                </button>
              </div>
              <fieldset className="group grid gap-1">
                <legend className="mb-1">Columns</legend>
                {COLS.filter((c) => c.hideable).map((c) => (
                  <label key={c.id} className="flex min-h-9 items-center gap-3">
                    <input type="checkbox" className="checkbox" checked={visible[c.id]} onChange={(e) => setVisible((v) => ({ ...v, [c.id]: e.target.checked }))} />
                    {c.label}
                  </label>
                ))}
                <button type="button" className="btn mt-2 justify-self-start" disabled={colw.isDefault} onClick={colw.resetAll}>
                  Reset column widths
                </button>
              </fieldset>
              <fieldset className="group grid gap-1">
                <legend className="mb-1">Row density</legend>
                {(["comfortable", "compact"] as const).map((d) => (
                  <label key={d} className="flex min-h-9 items-center gap-3 capitalize">
                    <input type="radio" name="density" className="checkbox" checked={density === d} onChange={() => setDensity(d)} />
                    {d}
                  </label>
                ))}
              </fieldset>
              <fieldset className="group grid gap-1">
                <legend className="mb-1">Edit style</legend>
                {(
                  [
                    ["inline", "Expand in row"],
                    ["dialog", "Open in dialog"],
                  ] as const
                ).map(([v, l]) => (
                  <label key={v} className="flex min-h-9 items-center gap-3">
                    <input type="radio" name="edit-style" className="checkbox" checked={editMode === v} onChange={() => setEditMode(v)} />
                    {l}
                  </label>
                ))}
              </fieldset>
            </div>
          )}
        </Popover>
        <button type="button" className="btn btn-collapse" aria-label="Import records" onClick={() => setImportOpen(true)}>
          <Upload size={16} aria-hidden="true" />
          <span className="max-md:sr-only">Import</span>
        </button>
        <button type="button" className="btn btn-collapse" aria-label="Export records" onClick={() => exportRows(records)}>
          <Download size={16} aria-hidden="true" />
          <span className="max-md:sr-only">Export</span>
        </button>
        <Link to="/dashboard/dns/new" className="btn btn-primary">
          <Plus size={16} aria-hidden="true" />
          Add record
        </Link>
      </div>

      {filters.length > 0 && (
        <ul className="mt-3 flex flex-wrap items-center gap-2" aria-label="Applied filters">
          {filters.map((f) => (
            <li key={f.id} className="badge py-1">
              <span>
                {FIELDS.find((x) => x.v === f.field)?.label} {OPS.find((x) => x.v === f.op)?.label} “{f.value}”
              </span>
              <button type="button" className="inline-flex size-6 items-center justify-center rounded-full border-0 bg-transparent text-muted hover:text-fg" aria-label={`Remove filter ${f.field} ${f.value}`} onClick={() => setFilters((l) => l.filter((x) => x.id !== f.id))}>
                <X size={12} aria-hidden="true" />
              </button>
            </li>
          ))}
          <li>
            <button type="button" className="link" onClick={() => setFilters([])}>
              Clear all
            </button>
          </li>
        </ul>
      )}

      <p className="mt-6 text-sm text-muted">
        You have used <strong className="text-fg">{records.length} of 200</strong> available DNS records for this domain.
      </p>

      <div ref={wrapRef} className="records mt-2">
        {compact ? (
          /* 窄容器（< 700px）：卡片列表。同一份数据换一种适合触控的呈现；仅渲染这一种，避免重复的编辑器 */
          <ul className="grid gap-3" aria-label="DNS records">
            {pageRows.map((r) => (
              <li key={r.id} id={`card-${r.id}`} className={cn("card p-4", r.id === (flash ?? highlight) && "row-flash")}>
                <div className="flex items-start gap-3">
                  <span className="-ml-2 -mt-1">{checkbox(r)}</span>
                  <div className="min-w-0 flex-1">
                    <p className="break-any font-semibold">
                      <NameCell name={r.name} />
                    </p>
                    <p className="break-any mono mt-1 text-muted">
                      <span className="badge mr-2 align-middle">{r.type}</span>
                      {r.content}
                    </p>
                  </div>
                  {r.pending && <PendingIcon />}
                </div>
                <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
                  <p className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-muted">
                    <ProxyCell proxied={r.proxied} />
                    <span>TTL {ttlLabel(r.ttl)}</span>
                    {r.type === "MX" && <span>Priority {r.priority ?? 10}</span>}
                  </p>
                  {rowActions(r, "c")}
                </div>
                {editMode === "inline" && editing.has(r.id) && (
                  <div id={`edit-${r.id}`} className="mt-4 border-t border-line pt-4">
                    <RecordEditor record={r} autoFocus onCancel={() => requestClose(r.id)} onSaved={onSaved} onDirtyChange={(d) => reportDirty(r.id, d)} />
                  </div>
                )}
              </li>
            ))}
          </ul>
        ) : (
          /* 宽容器：表格。列宽可调；首列（勾选）与末列（操作）粘性固定，列再多也能随时点到 Edit */
          <div ref={scrollRef} className="tbl overflow-x-auto rounded-lg border border-line" tabIndex={0} role="region" aria-label="DNS records table. Scroll horizontally to see more columns.">
            <table ref={colw.tableRef} className="dt" data-density={density} style={{ minWidth: colw.total }}>
              <caption className="sr-only">DNS records for {DOMAIN}. Drag the handle on a column header edge, or focus it and use the arrow keys, to resize the column.</caption>
              <colgroup>
                <col style={{ width: SEL_W }} />
                <col style={{ width: STATUS_W }} />
                {visibleCols.map((c) => (
                  <col key={c.id} ref={colw.colRef(c.id)} style={{ width: colw.widths[c.id] }} />
                ))}
                <col />
                <col style={{ width: ACT_W }} />
              </colgroup>
              <thead>
                <tr>
                  <th scope="col" className="sticky-l cell-sel">
                    <label className="hit">
                      <input ref={allRef} type="checkbox" className="checkbox" aria-label="Select all records on this page" checked={pageAll} onChange={togglePage} />
                    </label>
                  </th>
                  <th scope="col" className="cell-flush">
                    <span className="sr-only">Status</span>
                  </th>
                  {visibleCols.map((c) => {
                    const I = c.sort ? sortIcon(c.sort) : null;
                    return (
                      <th key={c.id} scope="col" aria-sort={c.sort ? ariaSort(c.sort) : undefined}>
                        <div className="flex min-w-0 items-center gap-1 pr-2">
                          {c.sort && I ? (
                            <button type="button" className="th-btn min-w-0" onClick={() => toggleSort(c.sort!)} aria-label={`Sort by ${c.label}`}>
                              <span className="min-w-0 truncate">{c.label}</span>
                              <I size={14} aria-hidden="true" className={cn("flex-none", sort?.key === c.sort ? "text-link" : "text-muted")} />
                            </button>
                          ) : (
                            <span className="min-w-0 truncate">{c.label}</span>
                          )}
                          {c.tip && <InfoTip text={c.tip} />}
                        </div>
                        <ResizeHandle
                          label={c.label}
                          value={colw.widths[c.id]}
                          min={c.min}
                          max={c.max}
                          onPreview={(w) => colw.preview(c.id, w)}
                          onCommit={(w) => colw.commit(c.id, w)}
                          onReset={() => colw.reset(c.id)}
                        />
                      </th>
                    );
                  })}
                  <th scope="col" aria-hidden="true" className="cell-flush" />
                  <th scope="col" className="sticky-r text-right">
                    Actions
                  </th>
                </tr>
              </thead>
              <tbody>
                {pageRows.map((r) => (
                  <Fragment key={r.id}>
                    <tr id={`row-${r.id}`} aria-selected={selected.has(r.id)} className={r.id === (flash ?? highlight) ? "row-flash" : undefined}>
                      <td className="sticky-l cell-sel">{checkbox(r)}</td>
                      <td className="cell-flush">{r.pending && <PendingIcon />}</td>
                      {visibleCols.map((c) => (
                        <td key={c.id}>
                          <CellContent r={r} id={c.id} />
                        </td>
                      ))}
                      <td aria-hidden="true" className="cell-flush" />
                      <td className="sticky-r">{rowActions(r, "t")}</td>
                    </tr>
                    {editMode === "inline" && editing.has(r.id) && (
                      <tr className="edit-row">
                        <td colSpan={visibleCols.length + 4} className="edit-cell">
                          <div id={`edit-${r.id}`} className="edit-inner">
                            <RecordEditor record={r} autoFocus onCancel={() => requestClose(r.id)} onSaved={onSaved} onDirtyChange={(d) => reportDirty(r.id, d)} />
                          </div>
                        </td>
                      </tr>
                    )}
                  </Fragment>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {rows.length === 0 && (
          <div className="rounded-lg border border-line px-4 py-12 text-center">
            <p className="font-semibold">{records.length === 0 ? "No DNS records yet" : "No records match your search or filters"}</p>
            <p className="mt-1 text-muted">{records.length === 0 ? "Add your first record to start routing traffic." : "Try a different keyword or clear the filters."}</p>
            {hasCtl && (
              <button
                type="button"
                className="btn mt-4"
                onClick={() => {
                  setQuery("");
                  setFilters([]);
                }}
              >
                Clear search and filters
              </button>
            )}
          </div>
        )}

        {/* 分页 */}
        <div className="mt-3 flex flex-wrap items-center justify-between gap-x-6 gap-y-3">
          <p className="text-sm text-muted" aria-live="polite">
            Showing {from === 0 ? 0 : `${from}–${to}`} of {rows.length}
            {rows.length !== records.length && ` (filtered from ${records.length})`}
          </p>
          <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
            <label className="flex items-center gap-2 text-sm">
              <span className="text-muted">Rows per page</span>
              <Select className="!w-20" value={pageSize} onChange={(e) => setPageSize(Number(e.target.value))}>
                {[5, 10, 25, 50].map((n) => (
                  <option key={n} value={n}>
                    {n}
                  </option>
                ))}
              </Select>
            </label>
            <div className="flex items-center gap-1" role="group" aria-label="Pagination">
              <button type="button" className="btn btn-icon" aria-label="Previous page" disabled={cur <= 1} onClick={() => setPage(cur - 1)}>
                <ChevronLeft size={16} aria-hidden="true" />
              </button>
              <span className="min-w-20 text-center text-sm">
                Page {cur} of {pages}
              </span>
              <button type="button" className="btn btn-icon" aria-label="Next page" disabled={cur >= pages} onClick={() => setPage(cur + 1)}>
                <ChevronRight size={16} aria-hidden="true" />
              </button>
            </div>
          </div>
        </div>

        {/* 批量操作条：悬浮 + 粘性贴在视口底部，出现时不会推动上方的表格行（Shift + 点击连续勾选才不会错位） */}
        {selRows.length > 0 && (
          <div className="bulkbar" role="region" aria-label="Bulk actions">
            <p className="font-medium" aria-live="polite">
              {selRows.length} selected
            </p>
            {pageAll && rows.length > pageRows.length && selRows.length < rows.length && (
              <button type="button" className="link" onClick={() => setSelected(new Set(rows.map((r) => r.id)))}>
                Select all {rows.length} matching records
              </button>
            )}
            <div className="ml-auto flex flex-wrap items-center gap-2">
              <button type="button" className="btn" onClick={() => bulkProxy(true)}>
                <Cloud size={16} aria-hidden="true" />
                Proxied
              </button>
              <button type="button" className="btn" onClick={() => bulkProxy(false)}>
                DNS only
              </button>
              <button type="button" className="btn" onClick={() => exportRows(selRows)}>
                <Download size={16} aria-hidden="true" />
                <span className="max-sm:sr-only">Export</span>
              </button>
              <button type="button" className="btn btn-danger" onClick={() => setConfirm(selRows.map((r) => r.id))}>
                <Trash size={16} aria-hidden="true" />
                Delete
              </button>
              <button type="button" className="btn btn-ghost btn-icon" aria-label="Clear selection" onClick={() => setSelected(new Set())}>
                <X size={16} aria-hidden="true" />
              </button>
            </div>
            <p className="basis-full text-xs text-muted max-sm:hidden">Tip: hold Shift while clicking a checkbox to select a range.</p>
          </div>
        )}
      </div>

      <ConfirmDialog open={confirm !== null} title={`Delete ${nConfirm > 1 ? `${nConfirm} DNS records` : "this DNS record"}?`} confirmLabel="Delete" danger onCancel={() => setConfirm(null)} onConfirm={confirmDelete}>
        <p>Traffic that relies on {nConfirm > 1 ? "these records" : "this record"} may stop resolving. You can undo right after deleting.</p>
      </ConfirmDialog>

      <ConfirmDialog
        open={discard !== null}
        title="Discard unsaved changes?"
        confirmLabel="Discard changes"
        cancelLabel="Keep editing"
        danger
        onCancel={() => setDiscard(null)}
        onConfirm={() => {
          const d = discard;
          setDiscard(null);
          d?.run();
        }}
      >
        <p>You have edits that haven’t been saved. If you continue they will be lost.</p>
      </ConfirmDialog>

      <Modal open={dialogId !== null} onClose={() => dialogId && requestClose(dialogId)} label="Edit DNS record" className="w-[min(640px,calc(100vw-16px))]">
        {dialogRec && (
          <div className="grid gap-4 p-6">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <h2 className="text-xl font-semibold">Edit {dialogRec.type} record</h2>
                <p className="break-all text-muted">{fqdn(dialogRec.name)}</p>
              </div>
              <button type="button" className="btn btn-ghost btn-icon" aria-label="Close dialog" onClick={() => requestClose(dialogRec.id)}>
                <X size={18} aria-hidden="true" />
              </button>
            </div>
            <RecordEditor record={dialogRec} onCancel={() => requestClose(dialogRec.id)} onSaved={onSaved} onDirtyChange={(d) => reportDirty(dialogRec.id, d)} />
          </div>
        )}
      </Modal>
      <Modal open={importOpen} onClose={() => setImportOpen(false)} label="Import DNS records">
        <ImportBody onClose={() => setImportOpen(false)} />
      </Modal>
    </div>
  );
}
