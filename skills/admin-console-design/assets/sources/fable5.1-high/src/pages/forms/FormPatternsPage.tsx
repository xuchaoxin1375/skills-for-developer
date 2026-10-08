import { useEffect, useMemo, useRef, useState } from "react";
import { Check, ChevronLeft, ChevronRight, Globe, Server, Shield, Zap } from "lucide-react";
import { cn } from "@/utils/cn";
import { Button, Checkbox, Field, Input, RadioCards, Select, Textarea, Toggle } from "@/components/ui/primitives";
import { Alert, Card, CardBody, CardHeader, PageHeader } from "@/components/ui/layout";
import { useToast } from "@/components/ui/overlays";

/* =====================================================================
   1) Long form: grouped sections + sticky outline + sticky action bar
   ===================================================================== */
interface CreateValues {
  name: string;
  hostname: string;
  env: "production" | "staging" | "dev";
  originType: "ip" | "hostname" | "lb";
  origin: string;
  port: string;
  tls: boolean;
  caching: "standard" | "aggressive" | "bypass";
  rateLimit: string;
  waf: boolean;
  botFight: boolean;
  notes: string;
  tags: string[];
  agree: boolean;
}

const initialCreate: CreateValues = {
  name: "",
  hostname: "",
  env: "production",
  originType: "ip",
  origin: "",
  port: "443",
  tls: true,
  caching: "standard",
  rateLimit: "",
  waf: true,
  botFight: false,
  notes: "",
  tags: [],
  agree: false,
};

type CErr = Partial<Record<keyof CreateValues, string>>;
function validateCreate(v: CreateValues): CErr {
  const e: CErr = {};
  if (!v.name.trim()) e.name = "Application name is required.";
  else if (v.name.length > 64) e.name = "Keep the name under 64 characters.";
  if (!v.hostname.trim()) e.hostname = "Hostname is required.";
  else if (!/^[a-z0-9.-]+\.[a-z]{2,}$/i.test(v.hostname.trim())) e.hostname = "Enter a fully-qualified hostname, e.g. app.example.com.";
  if (!v.origin.trim()) e.origin = v.originType === "ip" ? "Origin IP is required." : "Origin target is required.";
  else if (v.originType === "ip" && !/^(\d{1,3}\.){3}\d{1,3}$/.test(v.origin.trim())) e.origin = "Enter a valid IPv4 address.";
  const port = Number(v.port);
  if (!Number.isInteger(port) || port < 1 || port > 65535) e.port = "Port must be between 1 and 65535.";
  if (v.rateLimit && (!Number.isInteger(Number(v.rateLimit)) || Number(v.rateLimit) < 1)) e.rateLimit = "Enter a positive integer, or leave blank to disable.";
  if (v.notes.length > 500) e.notes = "Notes must be 500 characters or fewer.";
  if (!v.agree) e.agree = "You must accept the terms to continue.";
  return e;
}

const SECTIONS = [
  { id: "basics", label: "Basics", icon: Globe },
  { id: "origin", label: "Origin", icon: Server },
  { id: "performance", label: "Performance", icon: Zap },
  { id: "security", label: "Security", icon: Shield },
  { id: "review", label: "Review", icon: Check },
];

function useScrollSpy(ids: string[]) {
  const [active, setActive] = useState(ids[0]);
  useEffect(() => {
    const els = ids.map((id) => document.getElementById(id)).filter(Boolean) as HTMLElement[];
    if (!els.length) return;
    const io = new IntersectionObserver(
      (entries) => {
        const vis = entries.filter((e) => e.isIntersecting).sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top);
        if (vis[0]) setActive(vis[0].target.id);
      },
      { rootMargin: "-80px 0px -60% 0px", threshold: [0, 1] }
    );
    els.forEach((el) => io.observe(el));
    return () => io.disconnect();
  }, [ids]);
  return active;
}

