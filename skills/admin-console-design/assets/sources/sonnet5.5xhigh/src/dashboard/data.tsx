import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";

export type RecordType = "A" | "AAAA" | "CNAME" | "MX" | "TXT" | "NS";

export interface DnsRecord {
  id: string;
  type: RecordType;
  /** 相对名称：@ 表示根域名 */
  name: string;
  content: string;
  proxied: boolean;
  /** 0 = Auto */
  ttl: number;
  comment: string;
  priority?: number;
  pending?: boolean;
  /** 最近修改时间（毫秒时间戳） */
  modified?: number;
}

export interface Site {
  id: string;
  name: string;
  plan: string;
  status: "Active" | "Pending";
}

export const DOMAIN = "myexample.com";

export const TTL_OPTIONS: { value: number; label: string }[] = [
  { value: 0, label: "Auto" },
  { value: 60, label: "1 min" },
  { value: 120, label: "2 min" },
  { value: 300, label: "5 min" },
  { value: 600, label: "10 min" },
  { value: 900, label: "15 min" },
  { value: 1800, label: "30 min" },
  { value: 3600, label: "1 hr" },
  { value: 7200, label: "2 hr" },
  { value: 18000, label: "5 hr" },
  { value: 43200, label: "12 hr" },
  { value: 86400, label: "1 day" },
];

export const ttlLabel = (ttl: number) => TTL_OPTIONS.find((o) => o.value === ttl)?.label ?? `${ttl}s`;
export const fqdn = (name: string) => (name === "@" ? DOMAIN : `${name}.${DOMAIN}`);

const day = (m: number, d: number) => Date.UTC(2026, m - 1, d, 9, 30);

const SEED: DnsRecord[] = [
  { id: "r1", type: "A", name: "@", content: "199.168.103.236", proxied: true, ttl: 0, comment: "", pending: true, modified: day(1, 14) },
  { id: "r2", type: "A", name: "www", content: "199.168.103.236", proxied: true, ttl: 0, comment: "Marketing site", pending: true, modified: day(1, 14) },
  { id: "r3", type: "MX", name: "*", content: "mailx.gridhost.com", proxied: false, ttl: 0, comment: "", priority: 10, modified: day(1, 9) },
  { id: "r4", type: "MX", name: "@", content: "mailx.gridhost.com", proxied: false, ttl: 0, comment: "", priority: 10, modified: day(1, 9) },
  { id: "r5", type: "TXT", name: "_dmarc", content: '"v=DMARC1; p=reject; adkim=s; aspf=s"', proxied: false, ttl: 0, comment: "", modified: day(12, 2) },
  { id: "r6", type: "TXT", name: "@", content: '"d42fa940ba58b8b19485b4deb8b9a7facee31ed6"', proxied: false, ttl: 0, comment: "Domain verification", modified: day(12, 2) },
  { id: "r7", type: "TXT", name: "@", content: '"v=spf1 -all"', proxied: false, ttl: 0, comment: "", modified: day(12, 2) },
  { id: "r8", type: "TXT", name: "@", content: '"This domain does not send E-mail."', proxied: false, ttl: 0, comment: "", modified: day(12, 2) },
  { id: "r9", type: "CNAME", name: "blog", content: "hosting.example.net", proxied: true, ttl: 0, comment: "Blog on managed hosting", modified: day(2, 3) },
  { id: "r10", type: "CNAME", name: "docs", content: "docs-edge.example.net", proxied: true, ttl: 0, comment: "Product documentation", modified: day(2, 5) },
  { id: "r11", type: "A", name: "api", content: "203.0.113.24", proxied: true, ttl: 0, comment: "Public API", modified: day(2, 11) },
  { id: "r12", type: "AAAA", name: "api", content: "2001:db8::24", proxied: true, ttl: 0, comment: "Public API (IPv6)", modified: day(2, 11) },
  { id: "r13", type: "TXT", name: "_acme-challenge", content: '"b3f1c2d9e07a4a6c9f1d3b5e7a9c1e3f"', proxied: false, ttl: 120, comment: "Temporary — remove after issuance", modified: day(2, 18) },
  { id: "r14", type: "NS", name: "lab", content: "ns1.lab-dns.net", proxied: false, ttl: 3600, comment: "Delegated to the lab team", modified: day(3, 1) },
];

