import { CircleCheck, Plus } from "lucide-react";
import { Link } from "@/lib/route";
import { PageHeader } from "@/ui/controls";
import { DOMAIN, useData } from "../data";
import { PAGE_TITLES } from "../nav";

const STATS = [
  { k: "Requests (24h)", v: "12.4k", d: "+8% vs. yesterday" },
  { k: "Cached", v: "68%", d: "Of total requests" },
  { k: "Threats blocked", v: "214", d: "Last 24 hours" },
  { k: "Bandwidth", v: "3.2 GB", d: "Served from edge" },
];

const STEPS = [
  { t: "Add your domain", done: true },
  { t: "Review imported DNS records", done: true },
  { t: "Change nameservers at your registrar", done: false, to: "/dashboard/p/nameservers" },
  { t: "Enable Always use HTTPS", done: true },
  { t: "Verify ownership", done: false, to: "/dashboard/p/verify" },
];

export function Overview() {
  const done = STEPS.filter((s) => s.done).length;
  return (
    <div>
      <PageHeader title={`Overview · ${DOMAIN}`} description="A quick look at traffic and what is left to finish setting up this domain." />
      <ul className="mt-6 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {STATS.map((s) => (
          <li key={s.k} className="card p-4">
            <p className="text-sm text-muted">{s.k}</p>
            <p className="mt-1 text-2xl font-semibold">{s.v}</p>
            <p className="mt-1 text-xs text-muted">{s.d}</p>
          </li>
        ))}
      </ul>
      <section className="card mt-6 max-w-3xl" aria-labelledby="gs-h">
        <div className="card-pad">
          <h2 id="gs-h" className="text-base font-semibold">
            Get started
          </h2>
          <p className="mt-1 text-muted" aria-live="polite">
            {done} of {STEPS.length} steps complete
          </p>
          <div className="mt-3 h-2 overflow-hidden rounded-full bg-active" role="progressbar" aria-label="Setup progress" aria-valuemin={0} aria-valuemax={STEPS.length} aria-valuenow={done}>
            <div className="h-full bg-primary" style={{ width: `${(done / STEPS.length) * 100}%` }} />
          </div>
          <ol className="mt-4 grid gap-1">
            {STEPS.map((s) => (
              <li key={s.t} className="flex min-h-9 items-center gap-3">
                <CircleCheck size={16} aria-hidden="true" className={s.done ? "flex-none text-ok" : "flex-none text-muted"} />
                <span className={s.done ? "text-muted line-through" : ""}>
                  {s.t}
                  <span className="sr-only">{s.done ? " (done)" : " (to do)"}</span>
                </span>
                {s.to && (
                  <Link to={s.to} className="link ml-auto flex-none">
                    Start
                  </Link>
                )}
              </li>
            ))}
          </ol>
        </div>
      </section>
    </div>
  );
}

export function SitesPage() {
  const { sites } = useData();
  return (
    <div>
      <PageHeader
        title="Domains"
        description="Every site connected to this account."
        actions={
          <Link to="/dashboard/sites/new" className="btn btn-primary">
            <Plus size={16} aria-hidden="true" />
            Add a site
          </Link>
        }
      />
      <ul className="mt-6 grid max-w-3xl gap-3">
        {sites.map((s) => (
          <li key={s.id} className="card flex flex-wrap items-center justify-between gap-3 p-4">
            <div className="min-w-0 flex-1 basis-48">
              <p className="break-all font-semibold">{s.name}</p>
              <p className="text-sm text-muted">{s.plan} plan</p>
            </div>
            <span className={s.status === "Active" ? "badge badge-ok" : "badge badge-warn"}>{s.status}</span>
            <Link to="/dashboard/dns" className="btn" aria-label={`Manage ${s.name}`}>
              Manage
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function Placeholder({ slug }: { slug?: string }) {
  const key = slug ?? "";
  const title = PAGE_TITLES[key] ?? (key ? key.replace(/-/g, " ").replace(/^./, (c) => c.toUpperCase()) : "Page");
  return (
    <div>
      <PageHeader title={title} description="This page is outside the scope of the design reference." />
      <div className="card card-pad mt-6 max-w-3xl">
        <p className="text-muted">The prototype focuses on the sidebar, list, form, settings and wizard patterns. Try one of these:</p>
        <ul className="mt-4 grid list-disc gap-1 pl-6">
          <li>
            <Link to="/dashboard/dns" className="link">
              DNS records (list, filters, bulk actions)
            </Link>
          </li>
          <li>
            <Link to="/dashboard/dns/new" className="link">
              Add record (form)
            </Link>
          </li>
          <li>
            <Link to="/dashboard/settings" className="link">
              SSL/TLS (settings page)
            </Link>
          </li>
          <li>
            <Link to="/dashboard/sites/new" className="link">
              Add a site (wizard)
            </Link>
          </li>
        </ul>
      </div>
    </div>
  );
}
