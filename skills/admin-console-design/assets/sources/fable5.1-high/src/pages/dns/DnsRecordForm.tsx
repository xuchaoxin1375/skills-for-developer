import { useEffect, useMemo, useRef, useState } from "react";
import { Cloud, CloudOff, Trash2 } from "lucide-react";
import { cn } from "@/utils/cn";
import { Button, Field, Input, Select, Textarea, Toggle } from "@/components/ui/primitives";
import { Alert, InfoTip } from "@/components/ui/layout";
import { RECORD_TYPES, TTL_OPTIONS, ZONE, validateRecord, type DnsRecord, type FormErrors, type RecordFormValues, type RecordType } from "@/data/records";

const empty: RecordFormValues = { type: "A", name: "", content: "", proxied: true, ttl: "1", priority: "10", comment: "" };

export function toForm(r?: DnsRecord): RecordFormValues {
  if (!r) return empty;
  return {
    type: r.type,
    name: r.name === ZONE ? "@" : r.name.endsWith("." + ZONE) ? r.name.slice(0, -ZONE.length - 1) : r.name,
    content: r.content,
    proxied: r.proxied,
    ttl: String(r.ttl),
    priority: r.priority != null ? String(r.priority) : "10",
    comment: r.comment ?? "",
  };
}

export function DnsRecordForm({
  initial,
  existing,
  editingId,
  onCancel,
  onSave,
  onDelete,
  idPrefix,
}: {
  initial?: DnsRecord;
  existing: DnsRecord[];
  editingId?: string;
  onCancel: () => void;
  onSave: (v: RecordFormValues) => Promise<void> | void;
  onDelete?: () => void;
  idPrefix: string;
}) {
  const [v, setV] = useState<RecordFormValues>(() => toForm(initial));
  const [touched, setTouched] = useState<Partial<Record<keyof RecordFormValues, boolean>>>({});
  const [submitted, setSubmitted] = useState(false);
  const [saving, setSaving] = useState(false);
  const root = useRef<HTMLFormElement>(null);
  const firstInput = useRef<HTMLSelectElement>(null);

  const meta = RECORD_TYPES.find((t) => t.value === v.type)!;
  const allErrors = useMemo(() => validateRecord(v, existing, editingId), [v, existing, editingId]);
  // show an error only after the field was touched (blur) or after a submit attempt
  const errors: FormErrors = useMemo(() => {
    const out: FormErrors = {};
    (Object.keys(allErrors) as (keyof FormErrors)[]).forEach((k) => {
      if (submitted || touched[k]) out[k] = allErrors[k];
    });
    return out;
  }, [allErrors, submitted, touched]);

  const dirty = JSON.stringify(v) !== JSON.stringify(toForm(initial));
  const set = <K extends keyof RecordFormValues>(k: K, val: RecordFormValues[K]) => setV((s) => ({ ...s, [k]: val }));
  const blur = (k: keyof RecordFormValues) => setTouched((t) => ({ ...t, [k]: true }));
  const id = (k: string) => `${idPrefix}-${k}`;

  useEffect(() => {
    firstInput.current?.focus();
  }, []);

  // warn before leaving with unsaved changes (same tab close/refresh)
  useEffect(() => {
    if (!dirty) return;
    const h = (e: BeforeUnloadEvent) => {
      e.preventDefault();
    };
    window.addEventListener("beforeunload", h);
    return () => window.removeEventListener("beforeunload", h);
  }, [dirty]);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitted(true);
    const keys = Object.keys(allErrors) as (keyof FormErrors)[];
    if (keys.length) {
      // focus the first invalid control in DOM order
      const el = root.current?.querySelector<HTMLElement>("[aria-invalid='true']");
      el?.focus();
      el?.scrollIntoView({ block: "center", behavior: "smooth" });
      return;
    }
    setSaving(true);
    try {
      await onSave({ ...v, name: v.name.trim(), content: v.content.trim() });
    } finally {
      setSaving(false);
    }
  };

  const onTypeChange = (t: RecordType) => {
    const m = RECORD_TYPES.find((x) => x.value === t)!;
    setV((s) => ({ ...s, type: t, proxied: m.proxyable ? s.proxied : false, ttl: m.proxyable && s.proxied ? "1" : s.ttl }));
  };

  const errorCount = Object.keys(errors).length;

  return (
    <form ref={root} noValidate onSubmit={submit} aria-labelledby={id("title")} className="anim-fade">
      <h3 id={id("title")} className="sr-only">
        {initial ? "Edit DNS record" : "Add DNS record"}
      </h3>

      {submitted && errorCount > 0 && (
        <Alert tone="danger" className="mb-4" title={`${errorCount} field${errorCount > 1 ? "s" : ""} need${errorCount > 1 ? "" : "s"} attention`}>
          Fix the highlighted fields and try again. Nothing has been saved.
        </Alert>
      )}

      {/* responsive grid: 12 cols on lg; single column under 640px */}
      <div className="grid grid-cols-1 sm:grid-cols-6 lg:grid-cols-12 gap-x-4 gap-y-4">
        <Field label="Type" htmlFor={id("type")} required className="sm:col-span-2 lg:col-span-2">
          <Select ref={firstInput} id={id("type")} value={v.type} onChange={(e) => onTypeChange(e.target.value as RecordType)} options={RECORD_TYPES.map((t) => ({ value: t.value, label: t.label }))} />
        </Field>

        <Field
          label={
            <span className="inline-flex items-center gap-1">
              Name <InfoTip text="The hostname (domain or subdomain) this record applies to. Use @ for the root." />
            </span>
          }
          htmlFor={id("name")}
          required
          error={errors.name}
          hint={v.name && v.name !== "@" ? `Resolves as ${v.name.endsWith(ZONE) ? v.name : `${v.name}.${ZONE}`}` : "Use @ for root"}
          className="sm:col-span-4 lg:col-span-4"
        >
          <Input id={id("name")} value={v.name} onChange={(e) => set("name", e.target.value)} onBlur={() => blur("name")} invalid={!!errors.name} placeholder="@ or subdomain" autoComplete="off" spellCheck={false} />
        </Field>

        <Field label={meta.contentLabel} htmlFor={id("content")} required error={errors.content} hint={meta.help} className={cn("sm:col-span-6", v.type === "MX" || v.type === "SRV" ? "lg:col-span-4" : "lg:col-span-6")}>
          {v.type === "TXT" ? (
            <Textarea id={id("content")} rows={2} value={v.content} onChange={(e) => set("content", e.target.value)} onBlur={() => blur("content")} invalid={!!errors.content} placeholder={meta.placeholder} className="min-h-[36px] font-mono text-sm" />
          ) : (
            <Input id={id("content")} value={v.content} onChange={(e) => set("content", e.target.value)} onBlur={() => blur("content")} invalid={!!errors.content} placeholder={meta.placeholder} mono spellCheck={false} />
          )}
        </Field>

        {(v.type === "MX" || v.type === "SRV") && (
          <Field label="Priority" htmlFor={id("priority")} required error={errors.priority} className="sm:col-span-2 lg:col-span-2">
            <Input id={id("priority")} inputMode="numeric" value={v.priority} onChange={(e) => set("priority", e.target.value)} onBlur={() => blur("priority")} invalid={!!errors.priority} />
          </Field>
        )}

        {meta.proxyable && (
          <div className="sm:col-span-3 lg:col-span-4 flex flex-col gap-1.5">
            <span className="text-sm font-medium text-fg inline-flex items-center gap-1">
              Proxy status <InfoTip text="Proxied traffic flows through the edge, hiding your origin IP and enabling caching and WAF." />
            </span>
            <div className="h-9 flex items-center">
              <Toggle
                id={id("proxied")}
                checked={v.proxied}
                onChange={(c) => setV((s) => ({ ...s, proxied: c, ttl: c ? "1" : s.ttl }))}
                label={
                  <span className={cn("inline-flex items-center gap-1.5 text-base", v.proxied ? "text-fg" : "text-fg-2")}>
                    {v.proxied ? <Cloud className="size-4 text-brand fill-brand/20" /> : <CloudOff className="size-4 text-fg-3" />}
                    {v.proxied ? "Proxied" : "DNS only"}
                  </span>
                }
              />
            </div>
          </div>
        )}

        <Field label="TTL" htmlFor={id("ttl")} hint={v.proxied ? "Auto while proxied" : undefined} className="sm:col-span-3 lg:col-span-2">
          <Select id={id("ttl")} value={v.ttl} onChange={(e) => set("ttl", e.target.value)} options={TTL_OPTIONS} disabled={v.proxied} />
        </Field>

        <Field
          label="Comment"
          htmlFor={id("comment")}
          optional
          error={errors.comment}
          className="sm:col-span-6 lg:col-span-12"
          labelAside={<span className={cn("text-xs tabular-nums", v.comment.length > 100 ? "text-danger" : "text-fg-3")}>{v.comment.length}/100</span>}
        >
          <Input id={id("comment")} value={v.comment} onChange={(e) => set("comment", e.target.value)} onBlur={() => blur("comment")} invalid={!!errors.comment} placeholder="Internal note for your team" />
        </Field>
      </div>

      {/* actions: destructive on the far left, primary on the right; stacked on narrow */}
      <div className="mt-5 pt-4 border-t border-line flex flex-col-reverse sm:flex-row sm:items-center gap-2">
        {onDelete && (
          <Button variant="danger-outline" size="md" icon={<Trash2 className="size-4" />} onClick={onDelete} className="sm:mr-auto">
            Delete
          </Button>
        )}
        <div className="flex flex-col-reverse sm:flex-row gap-2 sm:ml-auto">
          <Button variant="secondary" onClick={onCancel}>
            Cancel
          </Button>
          <Button variant="primary" type="submit" loading={saving}>
            {initial ? "Save" : "Save record"}
          </Button>
        </div>
      </div>
    </form>
  );
}
