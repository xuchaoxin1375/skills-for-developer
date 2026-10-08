import { useEffect, useRef, useState, type FormEvent } from "react";
import { TriangleAlert } from "lucide-react";
import { navigate, setNavGuard } from "@/lib/route";
import { ConfirmDialog, Modal } from "@/ui/Modal";
import { Breadcrumbs, Field, PageHeader, Select, Spinner, Switch } from "@/ui/controls";
import { useToast } from "@/ui/Toast";
import { DOMAIN } from "../data";

interface Settings {
  mode: string;
  minTls: string;
  email: string;
  notifyExpiry: boolean;
  notifyRenewal: boolean;
}
const INITIAL: Settings = { mode: "full-strict", minTls: "1.2", email: "ops@myexample.com", notifyExpiry: true, notifyRenewal: true };

const MODES = [
  { v: "off", title: "Off", desc: "No encryption between visitors and Nimbus, or between Nimbus and your origin.", bad: true },
  { v: "flexible", title: "Flexible", desc: "Encrypts visitor traffic only. Your origin still receives plain HTTP." },
  { v: "full", title: "Full", desc: "End-to-end encryption. Accepts self-signed certificates on the origin." },
  { v: "full-strict", title: "Full (strict)", desc: "End-to-end encryption with a valid, trusted certificate on the origin.", rec: true },
];

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

function Row({ id, title, desc, children }: { id: string; title: string; desc: string; children: React.ReactNode }) {
  return (
    <section className="setrow" aria-labelledby={id}>
      <div className="min-w-0">
        <h2 id={id} className="text-base font-semibold">
          {title}
        </h2>
        <p className="mt-1 text-muted">{desc}</p>
      </div>
      <div className="min-w-0">{children}</div>
    </section>
  );
}

