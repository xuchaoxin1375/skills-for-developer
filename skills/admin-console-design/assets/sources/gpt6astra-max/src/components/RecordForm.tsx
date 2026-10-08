import { useEffect, useId, useRef, useState, type FormEvent } from 'react';
import { AlertCircle, ArrowLeft, Check, CheckCircle2, Cloud, Info, LoaderCircle, RotateCcw, Save, Trash2 } from 'lucide-react';
import { EMPTY_RECORD, RECORD_TYPES, supportsProxy, validateRecord, type DnsRecord, type FieldErrors, type RecordDraft, type RecordType } from '../lib/data';
import { useStoredState } from '../lib/hooks';

interface RecordFormProps {
  record?: DnsRecord;
  onSave: (draft: RecordDraft, id?: string) => Promise<void>;
  onCancel?: () => void;
  onDelete?: () => void;
  inline?: boolean;
  simulateFailure?: boolean;
}

export function RecordForm({ record, onSave, onCancel, onDelete, inline = false, simulateFailure = false }: RecordFormProps) {
  const [storedDraft, setStoredDraft] = useStoredState<RecordDraft>('edgelab.draft', EMPTY_RECORD, value => {
    if (!value || typeof value !== 'object') return false;
    const draft = value as RecordDraft;
    return RECORD_TYPES.includes(draft.type) && typeof draft.proxied === 'boolean' && ['name', 'content', 'ttl', 'priority', 'comment'].every(key => typeof draft[key as keyof RecordDraft] === 'string') && ['auto', '60', '300', '3600'].includes(draft.ttl);
  });
  const [draft, setDraft] = useState<RecordDraft>(record || storedDraft);
  const [errors, setErrors] = useState<FieldErrors>({});
  const [serverError, setServerError] = useState('');
  const [saving, setSaving] = useState(false);
  const [success, setSuccess] = useState(false);
  const [touched, setTouched] = useState<Partial<Record<keyof RecordDraft, boolean>>>({});
  const form = useRef<HTMLFormElement>(null);
  const alive = useRef(true);
  const saveTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const prefix = useId();
  const proxyAvailable = supportsProxy(draft.type);

  useEffect(() => { alive.current = true; return () => { alive.current = false; clearTimeout(saveTimer.current); }; }, []);
  useEffect(() => { if (!record) setStoredDraft(draft); }, [draft, record, setStoredDraft]);

  function update<K extends keyof RecordDraft>(key: K, value: RecordDraft[K]) {
    const next = { ...draft, [key]: value };
    if (key === 'type' && !supportsProxy(value as RecordType)) next.proxied = false;
    if (key === 'proxied' && value) next.ttl = 'auto';
    setDraft(next);
    setSuccess(false);
    setServerError('');
    if (touched[key]) setErrors(previous => ({ ...previous, [key]: validateRecord(next)[key] }));
    if (key === 'type') setErrors(previous => ({ ...previous, content: touched.content ? validateRecord(next).content : undefined, priority: undefined }));
  }

  function validateField(key: keyof RecordDraft) {
    setTouched(previous => ({ ...previous, [key]: true }));
    setErrors(previous => ({ ...previous, [key]: validateRecord(draft)[key] }));
  }

  function describedBy(key: keyof RecordDraft) { return `${prefix}-${key}-help${errors[key] ? ` ${prefix}-${key}-error` : ''}`; }
  function fieldError(key: keyof RecordDraft) { return errors[key] ? <p className="field-error" id={`${prefix}-${key}-error`}><AlertCircle size={13} />{errors[key]}</p> : null; }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (saving) return;
    const nextErrors = validateRecord(draft);
    setErrors(nextErrors);
    setTouched({ name: true, content: true, priority: true, ttl: true, comment: true });
    setServerError('');
    if (Object.keys(nextErrors).length > 0) {
      const first = Object.keys(nextErrors)[0];
      requestAnimationFrame(() => form.current?.querySelector<HTMLElement>(`[name="${first}"]`)?.focus());
      return;
    }
    setSaving(true);
    try {
      await new Promise<void>(resolve => { saveTimer.current = setTimeout(resolve, 550); });
      if (!alive.current) return;
      if (simulateFailure) throw new Error('模拟保存失败。已保留所有输入，请关闭“模拟保存失败”后重试。');
      await onSave({ ...draft, name: draft.name.trim(), content: draft.content.trim(), proxied: proxyAvailable && draft.proxied }, record?.id);
      if (!alive.current) return;
      if (!record) { setDraft({ ...EMPTY_RECORD }); setStoredDraft({ ...EMPTY_RECORD }); }
      setErrors({});
      setTouched({});
      setSuccess(true);
      if (inline) requestAnimationFrame(() => form.current?.querySelector<HTMLElement>('.success-banner')?.focus());
    } catch (error) {
      if (alive.current) {
        setServerError(error instanceof Error ? error.message : '保存失败，请重试。');
        requestAnimationFrame(() => form.current?.querySelector<HTMLElement>('.form-server-error')?.focus());
      }
    } finally { if (alive.current) setSaving(false); }
  }

  const contentLabel = { A: 'IPv4 地址', AAAA: 'IPv6 地址', CNAME: '目标域名', MX: '邮件服务器', TXT: '文本内容' }[draft.type];
  const placeholder = { A: '例如 192.0.2.1', AAAA: '例如 2001:db8::1', CNAME: '例如 target.example.com', MX: '例如 mail.example.com', TXT: '例如 v=spf1 ~all' }[draft.type];

  return <form className={`record-form ${inline ? 'inline-record-form' : ''}`} noValidate onSubmit={submit} ref={form}>
    <div className="form-scroll">
      {inline && <div className="inline-form-heading"><button className="text-button" type="button" onClick={onCancel}><ArrowLeft size={15} />返回记录</button><h2>添加 DNS 记录</h2><p>配置一条记录，将你的域名指向正确的目标。</p></div>}
      {success && inline && <div className="success-banner" role="status" tabIndex={-1}><CheckCircle2 size={18} /><div><strong>记录已添加</strong><p>演示记录已保存，可以继续添加下一条。</p></div></div>}
      {serverError && <div className="form-server-error" role="alert" tabIndex={-1}><AlertCircle size={18} /><span>{serverError}</span></div>}
      {Object.values(errors).some(Boolean) && <p className="validation-summary" role="alert">请检查以下标记的字段，已填写的内容不会丢失。</p>}
      <p className="required-note">标有 <span className="required">*</span> 的字段为必填项。</p>
      <fieldset className="form-section">
        <legend><span className="section-number">01</span>基本信息</legend>
        <p className="section-description">告诉我们，这条记录指向哪里。</p>
        <div className="form-pair">
          <div className="form-field type-field"><label htmlFor={`${prefix}-type`}>记录类型 <span className="required">*</span></label><select id={`${prefix}-type`} name="type" aria-required="true" value={draft.type} onChange={event => update('type', event.target.value as RecordType)}>{RECORD_TYPES.map(type => <option key={type}>{type}</option>)}</select><p className="field-help">选择解析协议。</p></div>
          <div className="form-field"><label htmlFor={`${prefix}-name`}>名称 <span className="required">*</span></label><input id={`${prefix}-name`} name="name" value={draft.name} data-autofocus={!inline || undefined} onChange={event => update('name', event.target.value)} onBlur={() => validateField('name')} placeholder="例如 www 或 @" autoComplete="off" spellCheck={false} aria-required="true" aria-invalid={!!errors.name} aria-describedby={describedBy('name')} maxLength={254} /><p className="field-help" id={`${prefix}-name-help`}>使用 <code>@</code> 表示根域名。</p>{fieldError('name')}</div>
        </div>
        <div className="form-field"><label htmlFor={`${prefix}-content`}>{contentLabel} <span className="required">*</span></label>{draft.type === 'TXT' ? <textarea id={`${prefix}-content`} name="content" value={draft.content} onChange={event => update('content', event.target.value)} onBlur={() => validateField('content')} placeholder={placeholder} rows={3} aria-required="true" aria-invalid={!!errors.content} aria-describedby={describedBy('content')} /> : <input id={`${prefix}-content`} name="content" value={draft.content} onChange={event => update('content', event.target.value)} onBlur={() => validateField('content')} placeholder={placeholder} autoComplete="off" spellCheck={false} aria-required="true" aria-invalid={!!errors.content} aria-describedby={describedBy('content')} />}<p className="field-help" id={`${prefix}-content-help`}>{draft.type === 'TXT' ? '请输入原始文本，不需要添加外层引号。' : '填写完整地址，不包含 http:// 或 https://。'}</p>{fieldError('content')}</div>
        {draft.type === 'MX' && <div className="form-field"><label htmlFor={`${prefix}-priority`}>优先级 <span className="required">*</span></label><input id={`${prefix}-priority`} name="priority" inputMode="numeric" value={draft.priority} onChange={event => update('priority', event.target.value)} onBlur={() => validateField('priority')} aria-invalid={!!errors.priority} aria-describedby={describedBy('priority')} /><p className="field-help" id={`${prefix}-priority-help`}>数值越小，优先级越高。允许 0 到 65535。</p>{fieldError('priority')}</div>}
      </fieldset>
      <fieldset className="form-section">
        <legend><span className="section-number">02</span>解析设置</legend>
        {proxyAvailable && <div className="proxy-setting"><div><span className="proxy-label" id={`${prefix}-proxy-label`}><Cloud size={17} className={draft.proxied ? 'cloud-orange' : ''} />代理状态</span><p className="field-help" id={`${prefix}-proxy-help`}>通过边缘网络代理流量，隐藏源站 IP。</p></div><button type="button" role="switch" aria-checked={draft.proxied} aria-labelledby={`${prefix}-proxy-label`} aria-describedby={`${prefix}-proxy-help`} className={`switch ${draft.proxied ? 'on' : ''}`} onClick={() => update('proxied', !draft.proxied)}><span /></button></div>}
        {!proxyAvailable && <p className="form-info"><Info size={15} />{draft.type} 记录仅支持 DNS 解析，不经过代理。</p>}
        <div className="form-field"><label htmlFor={`${prefix}-ttl`}>TTL <span className="optional">生存时间</span></label><select id={`${prefix}-ttl`} name="ttl" value={draft.proxied && proxyAvailable ? 'auto' : draft.ttl} disabled={draft.proxied && proxyAvailable} onChange={event => update('ttl', event.target.value)} aria-describedby={`${prefix}-ttl-help`}><option value="auto">自动</option><option value="60">1 分钟</option><option value="300">5 分钟</option><option value="3600">1 小时</option></select><p className="field-help" id={`${prefix}-ttl-help`}>{draft.proxied && proxyAvailable ? '已代理的记录由系统自动管理 TTL。' : 'DNS 解析器缓存这条记录的时间。'}</p></div>
        <div className="form-field"><label htmlFor={`${prefix}-comment`}>备注 <span className="optional">可选</span></label><input id={`${prefix}-comment`} name="comment" value={draft.comment} onChange={event => update('comment', event.target.value)} onBlur={() => validateField('comment')} placeholder="为这条记录添加说明" maxLength={201} aria-invalid={!!errors.comment} aria-describedby={describedBy('comment')} /><p className="field-help" id={`${prefix}-comment-help`}>仅供内部参考，不会公开在 DNS 中。{draft.comment.length}/200</p>{fieldError('comment')}</div>
      </fieldset>
      <p className="form-local-note"><Info size={14} />这是交互演示，不会修改任何真实 DNS 记录。</p>
    </div>
    <footer className="form-footer">
      {record && onDelete ? <button type="button" className="text-button danger-text" onClick={onDelete}><Trash2 size={15} />删除记录</button> : <span className="draft-status"><Check size={13} />草稿自动保留</span>}
      <div className="form-footer-actions">{onCancel && <button className="button" type="button" onClick={onCancel}>取消</button>}<button className="button primary" type="submit" disabled={saving} aria-busy={saving}>{saving ? <LoaderCircle size={15} className="spin" /> : serverError ? <RotateCcw size={15} /> : <Save size={15} />}{saving ? '正在保存...' : serverError ? '重新保存' : record ? '保存更改' : '保存记录'}</button></div>
    </footer>
  </form>;
}