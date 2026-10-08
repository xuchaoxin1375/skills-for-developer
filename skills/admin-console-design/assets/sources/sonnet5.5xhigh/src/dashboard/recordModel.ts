import { DOMAIN, fqdn, type DnsRecord, type RecordType } from "./data";

/**
 * DNS 记录的表单模型与校验规则（纯函数，无 UI 依赖）。
 * 整页表单（RecordForm）与行内 / 弹窗编辑器（RecordEditor）共用同一套规则，保证两处行为一致。
 */

const IPV4 = /^(25[0-5]|2[0-4]\d|1?\d?\d)(\.(25[0-5]|2[0-4]\d|1?\d?\d)){3}$/;
const IPV6 = /^(([0-9a-f]{1,4}:){7}[0-9a-f]{1,4}|(([0-9a-f]{1,4}:){0,6}[0-9a-f]{1,4})?::(([0-9a-f]{1,4}:){0,6}[0-9a-f]{1,4})?)$/i;
const LABEL = /^[a-z0-9_]([a-z0-9_-]{0,61}[a-z0-9_])?$/i;

export type FieldKey = "type" | "name" | "content" | "priority" | "comment";
export type FieldErrors = Partial<Record<FieldKey, string>>;
/** 与 DOM 顺序一致：首错聚焦按此顺序查找 */
export const FIELD_ORDER: FieldKey[] = ["type", "name", "content", "priority", "comment"];

export interface Draft {
  type: RecordType;
  name: string;
  content: string;
  priority: string;
  proxied: boolean;
  ttl: number;
  comment: string;
}

export const TYPE_META: Record<RecordType, { label: string; placeholder: string; tip: string }> = {
  A: { label: "IPv4 address", placeholder: "192.0.2.1", tip: "Points a name to an IPv4 address." },
  AAAA: { label: "IPv6 address", placeholder: "2001:db8::1", tip: "Points a name to an IPv6 address." },
  CNAME: { label: "Target", placeholder: "target.example.net", tip: "Aliases one name to another. A CNAME cannot share a name with other records." },
  MX: { label: "Mail server", placeholder: "mail.example.net", tip: "Routes email. Lower priority numbers are tried first." },
  TXT: { label: "Content", placeholder: "v=spf1 include:_spf.example.net ~all", tip: "Free-form text, commonly used for SPF, DKIM and ownership verification." },
  NS: { label: "Name server", placeholder: "ns1.example.net", tip: "Delegates a subdomain to other name servers." },
};

export const PROXYABLE: RecordType[] = ["A", "AAAA", "CNAME"];

export const emptyDraft = (): Draft => ({ type: "A", name: "", content: "", priority: "10", proxied: false, ttl: 0, comment: "" });

export const draftFromRecord = (r: DnsRecord): Draft => ({
  type: r.type,
  name: r.name,
  content: r.content,
  priority: String(r.priority ?? 10),
  proxied: r.proxied,
  ttl: r.ttl,
  comment: r.comment,
});

export function draftToRecord(f: Draft, base?: Pick<DnsRecord, "pending">): Omit<DnsRecord, "id"> {
  const proxied = PROXYABLE.includes(f.type) && f.proxied;
  return {
    type: f.type,
    name: normalizeName(f.name),
    content: f.content.trim(),
    proxied,
    ttl: proxied ? 0 : f.ttl,
    comment: f.comment.trim(),
    priority: f.type === "MX" ? Number(f.priority) : undefined,
    pending: base?.pending,
  };
}

/** 粘贴完整主机名（www.myexample.com）时自动缩写为相对名称 */
export const normalizeName = (v: string) => {
  const s = v.trim().toLowerCase();
  if (s === DOMAIN) return "@";
  return s.endsWith(`.${DOMAIN}`) ? s.slice(0, -(DOMAIN.length + 1)) : s;
};

function validName(v: string): string | undefined {
  const s = normalizeName(v);
  if (!s) return "Enter a name. Use @ for the root domain.";
  if (s === "@") return;
  if (s.length > 253) return "Name is too long (max 253 characters).";
  for (const l of s.split(".")) {
    if (l === "*") continue;
    if (!LABEL.test(l)) return `“${l}” is not a valid label. Use letters, numbers, hyphens or underscores (max 63 characters each).`;
  }
}

function validContent(type: RecordType, v: string): string | undefined {
  const s = v.trim();
  if (!s) return `Enter ${/^[AEIOU]/i.test(TYPE_META[type].label) ? "an" : "a"} ${TYPE_META[type].label.toLowerCase()}.`;
  if (type === "A") return IPV4.test(s) ? undefined : "Enter a valid IPv4 address, for example 192.0.2.1.";
  if (type === "AAAA") return IPV6.test(s) ? undefined : "Enter a valid IPv6 address, for example 2001:db8::1.";
  if (type === "TXT") return s.length > 2048 ? "TXT content is limited to 2048 characters." : undefined;
  const host = s.replace(/\.$/, "");
  if (IPV4.test(host)) return `A ${type} record must point to a hostname, not an IP address.`;
  if (!host.includes(".") || !host.split(".").every((l) => LABEL.test(l))) return "Enter a fully qualified hostname, for example target.example.net.";
}

/** 第一 / 第二级校验：纯客户端、纯字段规则 */
export function validateDraft(f: Draft): FieldErrors {
  const e: FieldErrors = {};
  const n = validName(f.name);
  if (n) e.name = n;
  const c = validContent(f.type, f.content);
  if (c) e.content = c;
  if (f.type === "MX") {
    const p = f.priority.trim();
    if (p === "") e.priority = "Enter a priority between 0 and 65535.";
    else if (!/^\d+$/.test(p) || Number(p) > 65535) e.priority = "Priority must be a whole number between 0 and 65535.";
  }
  if (f.comment.length > 100) e.comment = "Comment is limited to 100 characters.";
  return e;
}

const unquote = (s: string) => s.replace(/^"|"$/g, "");

/** 服务端级校验（跨记录约束）：CNAME 独占名称、禁止完全重复；错误同样映射回字段 */
export function findConflicts(records: DnsRecord[], f: Draft, selfId?: string): FieldErrors {
  const name = normalizeName(f.name);
  const others = records.filter((r) => r.id !== selfId && r.name === name);
  const conflict = f.type === "CNAME" ? others[0] : others.find((r) => r.type === "CNAME");
  const dup = others.find((r) => r.type === f.type && unquote(r.content) === unquote(f.content.trim()));
  const e: FieldErrors = {};
  if (conflict) {
    e.name =
      f.type === "CNAME"
        ? `A CNAME record cannot share a name with other records. “${fqdn(name)}” already has a ${conflict.type} record.`
        : `“${fqdn(name)}” already has a CNAME record, which cannot coexist with ${f.type} records.`;
  } else if (dup) e.content = "An identical record already exists.";
  return e;
}