const SITES: Site[] = [
  { id: "s1", name: "myexample.com", plan: "Free", status: "Pending" },
  { id: "s2", name: "goodpayway.shop", plan: "Free", status: "Active" },
  { id: "s3", name: "goodhjw.top", plan: "Pro", status: "Active" },
];

export interface RemovedItem {
  rec: DnsRecord;
  index: number;
}

interface Store {
  records: DnsRecord[];
  sites: Site[];
  addRecord: (r: Omit<DnsRecord, "id">) => string;
  updateRecord: (id: string, r: Omit<DnsRecord, "id">) => void;
  removeRecords: (ids: string[]) => RemovedItem[];
  restoreRecords: (items: RemovedItem[]) => void;
  importRecords: (rs: Omit<DnsRecord, "id">[]) => void;
  /** 批量更新，返回更新前的快照，可用 restoreSnapshots 撤销 */
  bulkUpdate: (ids: string[], patch: (r: DnsRecord) => Partial<DnsRecord>) => DnsRecord[];
  restoreSnapshots: (prev: DnsRecord[]) => void;
  addSite: (name: string, plan: string) => void;
}

const Ctx = createContext<Store | null>(null);

export function useData(): Store {
  const v = useContext(Ctx);
  if (!v) throw new Error("DataProvider missing");
  return v;
}

let seq = 100;

export function DataProvider({ children }: { children: ReactNode }) {
  const [records, setRecords] = useState<DnsRecord[]>(SEED);
  const [sites, setSites] = useState<Site[]>(SITES);

  const addRecord = useCallback((r: Omit<DnsRecord, "id">) => {
    const id = `r${++seq}`;
    setRecords((l) => [...l, { ...r, id, modified: Date.now() }]);
    return id;
  }, []);
  const updateRecord = useCallback((id: string, r: Omit<DnsRecord, "id">) => {
    setRecords((l) => l.map((x) => (x.id === id ? { ...r, id, modified: Date.now() } : x)));
  }, []);
  const removeRecords = useCallback(
    (ids: string[]) => {
      const removed: RemovedItem[] = [];
      records.forEach((rec, index) => ids.includes(rec.id) && removed.push({ rec, index }));
      setRecords((l) => l.filter((x) => !ids.includes(x.id)));
      return removed;
    },
    [records],
  );
  const restoreRecords = useCallback((items: RemovedItem[]) => {
    setRecords((l) => {
      const next = [...l];
      [...items].sort((a, b) => a.index - b.index).forEach(({ rec, index }) => next.splice(Math.min(index, next.length), 0, rec));
      return next;
    });
  }, []);
  const importRecords = useCallback((rs: Omit<DnsRecord, "id">[]) => {
    setRecords((l) => [...l, ...rs.map((r) => ({ ...r, id: `r${++seq}`, modified: Date.now() }))]);
  }, []);
  const bulkUpdate = useCallback(
    (ids: string[], patch: (r: DnsRecord) => Partial<DnsRecord>) => {
      const prev = records.filter((r) => ids.includes(r.id));
      const now = Date.now();
      setRecords((l) => l.map((r) => (ids.includes(r.id) ? { ...r, ...patch(r), modified: now } : r)));
      return prev;
    },
    [records],
  );
  const restoreSnapshots = useCallback((prev: DnsRecord[]) => {
    setRecords((l) => l.map((r) => prev.find((p) => p.id === r.id) ?? r));
  }, []);
  const addSite = useCallback((name: string, plan: string) => {
    setSites((l) => [{ id: `s${++seq}`, name, plan, status: "Pending" }, ...l]);
  }, []);

  const value = useMemo(
    () => ({ records, sites, addRecord, updateRecord, removeRecords, restoreRecords, importRecords, bulkUpdate, restoreSnapshots, addSite }),
    [records, sites, addRecord, updateRecord, removeRecords, restoreRecords, importRecords, bulkUpdate, restoreSnapshots, addSite],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}
