import { ArrowRight, CheckCircle2, Circle, Copy, ExternalLink, Globe, Lock, Network, Ruler, Shield, Zap } from "lucide-react";
import { Badge, Button } from "@/components/ui/primitives";
import { Alert, Card, CardBody, CardHeader, PageHeader, Stat } from "@/components/ui/layout";
import { useToast } from "@/components/ui/overlays";
import { ZONE } from "@/data/records";
import { Link } from "@/lib/router";

const NS = ["ada.ns.example-dns.com", "rob.ns.example-dns.com"];

export function OverviewPage() {
  const { toast } = useToast();
  const copy = (t: string) => {
    navigator.clipboard?.writeText(t);
    toast({ tone: "success", title: "Copied to clipboard", description: t });
  };

  return (
    <>
      <PageHeader
        title={ZONE}
        meta={<Badge tone="warning">Pending nameserver update</Badge>}
        description="This is the mock design reference. The dashboard layout: one primary task above the fold, secondary cards below."
        actions={
          <>
            <Button variant="secondary" icon={<Ruler className="size-4" />} onClick={() => (window.location.hash = "#/lab")}>
              Open Responsive Lab
            </Button>
            <Button variant="primary" icon={<Network className="size-4" />} onClick={() => (window.location.hash = "#/dns/records")}>
              Manage DNS
            </Button>
          </>
        }
      />

      <Alert tone="info" className="mb-6" title="Complete your nameserver setup">
        Replace your registrar's nameservers with the two below. Activation usually takes under an hour, but can take up to 24 hours.
      </Alert>

      {/* primary task card */}
      <div className="grid grid-cols-1 xl:grid-cols-3 gap-4 xl:gap-6 mb-6">
        <Card className="xl:col-span-2">
          <CardHeader title="1. Update your nameservers" description="Log in to your registrar and replace the current nameservers with these." />
          <CardBody className="pt-0">
            <ol className="space-y-2">
              {NS.map((n, i) => (
                <li key={n} className="flex items-center gap-3 p-3 rounded-sm border border-line bg-surface-2/60 min-w-0">
                  <span className="size-6 shrink-0 rounded-full bg-primary-soft text-primary-text text-xs font-semibold flex items-center justify-center">{i + 1}</span>
                  <code className="font-mono text-sm text-fg flex-1 min-w-0 truncate">{n}</code>
                  <Button size="sm" variant="ghost" square aria-label={`Copy ${n}`} onClick={() => copy(n)} icon={<Copy className="size-4" />} />
                </li>
              ))}
            </ol>
            <div className="mt-4 flex flex-wrap gap-2">
              <Button variant="primary" onClick={() => toast({ tone: "info", title: "Checking nameservers…", description: "We will email you when the domain is active." })}>
                Check nameservers now
              </Button>
              <Button variant="link" iconRight={<ExternalLink className="size-3.5" />}>Registrar instructions</Button>
            </div>
          </CardBody>
        </Card>

        <Card>
          <CardHeader title="Setup checklist" />
          <CardBody className="pt-0">
            <ul className="space-y-3 text-base">
              {[
                ["Add DNS records", true, "/dns/records"],
                ["Review SSL/TLS mode", true, "/placeholder/ssl"],
                ["Update nameservers", false, "/"],
                ["Enable security defaults", false, "/placeholder/security"],
              ].map(([label, done, path]) => (
                <li key={label as string}>
                  <Link to={path as string} className="flex items-center gap-3 group">
                    {done ? <CheckCircle2 className="size-5 text-success shrink-0" aria-hidden /> : <Circle className="size-5 text-fg-3 shrink-0" aria-hidden />}
                    <span className={done ? "text-fg-3 line-through flex-1" : "text-fg flex-1"}>{label as string}</span>
                    <ArrowRight className="size-4 text-fg-3 opacity-0 group-hover:opacity-100 transition-opacity" aria-hidden />
                  </Link>
                </li>
              ))}
            </ul>
          </CardBody>
        </Card>
      </div>

      {/* stats */}
      <Card className="mb-6">
        <CardHeader title="Last 24 hours" description="Traffic summary. Values are mocked." actions={<Button size="sm" variant="ghost" iconRight={<ArrowRight className="size-4" />}>Analytics</Button>} />
        <CardBody className="pt-0">
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-x-6 gap-y-5">
            <Stat label="Unique visitors" value="12,480" delta={{ value: "4.2%", up: true }} />
            <Stat label="Total requests" value="1.9M" delta={{ value: "1.1%", up: false }} hint="All HTTP requests served by the edge." />
            <Stat label="Bandwidth" value="86.4 GB" delta={{ value: "7.5%", up: true }} />
            <Stat label="Threats blocked" value="3,201" hint="Requests blocked by WAF and bot rules." />
          </div>
        </CardBody>
      </Card>

      {/* quick actions grid */}
      <h2 className="text-lg font-semibold text-fg mb-3">Quick actions</h2>
      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4">
        {[
          { icon: Network, title: "DNS records", desc: "Table + inline forms, filters, bulk actions.", path: "/dns/records" },
          { icon: Shield, title: "Form patterns", desc: "Long form with sticky outline, wizard, danger zone.", path: "/forms/create" },
          { icon: Lock, title: "Settings page", desc: "Card-per-setting with footer actions.", path: "/settings" },
          { icon: Zap, title: "Design guide", desc: "MUST / SHOULD / MAY / AVOID rules.", path: "/guide/readme" },
        ].map((q) => (
          <Link key={q.title} to={q.path} className="group block focus-visible:outline-2 rounded-md">
            <Card className="h-full p-4 transition-colors group-hover:border-line-strong">
              <q.icon className="size-5 text-primary-text mb-3" aria-hidden />
              <p className="text-base font-medium text-fg flex items-center gap-1">
                {q.title}
                <ArrowRight className="size-4 text-fg-3 group-hover:translate-x-0.5 transition-transform" aria-hidden />
              </p>
              <p className="text-sm text-fg-3 mt-1">{q.desc}</p>
            </Card>
          </Link>
        ))}
      </div>
    </>
  );
}

export function PlaceholderPage({ title }: { title: string }) {
  return (
    <>
      <PageHeader title={title} description="This section is a navigation placeholder in the mock. It exists so the sidebar information architecture feels complete." />
      <Card>
        <CardBody className="py-12 text-center">
          <Globe className="size-8 text-fg-3 mx-auto mb-3" aria-hidden />
          <p className="text-base font-medium text-fg">Nothing to configure here (yet)</p>
          <p className="text-sm text-fg-3 mt-1">Try the DNS records page or the Form Patterns section for complete interactions.</p>
          <div className="mt-4 flex justify-center gap-2">
            <Button onClick={() => (window.location.hash = "#/dns/records")}>DNS records</Button>
            <Button variant="primary" onClick={() => (window.location.hash = "#/forms/create")}>Form patterns</Button>
          </div>
        </CardBody>
      </Card>
    </>
  );
}
