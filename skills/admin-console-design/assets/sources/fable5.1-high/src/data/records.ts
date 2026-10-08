export type RecordType = "A" | "AAAA" | "CNAME" | "MX" | "TXT" | "NS" | "SRV" | "CAA";

export interface DnsRecord {
  id: string;
  type: RecordType;
  name: string;
  content: string;
  proxied: boolean;
  /** 1 = Auto */
  ttl: number;
  priority?: number;
  comment?: string;
  warning?: string;
  updatedAt: string;
}

export const ZONE = "myexample.com";

export const RECORD_TYPES: { value: RecordType; label: string; help: string; contentLabel: string; placeholder: string; proxyable: boolean }[] = [
  { value: "A", label: "A", help: "Maps a hostname to an IPv4 address.", contentLabel: "IPv4 address", placeholder: "192.0.2.1", proxyable: true },
  { value: "AAAA", label: "AAAA", help: "Maps a hostname to an IPv6 address.", contentLabel: "IPv6 address", placeholder: "2001:db8::1", proxyable: true },
  { value: "CNAME", label: "CNAME", help: "Alias one hostname to another.", contentLabel: "Target", placeholder: "example.com", proxyable: true },
  { value: "MX", label: "MX", help: "Mail exchange server for the domain.", contentLabel: "Mail server", placeholder: "mail.example.com", proxyable: false },
  { value: "TXT", label: "TXT", help: "Arbitrary text, used for verification and SPF/DKIM/DMARC.", contentLabel: "Content", placeholder: "v=spf1 -all", proxyable: false },
  { value: "NS", label: "NS", help: "Delegates a subdomain to other nameservers.", contentLabel: "Nameserver", placeholder: "ns1.example.com", proxyable: false },
  { value: "SRV", label: "SRV", help: "Service location record.", contentLabel: "Target", placeholder: "sip.example.com", proxyable: false },
  { value: "CAA", label: "CAA", help: "Which CAs may issue certificates.", contentLabel: "Value", placeholder: "letsencrypt.org", proxyable: false },
];

export const TTL_OPTIONS = [
  { value: "1", label: "Auto" },
  { value: "60", label: "1 min" },
  { value: "120", label: "2 min" },
  { value: "300", label: "5 min" },
  { value: "600", label: "10 min" },
  { value: "900", label: "15 min" },
  { value: "1800", label: "30 min" },
  { value: "3600", label: "1 hr" },
  { value: "7200", label: "2 hr" },
  { value: "18000", label: "5 hr" },
  { value: "43200", label: "12 hr" },
  { value: "86400", label: "1 day" },
];

export function ttlLabel(ttl: number) {
  return TTL_OPTIONS.find((t) => Number(t.value) === ttl)?.label ?? `${ttl}s`;
}

export const INITIAL_RECORDS: DnsRecord[] = [
  { id: "r1", type: "A", name: ZONE, content: "199.168.103.236", proxied: true, ttl: 1, updatedAt: "2026-02-11", warning: "This record exposes the origin IP because the zone is still pending activation." },
  { id: "r2", type: "A", name: `www.${ZONE}`, content: "199.168.103.236", proxied: true, ttl: 1, updatedAt: "2026-02-11", warning: "This record exposes the origin IP because the zone is still pending activation." },
  { id: "r3", type: "MX", name: `*.${ZONE}`, content: "mailx.gridhost.com", proxied: false, ttl: 1, priority: 10, updatedAt: "2026-01-29" },
  { id: "r4", type: "MX", name: ZONE, content: "mailx.gridhost.com", proxied: false, ttl: 1, priority: 10, updatedAt: "2026-01-29" },
  { id: "r5", type: "TXT", name: `_dmarc.${ZONE}`, content: '"v=DMARC1; p=reject; adkim=s; aspf=s"', proxied: false, ttl: 1, updatedAt: "2026-01-20", comment: "Strict DMARC policy" },
  { id: "r6", type: "TXT", name: ZONE, content: '"d42fa940ba58b8b19485b4deb8b9a7facee31ed6"', proxied: false, ttl: 1, updatedAt: "2026-01-20" },
  { id: "r7", type: "TXT", name: ZONE, content: '"v=spf1 -all"', proxied: false, ttl: 1, updatedAt: "2026-01-20" },
  { id: "r8", type: "TXT", name: ZONE, content: '"This domain does not send E-mail."', proxied: false, ttl: 1, updatedAt: "2026-01-20" },
];