export function CreateFormPage() {
  const { toast } = useToast();
  const [v, setV] = useState<CreateValues>(initialCreate);
  const [touched, setTouched] = useState<Partial<Record<keyof CreateValues, boolean>>>({});
  const [submitted, setSubmitted] = useState(false);
  const [saving, setSaving] = useState(false);
  const [tagInput, setTagInput] = useState("");
  const form = useRef<HTMLFormElement>(null);
  const ids = useMemo(() => SECTIONS.map((s) => s.id), []);
  const activeSection = useScrollSpy(ids);

  const all = useMemo(() => validateCreate(v), [v]);
  const err = (k: keyof CreateValues) => (submitted || touched[k] ? all[k] : undefined);
  const set = <K extends keyof CreateValues>(k: K, val: CreateValues[K]) => setV((s) => ({ ...s, [k]: val }));
  const blur = (k: keyof CreateValues) => setTouched((t) => ({ ...t, [k]: true }));
  const dirty = JSON.stringify(v) !== JSON.stringify(initialCreate);
  const sectionErrors = (keys: (keyof CreateValues)[]) => keys.filter((k) => err(k)).length;

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitted(true);
    if (Object.keys(all).length) {
      const el = form.current?.querySelector<HTMLElement>("[aria-invalid='true'], [data-invalid='true'] input");
      el?.focus();
      el?.scrollIntoView({ block: "center", behavior: "smooth" });
      toast({ tone: "error", title: `${Object.keys(all).length} fields need attention`, description: "Your input has been kept. Fix the highlighted fields." });
      return;
    }
    setSaving(true);
    await new Promise((r) => setTimeout(r, 600));
    setSaving(false);
    toast({ tone: "success", title: "Application created", description: `${v.name} → ${v.hostname}` });
    setV(initialCreate);
    setSubmitted(false);
    setTouched({});
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  const addTag = () => {
    const t = tagInput.trim().toLowerCase();
    if (t && !v.tags.includes(t) && v.tags.length < 8) set("tags", [...v.tags, t]);
    setTagInput("");
  };

  return (
    <>
      <PageHeader
        title="Create application"
        breadcrumb={<span>Form Patterns / <span className="text-fg">Create</span></span>}
        description="Long form pattern: 14 fields grouped into 4 sections, sticky outline on wide screens, single column under 1024px, sticky action bar when dirty."
      />

      <form ref={form} noValidate onSubmit={submit} className="grid grid-cols-1 lg:grid-cols-[minmax(0,1fr)_240px] gap-6 items-start">
        <div className="space-y-6 min-w-0">
          {submitted && Object.keys(all).length > 0 && (
            <Alert tone="danger" title="Please fix the errors below">
              <ul className="list-disc pl-4 mt-1 space-y-0.5">
                {(Object.keys(all) as (keyof CreateValues)[]).map((k) => (
                  <li key={k}>
                    <button type="button" className="underline underline-offset-2" onClick={() => document.getElementById(`c-${k}`)?.focus()}>
                      {all[k]}
                    </button>
                  </li>
                ))}
              </ul>
            </Alert>
          )}

          <Card id="basics" className="scroll-mt-20">
            <CardHeader title="Basics" description="How the application is identified." />
            <CardBody className="pt-0 grid grid-cols-1 md:grid-cols-2 gap-4">
              <Field label="Application name" htmlFor="c-name" required error={err("name")} hint="Shown in lists and alerts.">
                <Input id="c-name" value={v.name} onChange={(e) => set("name", e.target.value)} onBlur={() => blur("name")} invalid={!!err("name")} placeholder="Marketing site" autoComplete="off" />
              </Field>
              <Field label="Public hostname" htmlFor="c-hostname" required error={err("hostname")}>
                <Input id="c-hostname" value={v.hostname} onChange={(e) => set("hostname", e.target.value)} onBlur={() => blur("hostname")} invalid={!!err("hostname")} placeholder="app.myexample.com" mono spellCheck={false} />
              </Field>
              <div className="md:col-span-2">
                <p className="text-sm font-medium text-fg mb-1.5">Environment</p>
                <RadioCards
                  name="env"
                  value={v.env}
                  onChange={(x) => set("env", x)}
                  columns={3}
                  options={[
                    { value: "production", label: "Production", description: "Full protection and caching." },
                    { value: "staging", label: "Staging", description: "Access-restricted preview." },
                    { value: "dev", label: "Development", description: "Caching bypassed." },
                  ]}
                />
              </div>
              <div className="md:col-span-2">
                <Field label="Tags" htmlFor="c-tags" optional hint="Press Enter or comma to add. Up to 8.">
                  <div className="flex flex-wrap items-center gap-1.5 min-h-9 px-2 py-1 rounded-sm border border-line bg-surface focus-within:border-primary focus-within:ring-2 focus-within:ring-primary/30">
                    {v.tags.map((t) => (
                      <span key={t} className="inline-flex items-center gap-1 h-6 pl-2 pr-1 rounded-xs bg-surface-3 text-sm text-fg">
                        {t}
                        <button type="button" aria-label={`Remove tag ${t}`} onClick={() => set("tags", v.tags.filter((x) => x !== t))} className="size-5 inline-flex items-center justify-center rounded-xs hover:bg-line-strong">×</button>
                      </span>
                    ))}
                    <input
                      id="c-tags"
                      value={tagInput}
                      onChange={(e) => setTagInput(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" || e.key === ",") { e.preventDefault(); addTag(); }
                        else if (e.key === "Backspace" && !tagInput && v.tags.length) set("tags", v.tags.slice(0, -1));
                      }}
                      onBlur={addTag}
                      placeholder={v.tags.length ? "" : "team-web, critical"}
                      className="flex-1 min-w-[120px] h-7 bg-transparent text-base outline-none placeholder:text-fg-3"
                    />
                  </div>
                </Field>
              </div>
            </CardBody>
          </Card>

          <Card id="origin" className="scroll-mt-20">
            <CardHeader title="Origin" description="Where requests are sent after passing the edge." />
            <CardBody className="pt-0 space-y-4">
              <RadioCards
                name="originType"
                value={v.originType}
                onChange={(x) => set("originType", x)}
                columns={3}
                options={[
                  { value: "ip", label: "IP address" },
                  { value: "hostname", label: "Hostname" },
                  { value: "lb", label: "Load balancer" },
                ]}
              />
              <div className="grid grid-cols-1 md:grid-cols-[minmax(0,1fr)_140px] gap-4">
                <Field label={v.originType === "ip" ? "Origin IP" : v.originType === "hostname" ? "Origin hostname" : "Load balancer"} htmlFor="c-origin" required error={err("origin")}>
                  {v.originType === "lb" ? (
                    <Select id="c-origin" value={v.origin} onChange={(e) => set("origin", e.target.value)} onBlur={() => blur("origin")} invalid={!!err("origin")} placeholder="Select a load balancer" options={[{ value: "lb-eu", label: "lb-eu-west (3 origins)" }, { value: "lb-us", label: "lb-us-east (2 origins)" }]} />
                  ) : (
                    <Input id="c-origin" value={v.origin} onChange={(e) => set("origin", e.target.value)} onBlur={() => blur("origin")} invalid={!!err("origin")} placeholder={v.originType === "ip" ? "203.0.113.10" : "origin.internal.example"} mono spellCheck={false} />
                  )}
                </Field>
                <Field label="Port" htmlFor="c-port" required error={err("port")}>
                  <Input id="c-port" inputMode="numeric" value={v.port} onChange={(e) => set("port", e.target.value)} onBlur={() => blur("port")} invalid={!!err("port")} />
                </Field>
              </div>
              <Toggle checked={v.tls} onChange={(x) => set("tls", x)} label="Verify origin TLS certificate" description="Recommended. Disable only for self-signed certificates in development." />
            </CardBody>
          </Card>

          <Card id="performance" className="scroll-mt-20">
            <CardHeader title="Performance" description="Caching and rate limiting defaults." />
            <CardBody className="pt-0 grid grid-cols-1 md:grid-cols-2 gap-4">
              <Field label="Cache level" htmlFor="c-caching">
                <Select id="c-caching" value={v.caching} onChange={(e) => set("caching", e.target.value as CreateValues["caching"])} options={[{ value: "standard", label: "Standard" }, { value: "aggressive", label: "Aggressive (ignore query string)" }, { value: "bypass", label: "Bypass" }]} />
              </Field>
              <Field label="Rate limit (req/min)" htmlFor="c-rateLimit" optional error={err("rateLimit")} hint="Leave blank to disable.">
                <Input id="c-rateLimit" inputMode="numeric" value={v.rateLimit} onChange={(e) => set("rateLimit", e.target.value)} onBlur={() => blur("rateLimit")} invalid={!!err("rateLimit")} placeholder="600" />
              </Field>
            </CardBody>
          </Card>

          <Card id="security" className="scroll-mt-20">
            <CardHeader title="Security" description="Edge protections applied to this application." />
            <CardBody className="pt-0 space-y-4">
              <Toggle checked={v.waf} onChange={(x) => set("waf", x)} label="Managed WAF rules" description="Blocks OWASP top-10 attack patterns." />
              <Toggle checked={v.botFight} onChange={(x) => set("botFight", x)} label="Bot fight mode" description="Challenges requests that look automated. May affect legitimate API clients." />
              <Field label="Notes" htmlFor="c-notes" optional error={err("notes")} labelAside={<span className={cn("text-xs tabular-nums", v.notes.length > 500 ? "text-danger" : "text-fg-3")}>{v.notes.length}/500</span>}>
                <Textarea id="c-notes" value={v.notes} onChange={(e) => set("notes", e.target.value)} onBlur={() => blur("notes")} invalid={!!err("notes")} placeholder="Why does this application exist? Who owns it?" />
              </Field>
            </CardBody>
          </Card>

          <Card id="review" className="scroll-mt-20">
            <CardHeader title="Review" description="Summary of what will be created." />
            <CardBody className="pt-0">
              <dl className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-2 text-base mb-4">
                {[
                  ["Name", v.name || "—"],
                  ["Hostname", v.hostname || "—"],
                  ["Environment", v.env],
                  ["Origin", v.origin ? `${v.origin}:${v.port}` : "—"],
                  ["Cache", v.caching],
                  ["WAF", v.waf ? "On" : "Off"],
                ].map(([k, val]) => (
                  <div key={k} className="flex justify-between gap-3 border-b border-line py-1.5 min-w-0">
                    <dt className="text-fg-3">{k}</dt>
                    <dd className="text-fg truncate font-mono text-sm">{val}</dd>
                  </div>
                ))}
              </dl>
              <div data-invalid={!!err("agree")} className={cn("p-3 rounded-sm border", err("agree") ? "border-danger bg-danger-soft/40" : "border-line")}>
                <Checkbox id="c-agree" checked={v.agree} onChange={(x) => { set("agree", x); blur("agree"); }} label="I understand that traffic for this hostname will be routed through the edge." />
                {err("agree") && <p className="text-xs text-danger mt-1.5 ml-8" role="alert">{err("agree")}</p>}
              </div>
            </CardBody>
          </Card>
        </div>

        {/* sticky outline: ≥ lg only */}
        <aside className="hidden lg:block sticky top-[calc(var(--topbar-h)_+_24px)]">
          <p className="text-2xs font-semibold uppercase tracking-wide text-fg-3 px-2 mb-2">On this page</p>
          <nav aria-label="Form sections">
            <ul className="space-y-0.5">
              {SECTIONS.map((s) => {
                const n = sectionErrors(
                  s.id === "basics" ? ["name", "hostname"] : s.id === "origin" ? ["origin", "port"] : s.id === "performance" ? ["rateLimit"] : s.id === "security" ? ["notes"] : ["agree"]
                );
                return (
                  <li key={s.id}>
                    <a
                      href={`#${s.id}`}
                      onClick={(e) => { e.preventDefault(); document.getElementById(s.id)?.scrollIntoView({ behavior: "smooth", block: "start" }); }}
                      aria-current={activeSection === s.id ? "location" : undefined}
                      className={cn("flex items-center gap-2 h-8 px-2 rounded-sm text-sm border-l-2 -ml-px", activeSection === s.id ? "border-primary text-fg font-medium bg-surface-3" : "border-transparent text-fg-2 hover:text-fg hover:bg-surface-3")}
                    >
                      <s.icon className="size-3.5 text-fg-3" aria-hidden />
                      <span className="flex-1">{s.label}</span>
                      {n > 0 && <span className="size-5 rounded-full bg-danger text-white text-2xs flex items-center justify-center">{n}</span>}
                    </a>
                  </li>
                );
              })}
            </ul>
          </nav>
          <div className="mt-4 pt-4 border-t border-line flex flex-col gap-2">
            <Button variant="primary" type="submit" loading={saving}>Create application</Button>
            <Button variant="secondary" onClick={() => { setV(initialCreate); setTouched({}); setSubmitted(false); }} disabled={!dirty}>Reset</Button>
          </div>
        </aside>

        {/* sticky action bar for < lg (and as a dirty indicator everywhere) */}
        <div className={cn("lg:hidden sticky bottom-0 -mx-4 sm:-mx-6 px-4 sm:px-6 py-3 bg-surface/95 backdrop-blur-sm border-t border-line flex items-center justify-between gap-3 transition-transform", dirty ? "translate-y-0" : "translate-y-full pointer-events-none")}
          aria-hidden={!dirty}>
          <span className="text-sm text-fg-2 truncate">Unsaved changes</span>
          <div className="flex gap-2 shrink-0">
            <Button size="md" onClick={() => { setV(initialCreate); setTouched({}); setSubmitted(false); }}>Discard</Button>
            <Button size="md" variant="primary" type="submit" loading={saving}>Create</Button>
          </div>
        </div>
      </form>
    </>
  );
}

