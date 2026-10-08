export type RecordType = 'A' | 'AAAA' | 'CNAME' | 'MX' | 'TXT';
export type Theme = 'system' | 'light' | 'dark';
export type Page = 'overview' | 'navigation' | 'dns' | 'forms' | 'responsive' | 'guidelines' | 'tokens' | 'docs';

export interface DnsRecord {
  id: string;
  type: RecordType;
  name: string;
  content: string;
  proxied: boolean;
  ttl: string;
  priority: string;
  comment: string;
}

export type RecordDraft = Omit<DnsRecord, 'id'>;
export type FieldErrors = Partial<Record<keyof RecordDraft, string>>;

export const DOMAIN = 'example.com';
export const RECORD_TYPES: RecordType[] = ['A', 'AAAA', 'CNAME', 'MX', 'TXT'];
export const EMPTY_RECORD: RecordDraft = { type: 'A', name: '', content: '', proxied: true, ttl: 'auto', priority: '10', comment: '' };
export const SEED_RECORDS: DnsRecord[] = [
  { id: 'demo-1', type: 'A', name: '@', content: '192.0.2.1', proxied: true, ttl: 'auto', priority: '10', comment: '主站入口' },
  { id: 'demo-2', type: 'A', name: 'www', content: '192.0.2.1', proxied: true, ttl: 'auto', priority: '10', comment: '' },
  { id: 'demo-3', type: 'CNAME', name: 'blog', content: 'cname.vercel-dns.com', proxied: false, ttl: 'auto', priority: '10', comment: '博客站点' },
  { id: 'demo-4', type: 'MX', name: '@', content: 'mx1.mail.example.com', proxied: false, ttl: 'auto', priority: '10', comment: '' },
  { id: 'demo-5', type: 'TXT', name: '@', content: 'v=spf1 include:_spf.example.com ~all', proxied: false, ttl: 'auto', priority: '10', comment: '' },
  { id: 'demo-6', type: 'TXT', name: '_dmarc', content: 'v=DMARC1; p=reject;', proxied: false, ttl: 'auto', priority: '10', comment: '' },
];

export const PAGE_INFO: Record<Page, { title: string; subtitle: string; label: string }> = {
  overview: { title: '好的界面，让复杂变简单。', subtitle: '以成熟的控制台交互为起点，构建属于你的产品体验。', label: '设计总览' },
  navigation: { title: '恰到好处的导航，恰如其分的空间。', subtitle: '展开时清晰，收起时克制。让导航跟随意图，而不是打断任务。', label: '侧边栏导航' },
  dns: { title: '交互设计实验室', subtitle: '不止于外观，让每一次操作都有章可循。', label: 'DNS 管理' },
  forms: { title: '让每一次输入，都得到回应。', subtitle: '清晰的分组、及时的校验，以及可以从容继续的草稿。', label: '表单与校验' },
  responsive: { title: '屏幕在变，体验始终从容。', subtitle: '拖动宽度，观察真实重排。在每一种尺寸下，保留清晰的下一步。', label: '响应式布局' },
  guidelines: { title: '设计有依据，协作有共识。', subtitle: '从必须遵循的底线，到值得采用的细节，建立可执行的设计规范。', label: '设计规范' },
  tokens: { title: '一致性，从一个变量开始。', subtitle: '让颜色、间距与动效共享同一套语义，而不是散落的视觉数值。', label: '设计令牌' },
  docs: { title: '从设计参考，到落地实践。', subtitle: '一份清晰的文档地图，连接设计决策、实现方式与交付验收。', label: '交付文档' },
};

export function supportsProxy(type: RecordType) {
  return type === 'A' || type === 'AAAA' || type === 'CNAME';
}

export function validateRecord(record: RecordDraft): FieldErrors {
  const errors: FieldErrors = {};
  const hostname = record.name.trim();
  const labels = hostname.replace(/\.$/, '').split('.');
  const validName = hostname === '@' || labels.every((label, index) =>
    (index === 0 && label === '*') || /^[a-zA-Z0-9_](?:[a-zA-Z0-9_-]{0,61}[a-zA-Z0-9_])?$/.test(label));
  if (!hostname) errors.name = '请输入记录名称，根域名请填写 @。';
  else if (hostname.length > 253 || !validName) {
    errors.name = '请输入有效的主机名，例如 www、_dmarc 或 @。';
  }
  const content = record.content.trim();
  if (!content) errors.content = '请输入记录内容。';
  else if (record.type === 'A' && !/^(\d{1,3}\.){3}\d{1,3}$/.test(content)) errors.content = '请输入有效的 IPv4 地址，例如 192.0.2.1。';
  else if (record.type === 'A' && content.split('.').some(part => Number(part) > 255 || (part.length > 1 && part.startsWith('0')))) errors.content = 'IPv4 每段必须为 0 到 255，且不能有前导零。';
  else if (record.type === 'AAAA') {
    try {
      if (!content.includes(':') || !/^[0-9a-fA-F:.]+$/.test(content)) throw new Error('Invalid IPv6 syntax');
      new URL(`https://[${content}]/`);
    } catch { errors.content = '请输入有效的 IPv6 地址，例如 2001:db8::1。'; }
  } else if ((record.type === 'CNAME' || record.type === 'MX') && (content.length > 253 || !/^(?=.{1,253}\.?$)(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.?$/.test(content))) errors.content = '请输入完整的目标域名，例如 mail.example.com。';
  else if (record.type === 'TXT' && content.length > 2048) errors.content = '演示中的 TXT 内容最多为 2048 个字符。';
  if (record.type === 'MX' && (!/^\d+$/.test(record.priority) || Number(record.priority) > 65535)) errors.priority = '优先级必须为 0 到 65535 的整数。';
  if (!['auto', '60', '300', '3600'].includes(record.ttl)) errors.ttl = '请选择有效的 TTL。';
  if (record.comment.length > 200) errors.comment = '备注最多为 200 个字符。';
  return errors;
}

export function isDnsRecord(value: unknown): value is DnsRecord {
  if (!value || typeof value !== 'object') return false;
  const record = value as DnsRecord;
  return typeof record.id === 'string' && record.id.length > 0 && RECORD_TYPES.includes(record.type) &&
    ['name', 'content', 'ttl', 'priority', 'comment'].every(key => typeof record[key as keyof DnsRecord] === 'string') &&
    typeof record.proxied === 'boolean' && (!record.proxied || (supportsProxy(record.type) && record.ttl === 'auto')) && Object.keys(validateRecord(record)).length === 0;
}

export function recordKey(record: RecordDraft) {
  return `${record.type}|${record.name.trim().toLowerCase()}|${record.content.trim()}`;
}

export function createId() {
  return typeof crypto.randomUUID === 'function' ? crypto.randomUUID() : `record-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

export function downloadFile(filename: string, content: string, type = 'application/json') {
  const url = URL.createObjectURL(new Blob([content], { type }));
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  link.hidden = true;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}