export function SettingsPage() {
  const { push } = useToast();
  const [saved, setSaved] = useState<Settings>(INITIAL);
  const [draft, setDraft] = useState<Settings>(INITIAL);
  const [https, setHttps] = useState(true);
  const [emailError, setEmailError] = useState<string>();
  const [saving, setSaving] = useState(false);
  const [leave, setLeave] = useState<(() => void) | null>(null);
  const [removeOpen, setRemoveOpen] = useState(false);
  const emailRef = useRef<HTMLInputElement>(null);

  const dirty = JSON.stringify(saved) !== JSON.stringify(draft);
  const dirtyRef = useRef(false);
  dirtyRef.current = dirty;

  useEffect(() => {
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
      setNavGuard(null);
      window.removeEventListener("beforeunload", before);
    };
  }, []);

  const set = <K extends keyof Settings>(k: K, v: Settings[K]) => setDraft((d) => ({ ...d, [k]: v }));

  const save = async (e: FormEvent) => {
    e.preventDefault();
    if (saving) return;
    if (!EMAIL_RE.test(draft.email.trim())) {
      setEmailError("Enter a valid email address, for example ops@myexample.com.");
      emailRef.current?.focus();
      return;
    }
    setEmailError(undefined);
    setSaving(true);
    await sleep(600);
    setSaving(false);
    setSaved(draft);
    push({ title: "SSL/TLS settings saved" });
  };

  return (
    <div>
      <Breadcrumbs items={[{ label: "SSL/TLS", to: "/dashboard/settings" }, { label: "Overview" }]} />
      <PageHeader title="SSL/TLS" description={`Choose how traffic to ${DOMAIN} is encrypted, and who is told when certificates change.`} />

      <form noValidate onSubmit={save} className="formgrid mt-6">
        <div className="card">
          <Row id="enc-h" title="Encryption mode" desc="Applies to all traffic for this domain. Changes are saved with the button below.">
            <div role="radiogroup" aria-labelledby="enc-h" className="grid gap-3">
              {MODES.map((m) => (
                <label key={m.v} className="choice">
                  <input type="radio" name="mode" value={m.v} checked={draft.mode === m.v} onChange={() => set("mode", m.v)} />
                  <span className="min-w-0">
                    <span className="flex flex-wrap items-center gap-2 font-semibold">
                      {m.title}
                      {m.rec && <span className="badge badge-ok">Recommended</span>}
                      {m.bad && (
                        <span className="badge badge-warn">
                          <TriangleAlert size={12} aria-hidden="true" />
                          Not secure
                        </span>
                      )}
                    </span>
                    <span className="mt-1 block text-muted">{m.desc}</span>
                  </span>
                </label>
              ))}
            </div>
          </Row>

          <Row id="tls-h" title="Minimum TLS version" desc="Visitors using older clients below this version are refused.">
            <Field label="Version" className="sm:max-w-xs" hint={draft.minTls < "1.2" ? "Versions below 1.2 are deprecated and not recommended." : undefined}>
              {(p) => (
                <Select {...p} value={draft.minTls} onChange={(e) => set("minTls", e.target.value)}>
                  <option value="1.0">TLS 1.0 (deprecated)</option>
                  <option value="1.1">TLS 1.1 (deprecated)</option>
                  <option value="1.2">TLS 1.2 (recommended)</option>
                  <option value="1.3">TLS 1.3</option>
                </Select>
              )}
            </Field>
          </Row>

          <Row id="https-h" title="Always use HTTPS" desc="Redirect all HTTP requests to HTTPS. Applied instantly — no save needed.">
            <div className="flex items-center justify-between gap-4">
              <span id="https-l" className="font-medium">
                {https ? "On" : "Off"}
              </span>
              <Switch
                checked={https}
                aria-labelledby="https-h"
                onChange={(v) => {
                  setHttps(v);
                  push({ title: `Always use HTTPS turned ${v ? "on" : "off"}`, tone: "info" });
                }}
              />
            </div>
          </Row>

          <Row id="notify-h" title="Certificate notifications" desc="Who should hear about certificate issues and when.">
            <div className="grid gap-4">
              <Field label="Notification email" required error={emailError}>
                {(p) => (
                  <input
                    {...p}
                    ref={emailRef}
                    type="email"
                    className="input"
                    autoComplete="email"
                    value={draft.email}
                    onChange={(e) => {
                      set("email", e.target.value);
                      if (emailError) setEmailError(undefined);
                    }}
                  />
                )}
              </Field>
              <fieldset className="group grid gap-1">
                <legend className="mb-1">Notify me when</legend>
                <label className="flex min-h-9 items-center gap-3">
                  <input type="checkbox" className="checkbox" checked={draft.notifyExpiry} onChange={(e) => set("notifyExpiry", e.target.checked)} />
                  A certificate is about to expire
                </label>
                <label className="flex min-h-9 items-center gap-3">
                  <input type="checkbox" className="checkbox" checked={draft.notifyRenewal} onChange={(e) => set("notifyRenewal", e.target.checked)} />
                  Automatic renewal fails
                </label>
              </fieldset>
            </div>
          </Row>
        </div>

        {dirty && (
          <div className="actionbar mt-4 rounded-lg border" role="region" aria-label="Unsaved changes">
            <p className="grow text-sm font-medium" aria-live="polite">
              You have unsaved changes
            </p>
            <button type="button" className="btn" onClick={() => { setDraft(saved); setEmailError(undefined); }}>
              Discard
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
        )}
      </form>

      {/* 危险区：远离首屏、视觉上与普通设置分隔、需要二次确认 */}
      <section className="mt-12 max-w-4xl rounded-lg border border-danger" aria-labelledby="danger-h">
        <div className="flex flex-wrap items-center justify-between gap-4 p-6 max-sm:p-4">
          <div className="min-w-0 flex-1 basis-64">
            <h2 id="danger-h" className="text-base font-semibold text-danger">
              Remove site
            </h2>
            <p className="mt-1 text-muted">Removing {DOMAIN} deletes its DNS records and settings. This cannot be undone.</p>
          </div>
          <button type="button" className="btn btn-danger" onClick={() => setRemoveOpen(true)}>
            Remove site…
          </button>
        </div>
      </section>

      <Modal open={removeOpen} onClose={() => setRemoveOpen(false)} label="Remove site">
        <RemoveBody
          onClose={() => setRemoveOpen(false)}
          onRemoved={() => {
            setRemoveOpen(false);
            push({ title: `${DOMAIN} was removed (demo only)`, tone: "info" });
            navigate("/dashboard/sites", { force: true });
          }}
        />
      </Modal>

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
          setLeave(null);
          go?.();
        }}
      >
        <p>Your SSL/TLS changes haven’t been saved yet.</p>
      </ConfirmDialog>
    </div>
  );
}

/** 输入域名确认：按钮保持可用，错误通过校验反馈（而非禁用按钮） */
function RemoveBody({ onClose, onRemoved }: { onClose: () => void; onRemoved: () => void }) {
  const [v, setV] = useState("");
  const [err, setErr] = useState<string>();
  const ref = useRef<HTMLInputElement>(null);
  return (
    <form
      noValidate
      onSubmit={(e) => {
        e.preventDefault();
        if (v.trim() !== DOMAIN) {
          setErr(`Type “${DOMAIN}” exactly to confirm.`);
          ref.current?.focus();
        } else onRemoved();
      }}
    >
      <div className="grid gap-4 p-6">
        <h2 className="text-xl font-semibold">Remove {DOMAIN}?</h2>
        <p className="text-muted">All DNS records, certificates and rules for this site will be permanently deleted.</p>
        <Field label={`Type ${DOMAIN} to confirm`} required error={err}>
          {(p) => (
            <input
              {...p}
              ref={ref}
              data-autofocus
              className="input"
              value={v}
              autoComplete="off"
              spellCheck={false}
              onChange={(e) => {
                setV(e.target.value);
                setErr(undefined);
              }}
            />
          )}
        </Field>
      </div>
      <div className="flex flex-wrap justify-end gap-3 border-t border-line px-6 py-4">
        <button type="button" className="btn" onClick={onClose}>
          Cancel
        </button>
        <button type="submit" className="btn btn-danger">
          Remove site
        </button>
      </div>
    </form>
  );
}