/* =====================================================================
   2) Wizard: 3 steps, values retained, linear progress, summary last
   ===================================================================== */
const STEPS = ["Domain", "Plan", "Confirm"]; // wizard steps

export function WizardPage() {
  const { toast } = useToast();
  const [step, setStep] = useState(0);
  const [domain, setDomain] = useState("");
  const [plan, setPlan] = useState<"free" | "pro" | "business">("free");
  const [touched, setTouched] = useState(false);
  const domainErr = !domain.trim() ? "Enter the domain you want to add." : !/^[a-z0-9-]+(\.[a-z0-9-]+)+$/i.test(domain.trim()) ? "Enter a valid domain, e.g. example.com (no https://)." : undefined;
  const heading = useRef<HTMLHeadingElement>(null);

  const go = (n: number) => {
    setStep(n);
    requestAnimationFrame(() => heading.current?.focus());
  };

  return (
    <>
      <PageHeader title="Add a domain" breadcrumb={<span>Form Patterns / <span className="text-fg">Wizard</span></span>} description="Stepper pattern for sequential decisions. Back never loses data; the last step is a review." />

      <div className="max-w-[760px]">
        {/* progress */}
        <ol className="flex items-center gap-2 mb-6" aria-label="Progress">
          {STEPS.map((s, i) => {
            const state = i < step ? "done" : i === step ? "current" : "todo";
            return (
              <li key={s} className="flex items-center gap-2 flex-1 min-w-0 last:flex-none">
                <button
                  type="button"
                  disabled={i > step}
                  onClick={() => go(i)}
                  aria-current={state === "current" ? "step" : undefined}
                  className="flex items-center gap-2 min-w-0 disabled:cursor-not-allowed"
                >
                  <span className={cn("size-7 shrink-0 rounded-full border text-xs font-semibold flex items-center justify-center", state === "done" && "bg-success border-success text-white", state === "current" && "bg-primary border-primary text-white", state === "todo" && "border-line-strong text-fg-3")}>
                    {state === "done" ? <Check className="size-4" /> : i + 1}
                  </span>
                  <span className={cn("text-sm truncate hidden sm:inline", state === "current" ? "text-fg font-medium" : "text-fg-3")}>{s}</span>
                </button>
                {i < STEPS.length - 1 && <span className={cn("h-px flex-1 min-w-4", i < step ? "bg-success" : "bg-line")} aria-hidden />}
              </li>
            );
          })}
        </ol>

        <Card>
          <CardBody>
            <h2 ref={heading} tabIndex={-1} className="text-lg font-semibold text-fg mb-1 outline-none">
              Step {step + 1} of {STEPS.length}: {STEPS[step]}
            </h2>

            {step === 0 && (
              <div className="mt-4 max-w-md">
                <Field label="Domain name" htmlFor="w-domain" required error={touched ? domainErr : undefined} hint="Enter the apex domain only; subdomains are added later as records.">
                  <Input id="w-domain" value={domain} onChange={(e) => setDomain(e.target.value)} onBlur={() => setTouched(true)} invalid={touched && !!domainErr} placeholder="example.com" mono autoFocus spellCheck={false} />
                </Field>
              </div>
            )}

            {step === 1 && (
              <div className="mt-4">
                <RadioCards
                  name="plan"
                  value={plan}
                  onChange={setPlan}
                  columns={3}
                  options={[
                    { value: "free", label: "Free", description: "$0 / month. DNS, CDN, basic DDoS." },
                    { value: "pro", label: "Pro", description: "$20 / month. WAF, image optimization." },
                    { value: "business", label: "Business", description: "$200 / month. SLA, custom certs." },
                  ]}
                />
              </div>
            )}

            {step === 2 && (
              <div className="mt-4 space-y-3">
                <dl className="text-base divide-y divide-line">
                  <div className="flex justify-between py-2"><dt className="text-fg-3">Domain</dt><dd className="font-mono text-sm">{domain}</dd></div>
                  <div className="flex justify-between py-2"><dt className="text-fg-3">Plan</dt><dd className="capitalize">{plan}</dd></div>
                </dl>
                <Alert tone="info">We will scan existing DNS records so you can import them in the next step.</Alert>
              </div>
            )}
          </CardBody>
          <div className="px-4 sm:px-5 py-3 border-t border-line flex items-center justify-between gap-2">
            <Button variant="ghost" icon={<ChevronLeft className="size-4" />} onClick={() => go(step - 1)} disabled={step === 0}>
              Back
            </Button>
            {step < STEPS.length - 1 ? (
              <Button variant="primary" iconRight={<ChevronRight className="size-4" />} onClick={() => { if (step === 0) { setTouched(true); if (domainErr) { document.getElementById("w-domain")?.focus(); return; } } go(step + 1); }}>
                Continue
              </Button>
            ) : (
              <Button variant="primary" onClick={() => { toast({ tone: "success", title: `${domain} added`, description: `${plan} plan` }); setStep(0); setDomain(""); setTouched(false); }}>
                Add domain
              </Button>
            )}
          </div>
        </Card>
      </div>
    </>
  );
}
