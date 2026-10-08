import { useState } from "react";
import { Pause, Trash2 } from "lucide-react";
import { Button, Field, Input, Select, Toggle } from "@/components/ui/primitives";
import { Card, CardBody, CardFooter, CardHeader, PageHeader } from "@/components/ui/layout";
import { Dialog, useToast } from "@/components/ui/overlays";
import { ZONE } from "@/data/records";

function SettingCard({
  title,
  description,
  children,
  onSave,
  dirty,
  note,
}: {
  title: string;
  description: string;
  children: React.ReactNode;
  onSave?: () => void;
  dirty?: boolean;
  note?: string;
}) {
  return (
    <Card>
      <CardHeader title={title} description={description} />
      <CardBody className="pt-0">{children}</CardBody>
      {onSave && (
        <CardFooter note={note ?? (dirty ? "You have unsaved changes." : "Saved")}>
          <Button variant="primary" size="sm" onClick={onSave} disabled={!dirty}>
            Save
          </Button>
        </CardFooter>
      )}
    </Card>
  );
}

export function SettingsPage({ section }: { section?: "dns" }) {
  const { toast } = useToast();
  const [dnssec, setDnssec] = useState(false);
  const [cnameFlat, setCnameFlat] = useState("apex");
  const [cnameSaved, setCnameSaved] = useState("apex");
  const [emailObf, setEmailObf] = useState(true);
  const [minTls, setMinTls] = useState("1.2");
  const [minTlsSaved, setMinTlsSaved] = useState("1.2");
  const [confirm, setConfirm] = useState<"pause" | "delete" | null>(null);
  const [typed, setTyped] = useState("");

  const isDns = section === "dns";

  return (
    <>
      <PageHeader
        title={isDns ? "DNS settings" : "Settings"}
        description={isDns ? "Zone-level DNS behaviour. Each card is one decision; save per card." : "Settings page pattern: single column of independent cards, each with its own footer actions. Danger actions live at the very bottom."}
      />

      <div className="space-y-4 sm:space-y-6">
        {!isDns && (
          <SettingCard title="Minimum TLS version" description="Only allow HTTPS connections from visitors that support the selected TLS protocol version or newer." dirty={minTls !== minTlsSaved} onSave={() => { setMinTlsSaved(minTls); toast({ tone: "success", title: "Minimum TLS version saved" }); }}>
            <div className="max-w-xs">
              <Field label="Version" htmlFor="min-tls" hint="TLS 1.2 is recommended for PCI compliance.">
                <Select id="min-tls" value={minTls} onChange={(e) => setMinTls(e.target.value)} options={["1.0", "1.1", "1.2", "1.3"].map((v) => ({ value: v, label: `TLS ${v}` }))} />
              </Field>
            </div>
          </SettingCard>
        )}

        <SettingCard title="DNSSEC" description="Protects against forged DNS answers. Requires adding a DS record at your registrar.">
          <Toggle checked={dnssec} onChange={(v) => { setDnssec(v); toast({ tone: v ? "success" : "info", title: v ? "DNSSEC enabled" : "DNSSEC disabled" }); }} label={dnssec ? "Enabled" : "Disabled"} description="Instant-apply toggle: no Save button needed. Feedback via toast." />
        </SettingCard>

        <SettingCard title="CNAME flattening" description="Return an IP address instead of a CNAME at the zone apex or for all records." dirty={cnameFlat !== cnameSaved} onSave={() => { setCnameSaved(cnameFlat); toast({ tone: "success", title: "CNAME flattening updated" }); }}>
          <div className="max-w-xs">
            <Field label="Flatten" htmlFor="cname-flat">
              <Select id="cname-flat" value={cnameFlat} onChange={(e) => setCnameFlat(e.target.value)} options={[{ value: "apex", label: "CNAME at apex only" }, { value: "all", label: "All CNAME records" }]} />
            </Field>
          </div>
        </SettingCard>

        {!isDns && (
          <SettingCard title="Email address obfuscation" description="Hide email addresses on your pages from bots while keeping them visible to humans.">
            <Toggle checked={emailObf} onChange={setEmailObf} label={emailObf ? "On" : "Off"} />
          </SettingCard>
        )}

        {/* Danger zone – always last, visually separated, never on the first screen */}
        <Card className="border-danger/40">
          <CardHeader title="Advanced actions" description="These actions affect the whole zone and require confirmation." />
          <CardBody className="pt-0 divide-y divide-line">
            <div className="flex flex-col sm:flex-row sm:items-center gap-3 py-3 first:pt-0">
              <div className="flex-1 min-w-0">
                <p className="text-base font-medium text-fg">Pause on this site</p>
                <p className="text-sm text-fg-3">Traffic bypasses the proxy; DNS keeps resolving.</p>
              </div>
              <Button variant="danger-outline" icon={<Pause className="size-4" />} onClick={() => setConfirm("pause")}>Pause</Button>
            </div>
            <div className="flex flex-col sm:flex-row sm:items-center gap-3 py-3 last:pb-0">
              <div className="flex-1 min-w-0">
                <p className="text-base font-medium text-fg">Remove site</p>
                <p className="text-sm text-fg-3">Deletes all records and configuration. Cannot be undone.</p>
              </div>
              <Button variant="danger-outline" icon={<Trash2 className="size-4" />} onClick={() => { setTyped(""); setConfirm("delete"); }}>Remove</Button>
            </div>
          </CardBody>
        </Card>
      </div>

      <Dialog
        open={confirm === "pause"}
        onClose={() => setConfirm(null)}
        size="sm"
        title="Pause this site?"
        description="Visitors will connect directly to your origin. Security and performance features are disabled until resumed."
        footer={
          <>
            <Button onClick={() => setConfirm(null)}>Cancel</Button>
            <Button variant="danger" data-autofocus onClick={() => { setConfirm(null); toast({ tone: "warning", title: "Site paused", action: { label: "Resume", onClick: () => toast({ tone: "success", title: "Site resumed" }) } }); }}>
              Pause site
            </Button>
          </>
        }
      />

      <Dialog
        open={confirm === "delete"}
        onClose={() => setConfirm(null)}
        tone="danger"
        size="sm"
        title={`Remove ${ZONE}?`}
        description="This permanently deletes every DNS record and setting. Type the domain name to confirm."
        footer={
          <>
            <Button onClick={() => setConfirm(null)}>Cancel</Button>
            <Button variant="danger" disabled={typed !== ZONE} onClick={() => { setConfirm(null); toast({ tone: "error", title: "Site removed (mock)", description: "Nothing really happened." }); }}>
              Remove site
            </Button>
          </>
        }
      >
        <Field label={<span>Type <code className="font-mono text-sm bg-surface-2 px-1 rounded-xs">{ZONE}</code> to continue</span>} htmlFor="confirm-zone">
          <Input id="confirm-zone" value={typed} onChange={(e) => setTyped(e.target.value)} autoComplete="off" spellCheck={false} data-autofocus />
        </Field>
      </Dialog>
    </>
  );
}