/* ---------------------------------------------------------------- validation */
const IPV4 = /^(25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)(\.(25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)){3}$/;
const IPV6 = /^(([0-9a-f]{1,4}:){7}[0-9a-f]{1,4}|(([0-9a-f]{1,4}:){1,7}|:):(([0-9a-f]{1,4}:){0,6}[0-9a-f]{1,4})?)$/i;
const HOST = /^(?=.{1,253}$)(\*\.)?([a-z0-9_]([a-z0-9-_]{0,61}[a-z0-9_])?\.)*[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.?$/i;

export interface RecordFormValues {
  type: RecordType;
  name: string;
  content: string;
  proxied: boolean;
  ttl: string;
  priority: string;
  comment: string;
}

export type FormErrors = Partial<Record<keyof RecordFormValues, string>>;

export function validateRecord(v: RecordFormValues, existing: DnsRecord[], editingId?: string): FormErrors {
  const e: FormErrors = {};
  const name = v.name.trim();
  const content = v.content.trim();

  if (!name) e.name = "Name is required. Use @ for the root domain.";
  else if (name !== "@" && !HOST.test(name)) e.name = "Enter a valid hostname (letters, digits, hyphens; labels ≤ 63 chars).";

  if (!content) e.content = `${RECORD_TYPES.find((t) => t.value === v.type)?.contentLabel ?? "Content"} is required.`;
  else if (v.type === "A" && !IPV4.test(content)) e.content = "Enter a valid IPv4 address, e.g. 192.0.2.1.";
  else if (v.type === "AAAA" && !IPV6.test(content)) e.content = "Enter a valid IPv6 address, e.g. 2001:db8::1.";
  else if ((v.type === "CNAME" || v.type === "MX" || v.type === "NS") && !HOST.test(content)) e.content = "Enter a valid target hostname.";
  else if (v.type === "TXT" && content.length > 2048) e.content = "TXT content must be 2048 characters or fewer.";

  if (v.type === "MX" || v.type === "SRV") {
    const p = Number(v.priority);
    if (v.priority === "" || !Number.isInteger(p) || p < 0 || p > 65535) e.priority = "Priority must be an integer between 0 and 65535.";
  }

  if (v.comment.length > 100) e.comment = "Comment must be 100 characters or fewer.";

  // CNAME conflict: a CNAME cannot coexist with other records on the same name
  const fqdn = toFqdn(name);
  if (!e.name && !e.content) {
    const same = existing.filter((r) => r.id !== editingId && r.name.toLowerCase() === fqdn.toLowerCase());
    if (v.type === "CNAME" && same.length) e.name = `A CNAME cannot be added: ${same.length} other record(s) already exist for ${fqdn}.`;
    else if (v.type !== "CNAME" && same.some((r) => r.type === "CNAME")) e.name = `A CNAME record already exists for ${fqdn}. Delete it first.`;
    else if (same.some((r) => r.type === v.type && r.content === content)) e.content = "An identical record already exists.";
  }
  return e;
}

export function toFqdn(name: string) {
  const n = name.trim().replace(/\.$/, "");
  if (!n || n === "@") return ZONE;
  if (n.toLowerCase() === ZONE || n.toLowerCase().endsWith("." + ZONE)) return n;
  return `${n}.${ZONE}`;
}

export function displayName(fqdn: string) {
  // split into (sub, zone) for muted zone suffix rendering
  if (fqdn === ZONE) return { sub: "", zone: ZONE };
  if (fqdn.endsWith("." + ZONE)) return { sub: fqdn.slice(0, -ZONE.length), zone: ZONE };
  return { sub: fqdn, zone: "" };
}
