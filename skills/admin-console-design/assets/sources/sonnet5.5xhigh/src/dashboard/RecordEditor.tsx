import { useEffect, useId, useMemo, useRef, useState, type FormEvent } from "react";
import { Link } from "@/lib/route";
import { Field, Select, Spinner, Switch } from "@/ui/controls";
import { useToast } from "@/ui/Toast";
import { DOMAIN, TTL_OPTIONS, fqdn, useData, type DnsRecord, type RecordType } from "./data";
import {
  FIELD_ORDER,
  PROXYABLE,
  TYPE_META,
  draftFromRecord,
  draftToRecord,
  findConflicts,
  normalizeName,
  validateDraft,
  type Draft,
  type FieldErrors,
  type FieldKey,
} from "./recordModel";

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

/**
 * 紧凑编辑器：既可嵌在表格行下方（行内展开），也可放进弹窗。
 * 规则与整页表单一致：失焦即时校验 → 提交整体校验 → 首个错误字段聚焦 → 已填内容保留；
 * 区别：紧凑场景不显示顶部错误汇总，只保留行内错误 + 首错聚焦。
 */
export function RecordEditor({
  record,
  autoFocus,
  onCancel,
  onSaved,
  onDirtyChange,
}: {
  record: DnsRecord;
  autoFocus?: boolean;
  onCancel: () => void;
  onSaved: (id: string) => void;
  onDirtyChange?: (dirty: boolean) => void;
}) {
  const { records, updateRecord } = useData();
  const { push } = useToast();
  const [initial] = useState<Draft>(() => draftFromRecord(record));
  const [form, setForm] = useState<Draft>(initial);
  const [touched, setTouched] = useState<Partial<Record<FieldKey, boolean>>>({});
  const [submitted, setSubmitted] = useState(false);
  const [serverErrors, setServerErrors] = useState<FieldErrors>({});
  const [saving, setSaving] = useState(false);
  const formRef = useRef<HTMLFormElement>(null);
  const alive = useRef(true);
  const proxyLabel = useId();
  const proxyHint = useId();

  const dirty = JSON.stringify(form) !== JSON.stringify(initial);
  const cb = useRef(onDirtyChange);
  cb.current = onDirtyChange;
  useEffect(() => {
    cb.current?.(dirty);
  }, [dirty]);
  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
      cb.current?.(false);
    };
  }, []);
  useEffect(() => {
    if (autoFocus) formRef.current?.querySelector<HTMLElement>("select,input,textarea")?.focus();
  }, [autoFocus]);

  const clientErrors = useMemo(() => validateDraft(form), [form]);
  const errors = useMemo(() => {
    const out: FieldErrors = {};
    for (const k of FIELD_ORDER) {
      const msg = clientErrors[k] ?? serverErrors[k];
      if (msg && (touched[k] || submitted || serverErrors[k])) out[k] = msg;
    }
    return out;
  }, [clientErrors, serverErrors, touched, submitted]);

  const set = <K extends keyof Draft>(k: K, v: Draft[K]) => {
    setForm((f) => ({ ...f, [k]: v }));
    if (k in serverErrors) setServerErrors({});
  };
  const blur = (k: FieldKey) => setTouched((t) => ({ ...t, [k]: true }));
  const focusField = (k: FieldKey) => (formRef.current?.elements.namedItem(k) as HTMLElement | null)?.focus();
  const onType = (t: RecordType) =>
    setForm((f) => ({ ...f, type: t, proxied: PROXYABLE.includes(t) ? f.proxied : false, content: f.type === t ? f.content : "" }));

  const supportsProxy = PROXYABLE.includes(form.type);
  const effTtl = form.proxied ? 0 : form.ttl;

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (saving) return;
    setSubmitted(true);
    setServerErrors({});
    const first = FIELD_ORDER.find((k) => clientErrors[k]);
    if (first) return focusField(first);
    setSaving(true);
    await sleep(450);
    if (!alive.current) return;
    const se = findConflicts(records, form, record.id);
    if (Object.keys(se).length) {
      setSaving(false);
      setServerErrors(se);
      window.setTimeout(() => focusField(se.name ? "name" : "content"), 0);
      return;
    }
    updateRecord(record.id, draftToRecord(form, record));
    setSaving(false);
    push({ title: `${form.type} record for ${fqdn(normalizeName(form.name) || "@")} updated` });
    onSaved(record.id);
  };

  const trim = (k: "content") => setForm((f) => ({ ...f, [k]: f[k].trim() }));

  return (
    <form ref={formRef} noValidate autoComplete="off" onSubmit={submit} className="grid gap-4" aria-label={`Edit ${record.type} record ${fqdn(record.name)}`}>
      <div className="edit-grid">
        <Field label="Type" required name="type">
          {(p) => (
            <Select {...p} name="type" value={form.type} onChange={(e) => onType(e.target.value as RecordType)}>
              {(Object.keys(TYPE_META) as RecordType[]).map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </Select>
          )}
        </Field>
        <Field label="Name" required name="name" error={errors.name}>
          {(p) => (
            <div className="input-group">
              <input
                {...p}
                name="name"
                className="input"
                value={form.name}
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
        <Field label="TTL" name="ttl" hint={form.proxied ? "Fixed to Auto while proxied." : undefined}>
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

        <Field label={TYPE_META[form.type].label} required name="content" error={errors.content} className="full">
          {(p) =>
            form.type === "TXT" ? (
              <textarea
                {...p}
                name="content"
                className="textarea mono"
                rows={2}
                value={form.content}
                spellCheck={false}
                onChange={(e) => set("content", e.target.value)}
                onBlur={() => {
                  blur("content");
                  trim("content");
                }}
              />
            ) : (
              <input
                {...p}
                name="content"
                className="input"
                value={form.content}
                placeholder={TYPE_META[form.type].placeholder}
                autoCapitalize="none"
                spellCheck={false}
                onChange={(e) => set("content", e.target.value)}
                onBlur={() => {
                  blur("content");
                  trim("content");
                }}
              />
            )
          }
        </Field>

        {form.type === "MX" && (
          <Field label="Priority" required name="priority" error={errors.priority} hint="Lower numbers are preferred.">
            {(p) => <input {...p} name="priority" className="input" inputMode="numeric" value={form.priority} onChange={(e) => set("priority", e.target.value)} onBlur={() => blur("priority")} />}
          </Field>
        )}
        {supportsProxy && (
          <div className="field">
            <span id={proxyLabel} className="label">
              Proxy status
            </span>
            <div className="flex min-h-9 items-center gap-3">
              <Switch checked={form.proxied} onChange={(v) => set("proxied", v)} aria-labelledby={proxyLabel} aria-describedby={proxyHint} />
              <span id={proxyHint}>{form.proxied ? "Proxied" : "DNS only"}</span>
            </div>
          </div>
        )}

        <Field label="Comment" optional name="comment" error={errors.comment} hint={`${form.comment.length}/100 characters`} className="full">
          {(p) => <input {...p} name="comment" className="input" value={form.comment} onChange={(e) => set("comment", e.target.value)} onBlur={() => blur("comment")} />}
        </Field>
      </div>

      <div className="flex flex-wrap items-center justify-end gap-3">
        <Link to={`/dashboard/dns/edit/${record.id}`} className="link mr-auto">
          Open full form
        </Link>
        <button type="button" className="btn" onClick={onCancel}>
          Cancel
        </button>
        <button type="submit" className="btn btn-primary" aria-disabled={saving} aria-busy={saving}>
          {saving ? (
            <>
              <Spinner />
              Saving…
            </>
          ) : (
            "Save changes"
          )}
        </button>
      </div>
    </form>
  );
}
