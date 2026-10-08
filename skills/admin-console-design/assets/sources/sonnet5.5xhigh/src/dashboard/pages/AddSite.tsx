import { useEffect, useRef, useState } from "react";
import { Check } from "lucide-react";
import { navigate, setNavGuard } from "@/lib/route";
import { ConfirmDialog } from "@/ui/Modal";
import { Breadcrumbs, Field, PageHeader } from "@/ui/controls";
import { useToast } from "@/ui/Toast";
import { cn } from "@/utils/cn";
import { useData } from "../data";

const STEPS = ["Domain", "Plan", "Review"];
const PLANS = [
  { v: "Free", price: "$0", note: "per month", feats: "Universal SSL, basic DDoS protection, global CDN" },
  { v: "Pro", price: "$25", note: "per month", feats: "Everything in Free, WAF managed rules, image optimization" },
  { v: "Business", price: "$250", note: "per month", feats: "Everything in Pro, custom WAF rules, 100% uptime SLA" },
];
const DOMAIN_RE = /^(?!-)([a-z0-9-]{1,63}\.)+[a-z]{2,}$/;

/** 粘贴 URL 也能用：去掉协议、路径、端口与首尾空白 */
const normalizeDomain = (v: string) =>
  v
    .trim()
    .toLowerCase()
    .replace(/^[a-z]+:\/\//, "")
    .replace(/[/?#:].*$/, "");

/** 分步表单（> 7 项 / 逻辑上分阶段）：每步只做一件事，Review 汇总并允许回改 */
export function AddSiteWizard() {
  const { sites, addSite } = useData();
  const { push } = useToast();
  const [step, setStep] = useState(0);
  const [domain, setDomain] = useState("");
  const [plan, setPlan] = useState("Free");
  const [confirmOwn, setConfirmOwn] = useState(false);
  const [errors, setErrors] = useState<{ domain?: string; confirm?: string }>({});
  const [leave, setLeave] = useState<(() => void) | null>(null);
  const headingRef = useRef<HTMLHeadingElement>(null);
  const domainRef = useRef<HTMLInputElement>(null);
  const confirmRef = useRef<HTMLInputElement>(null);
  const done = useRef(false);
  const first = useRef(true);

  const dirtyRef = useRef(false);
  dirtyRef.current = !done.current && (domain !== "" || plan !== "Free" || step > 0);

  useEffect(() => {
    setNavGuard((proceed) => {
      if (!dirtyRef.current) return false;
      setLeave(() => proceed);
      return true;
    });
    return () => setNavGuard(null);
  }, []);

  useEffect(() => {
    if (first.current) {
      first.current = false;
      return;
    }
    headingRef.current?.focus();
  }, [step]);

  const validateDomain = (v: string): string | undefined => {
    if (!v) return "Enter the domain you want to add, for example example.com.";
    if (!DOMAIN_RE.test(v)) return "That doesn’t look like a domain. Use a name like example.com (no spaces or paths).";
    if (sites.some((s) => s.name === v)) return `${v} is already on this account.`;
  };

  const next = () => {
    if (step === 0) {
      const d = normalizeDomain(domain);
      setDomain(d);
      const err = validateDomain(d);
      setErrors({ domain: err });
      if (err) return void domainRef.current?.focus();
    }
    if (step === 2) {
      if (!confirmOwn) {
        setErrors({ confirm: "Confirm that you are allowed to manage this domain." });
        return void confirmRef.current?.focus();
      }
      done.current = true;
      addSite(domain, plan);
      push({ title: `${domain} added — complete the setup to activate it` });
      return navigate("/dashboard/sites", { force: true });
    }
    setErrors({});
    setStep((s) => s + 1);
  };

  return (
    <div>
      <Breadcrumbs items={[{ label: "Domains", to: "/dashboard/sites" }, { label: "Add a site" }]} />
      <PageHeader title="Add a site" description="Connect a domain in three short steps. You can change the plan later." />

      <nav aria-label="Progress" className="mt-6">
        <p className="text-sm font-medium sm:hidden">
          Step {step + 1} of {STEPS.length}: {STEPS[step]}
        </p>
        <ol className="hidden items-center gap-3 sm:flex">
          {STEPS.map((s, i) => (
            <li key={s} className="flex items-center gap-3" aria-current={i === step ? "step" : undefined}>
              <span
                className={cn(
                  "inline-flex size-6 items-center justify-center rounded-full border text-xs font-semibold",
                  i < step ? "border-primary bg-primary text-white" : i === step ? "border-primary text-link" : "border-line-strong text-muted",
                )}
              >
                {i < step ? <Check size={14} aria-label="Completed" /> : i + 1}
              </span>
              <span className={cn("font-medium", i === step ? "text-fg" : "text-muted")}>{s}</span>
              {i < STEPS.length - 1 && <span aria-hidden="true" className="h-px w-8 bg-line-strong" />}
            </li>
          ))}
        </ol>
        <div className="mt-3 h-1 overflow-hidden rounded-full bg-active sm:hidden" aria-hidden="true">
          <div className="h-full bg-primary transition-[width] duration-300" style={{ width: `${((step + 1) / STEPS.length) * 100}%` }} />
        </div>
      </nav>

      <form
        noValidate
        className="card mt-6 max-w-3xl"
        onSubmit={(e) => {
          e.preventDefault();
          next();
        }}
      >
        <div className="card-pad grid gap-6">
          <h2 ref={headingRef} tabIndex={-1} className="text-xl font-semibold">
            {step === 0 ? "Enter your domain" : step === 1 ? "Select a plan" : "Review and confirm"}
          </h2>

          {step === 0 && (
            <Field label="Domain name" required error={errors.domain} hint="Paste a URL if you like — we’ll keep just the domain.">
              {(p) => (
                <input
                  {...p}
                  ref={domainRef}
                  className="input"
                  inputMode="url"
                  autoCapitalize="none"
                  spellCheck={false}
                  autoComplete="off"
                  placeholder="example.com"
                  value={domain}
                  onChange={(e) => {
                    setDomain(e.target.value);
                    if (errors.domain) setErrors({});
                  }}
                  onBlur={() => domain && setDomain(normalizeDomain(domain))}
                />
              )}
            </Field>
          )}

          {step === 1 && (
            <div role="radiogroup" aria-label="Plan" className="grid gap-3">
              {PLANS.map((p) => (
                <label key={p.v} className="choice">
                  <input type="radio" name="plan" checked={plan === p.v} onChange={() => setPlan(p.v)} />
                  <span className="flex min-w-0 flex-1 flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
                    <span className="min-w-0">
                      <span className="block font-semibold">{p.v}</span>
                      <span className="block text-muted">{p.feats}</span>
                    </span>
                    <span className="font-semibold">
                      {p.price} <span className="text-sm font-normal text-muted">{p.note}</span>
                    </span>
                  </span>
                </label>
              ))}
            </div>
          )}

          {step === 2 && (
            <>
              <dl className="grid gap-3">
                {[
                  { k: "Domain", v: domain, to: 0 },
                  { k: "Plan", v: plan, to: 1 },
                ].map((r) => (
                  <div key={r.k} className="flex flex-wrap items-center justify-between gap-3 border-b border-line pb-3">
                    <div className="min-w-0">
                      <dt className="text-sm text-muted">{r.k}</dt>
                      <dd className="break-all font-semibold">{r.v}</dd>
                    </div>
                    <button type="button" className="link" onClick={() => setStep(r.to)}>
                      Change<span className="sr-only"> {r.k.toLowerCase()}</span>
                    </button>
                  </div>
                ))}
              </dl>
              <Field label="Ownership" error={errors.confirm} name="confirm">
                {(p) => (
                  <label className="flex items-start gap-3">
                    <input
                      {...p}
                      ref={confirmRef}
                      type="checkbox"
                      className="checkbox mt-1"
                      checked={confirmOwn}
                      onChange={(e) => {
                        setConfirmOwn(e.target.checked);
                        setErrors({});
                      }}
                    />
                    <span>I own this domain or have permission to manage its DNS.</span>
                  </label>
                )}
              </Field>
            </>
          )}
        </div>
        <div className="actionbar rounded-b-lg">
          <div className="grow" />
          {step === 0 ? (
            <button type="button" className="btn" onClick={() => navigate("/dashboard/sites")}>
              Cancel
            </button>
          ) : (
            <button type="button" className="btn" onClick={() => setStep((s) => s - 1)}>
              Back
            </button>
          )}
          <button type="submit" className="btn btn-primary">
            {step === 2 ? "Add site" : "Continue"}
          </button>
        </div>
      </form>

      <ConfirmDialog
        open={leave !== null}
        title="Leave without finishing?"
        confirmLabel="Leave"
        cancelLabel="Stay"
        danger
        onCancel={() => setLeave(null)}
        onConfirm={() => {
          const go = leave;
          dirtyRef.current = false;
          done.current = true;
          setLeave(null);
          go?.();
        }}
      >
        <p>Your progress in this form will be lost.</p>
      </ConfirmDialog>
    </div>
  );
}
