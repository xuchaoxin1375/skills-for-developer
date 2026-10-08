import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { CircleAlert } from "lucide-react";
import { navigate, setNavGuard } from "@/lib/route";
import { ConfirmDialog } from "@/ui/Modal";
import { Breadcrumbs, Field, PageHeader, Select, Spinner, Switch } from "@/ui/controls";
import { useToast } from "@/ui/Toast";
import { DOMAIN, TTL_OPTIONS, fqdn, useData, type RecordType } from "../data";
import {
  FIELD_ORDER,
  PROXYABLE,
  TYPE_META,
  draftFromRecord,
  draftToRecord,
  emptyDraft,
  findConflicts,
  normalizeName,
  validateDraft,
  type Draft,
  type FieldErrors,
  type FieldKey,
} from "../recordModel";

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

/** 整页表单：创建 / 编辑一个记录。校验规则来自 recordModel，与行内 / 弹窗编辑器共用 */
export function RecordForm({ mode, id }: { mode: "add" | "edit"; id?: string }) {
  const { records, addRecord, updateRecord } = useData();
  const { push } = useToast();
  const existing = mode === "edit" ? records.find((r) => r.id === id) : undefined;

  const initial = useMemo<Draft>(
    () => (existing ? draftFromRecord(existing) : emptyDraft()),
    // 仅在进入页面（id / mode 变化）时取初值，之后用户的编辑不被外部数据覆盖
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [id, mode],
  );
  const [form, setForm] = useState<Draft>(initial);
  const [touched, setTouched] = useState<Partial<Record<FieldKey, boolean>>>({});
  const [submitted, setSubmitted] = useState(false);
  const [serverErrors, setServerErrors] = useState<FieldErrors>({});
  const [saving, setSaving] = useState(false);
  const [leave, setLeave] = useState<(() => void) | null>(null);
  const formRef = useRef<HTMLFormElement>(null);
  const alive = useRef(true);
  const saved = useRef(false);

  const dirty = JSON.stringify(form) !== JSON.stringify(initial);
  const dirtyRef = useRef(false);
  dirtyRef.current = dirty && !saved.current;

  // 未保存修改保护：站内导航弹出确认；刷新 / 关闭标签页使用浏览器原生提示
  useEffect(() => {
    alive.current = true;
    setNavGuard((proceed) => {
      if (!dirtyRef.current) return false;
      setLeave(() => proceed);
      return true;
    });
    const before = (e: BeforeUnloadEvent) => {
      if (dirtyRef.current) {
        e.preventDefault();
        e.returnValue = "";
      }
    };
    window.addEventListener("beforeunload", before);
    return () => {
      alive.current = false;
      setNavGuard(null);
      window.removeEventListener("beforeunload", before);
    };
  }, []);

  const clientErrors = useMemo(() => validateDraft(form), [form]);
  const errors: FieldErrors = useMemo(() => {
    const out: FieldErrors = {};
    for (const k of FIELD_ORDER) {
      const msg = clientErrors[k] ?? serverErrors[k];
      if (msg && (touched[k] || submitted || serverErrors[k])) out[k] = msg;
    }
    return out;
  }, [clientErrors, serverErrors, touched, submitted]);

  const set = <K extends keyof Draft>(k: K, v: Draft[K]) => {
    setForm((f) => ({ ...f, [k]: v }));
    if (k in serverErrors || k === "type") setServerErrors({});
  };
  const blur = (k: FieldKey) => setTouched((t) => ({ ...t, [k]: true }));
  const focusField = (k: FieldKey) => (formRef.current?.elements.namedItem(k) as HTMLElement | null)?.focus();
  const onType = (t: RecordType) =>
    setForm((f) => ({ ...f, type: t, proxied: PROXYABLE.includes(t) ? f.proxied : false, content: f.type === t ? f.content : "" }));

  const supportsProxy = PROXYABLE.includes(form.type);
  const effTtl = form.proxied ? 0 : form.ttl;
  const normName = normalizeName(form.name);
  const previewLine = `${fqdn(normName || "@")}.  ${effTtl || 300}  IN  ${form.type}  ${form.type === "MX" ? `${form.priority || "10"}  ` : ""}${form.content.trim() || "…"}`;

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (saving) return;
    setSubmitted(true);
    setServerErrors({});
    const first = FIELD_ORDER.find((k) => clientErrors[k]);
    if (first) {
      focusField(first); // 首个错误字段获得焦点
      return;
    }
    setSaving(true);
    await sleep(700); // 模拟网络请求
    if (!alive.current) return;

    const se = findConflicts(records, form, id);
    if (Object.keys(se).length) {
      setSaving(false);
      setServerErrors(se);
      window.setTimeout(() => focusField(se.name ? "name" : "content"), 0);
      return;
    }

    const data = draftToRecord(form, existing);
    let rid = id ?? "";
    if (mode === "add") rid = addRecord(data);
    else updateRecord(rid, data);
    saved.current = true;
    setSaving(false);
    push({ title: mode === "add" ? `${form.type} record for ${fqdn(normName)} added` : "Record updated" });
    navigate(`/dashboard/dns?highlight=${rid}`, { force: true });
  };

  if (mode === "edit" && !existing) {
    return (
      <div>
        <Breadcrumbs items={[{ label: "DNS", to: "/dashboard/dns" }, { label: "Records", to: "/dashboard/dns" }, { label: "Edit record" }]} />
        <PageHeader title="Record not found" description="It may have been deleted. Return to the list to pick another record." />
        <button type="button" className="btn mt-6" onClick={() => navigate("/dashboard/dns")}>
          Back to DNS records
        </button>
      </div>
    );
  }

  const errList = FIELD_ORDER.filter((k) => errors[k]);
  const inputProps = (k: FieldKey) => ({ name: k, onBlur: () => blur(k) });

  return (
    <div>
      <Breadcrumbs items={[{ label: "DNS", to: "/dashboard/dns" }, { label: "Records", to: "/dashboard/dns" }, { label: mode === "add" ? "Add record" : "Edit record" }]} />
      <PageHeader
        title={mode === "add" ? "Add DNS record" : `Edit ${existing?.type} record`}
        description={mode === "add" ? `Create a record for ${DOMAIN}. You can change or delete it at any time.` : fqdn(existing?.name ?? "@")}
      />

      <div className="formgrid mt-6">
        <div className="formgrid-in">
          <form ref={formRef} noValidate autoComplete="off" onSubmit={submit} className="card min-w-0" aria-describedby="req-note">
            <div className="card-pad grid gap-6">
              {submitted && errList.length > 0 && (
                <div className="alert alert-danger" role="alert">
                  <CircleAlert size={16} aria-hidden="true" />
                  <div className="min-w-0">
                    <p className="font-semibold">
                      {errList.length} {errList.length > 1 ? "problems need" : "problem needs"} your attention
                    </p>
                    <ul className="mt-1 grid gap-1">
                      {errList.map((k) => (
                        <li key={k}>
                          <button type="button" className="link break-words text-left text-danger" onClick={() => focusField(k)}>
                            {errors[k]}
                          </button>
                        </li>
                      ))}
                    </ul>
                  </div>
                </div>
              )}
              <p id="req-note" className="text-sm text-muted">
                Fields marked with <span aria-hidden="true">*</span>
                <span className="sr-only">an asterisk</span> are required.
              </p>

              <fieldset className="group grid gap-4">
                <legend className="mb-1 text-base">Record</legend>
                <Field label="Type" required name="type" className="sm:max-w-xs">
                  {(p) => (
                    <Select {...p} {...inputProps("type")} value={form.type} onChange={(e) => onType(e.target.value as RecordType)}>
                      {(Object.keys(TYPE_META) as RecordType[]).map((t) => (
                        <option key={t} value={t}>
                          {t}
                        </option>
                      ))}
                    </Select>
                  )}
                </Field>
                <Field
                  label="Name"
                  required
                  name="name"
                  error={errors.name}
                  hint={`Use @ for the root domain. Pasting a full hostname (e.g. www.${DOMAIN}) is fine — we shorten it for you.`}
                >
                  {(p) => (
                    <div className="input-group">
                      <input
                        {...p}
                        {...inputProps("name")}
                        className="input"
                        value={form.name}
                        placeholder="www"
                        autoCapitalize="none"
                        spellCheck={false}
                        onChange={(e) => set("name", e.target.value)}
                        onBlur={() => {
                          blur("name");
                          if (form.name.trim()) setForm((f) => ({ ...f, name: normalizeName(f.name) }));
                        }}
                      />
                      <span className="addon" aria-hidden="true">
                        .{DOMAIN}
                      </span>
                    </div>
                  )}
                </Field>
                <Field label={TYPE_META[form.type].label} required name="content" error={errors.content}>
                  {(p) =>
                    form.type === "TXT" ? (
                      <textarea
                        {...p}
                        {...inputProps("content")}
                        className="textarea mono"
                        rows={3}
                        value={form.content}
                        placeholder={TYPE_META.TXT.placeholder}
                        spellCheck={false}
                        onChange={(e) => set("content", e.target.value)}
                        onBlur={() => {
                          blur("content");
                          setForm((f) => ({ ...f, content: f.content.trim() }));
                        }}
                      />
                    ) : (
                      <input
                        {...p}
                        {...inputProps("content")}
                        className="input"
                        value={form.content}
                        placeholder={TYPE_META[form.type].placeholder}
                        autoCapitalize="none"
                        spellCheck={false}
                        inputMode={form.type === "A" ? "decimal" : "text"}
                        onChange={(e) => set("content", e.target.value)}
                        onBlur={() => {
                          blur("content");
                          setForm((f) => ({ ...f, content: f.content.trim() }));
                        }}
                      />
                    )
                  }
                </Field>
                {form.type === "MX" && (
                  <Field label="Priority" required name="priority" error={errors.priority} hint="Lower numbers are preferred. 10 is a common default." className="sm:max-w-xs">
                    {(p) => <input {...p} {...inputProps("priority")} className="input" inputMode="numeric" value={form.priority} onChange={(e) => set("priority", e.target.value)} />}
                  </Field>
                )}
              </fieldset>

              <fieldset className="group grid gap-4 border-t border-line pt-6">
                <legend className="mb-1 text-base">Routing and caching</legend>
                {supportsProxy ? (
                  <div className="flex items-start justify-between gap-4">
                    <div className="min-w-0">
                      <p id="proxy-l" className="label">
                        Proxy status
                      </p>
                      <p id="proxy-h" className="hint">
                        Proxied traffic is cached and protected. DNS-only records resolve straight to the origin.
                      </p>
                    </div>
                    <div className="flex flex-none items-center gap-3 pt-1">
                      <span className="text-sm" aria-hidden="true">
                        {form.proxied ? "Proxied" : "DNS only"}
                      </span>
                      <Switch checked={form.proxied} onChange={(v) => set("proxied", v)} aria-labelledby="proxy-l" aria-describedby="proxy-h" />
                    </div>
                  </div>
                ) : (
                  <p className="hint">Proxy status isn’t available for {form.type} records — they are always DNS only.</p>
                )}
                <Field label="TTL" name="ttl" hint={form.proxied ? "TTL is fixed to Auto while the record is proxied." : "How long resolvers may cache this record."} className="sm:max-w-xs">
                  {(p) => (
                    <Select {...p} name="ttl" value={String(effTtl)} disabled={form.proxied} onChange={(e) => set("ttl", Number(e.target.value))}>
                      {TTL_OPTIONS.map((o) => (
                        <option key={o.value} value={o.value}>
                          {o.label}
                        </option>
                      ))}
                    </Select>
                  )}
                </Field>
              </fieldset>

              <fieldset className="group grid gap-4 border-t border-line pt-6">
                <legend className="mb-1 text-base">Notes</legend>
                <Field label="Comment" optional name="comment" error={errors.comment} hint={`${form.comment.length}/100 characters. Visible to your team only.`}>
                  {(p) => <textarea {...p} {...inputProps("comment")} className="textarea" rows={2} value={form.comment} onChange={(e) => set("comment", e.target.value)} placeholder="Why does this record exist?" />}
                </Field>
              </fieldset>

              <div className="field">
                <span id="prev-l" className="label">
                  Preview
                </span>
                <output aria-labelledby="prev-l" className="mono block overflow-x-auto whitespace-pre-wrap break-all rounded-md border border-line bg-subtle p-3">
                  {previewLine}
                </output>
              </div>
            </div>

            <div className="actionbar rounded-b-lg">
              <p className="grow text-sm text-muted" aria-live="polite">
                {dirty ? (
                  <span className="inline-flex items-center gap-2">
                    <span aria-hidden="true" className="size-2 rounded-full bg-brand" />
                    Unsaved changes
                  </span>
                ) : (
                  ""
                )}
              </p>
              <button type="button" className="btn" onClick={() => navigate("/dashboard/dns")}>
                Cancel
              </button>
              <button type="submit" className="btn btn-primary" aria-disabled={saving} aria-busy={saving}>
                {saving ? (
                  <>
                    <Spinner />
                    Saving…
                  </>
                ) : mode === "add" ? (
                  "Save record"
                ) : (
                  "Save changes"
                )}
              </button>
            </div>
          </form>

          <aside className="formgrid-aside card card-pad" aria-label="Help">
            <h2 className="text-base font-semibold">About {form.type} records</h2>
            <p className="mt-2 text-muted">{TYPE_META[form.type].tip}</p>
            <h2 className="mt-6 text-base font-semibold">Good to know</h2>
            <ul className="mt-2 grid list-disc gap-1 pl-4 text-muted">
              <li>Changes to proxied records apply within seconds.</li>
              <li>
                Press <kbd className="kbd">Enter</kbd> in any field to save.
              </li>
              <li>Leaving this page with unsaved edits asks for confirmation.</li>
            </ul>
          </aside>
        </div>
      </div>

      <ConfirmDialog
        open={leave !== null}
        title="Discard unsaved changes?"
        confirmLabel="Discard changes"
        cancelLabel="Keep editing"
        danger
        onCancel={() => setLeave(null)}
        onConfirm={() => {
          const go = leave;
          dirtyRef.current = false;
          saved.current = true;
          setLeave(null);
          go?.();
        }}
      >
        <p>Your edits to this record haven’t been saved. If you leave now they will be lost.</p>
      </ConfirmDialog>
    </div>
  );
}
