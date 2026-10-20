/**
 * 统一日志出口：所有进度/诊断都从这里出去。
 *
 * 约定
 * - 只写 stderr。stdout 留给载荷，`htmlmini page.html -t | ...` 这类管道不会被日志污染。
 * - 级别 quiet < info < debug：info 是阶段级进度（默认），debug 是 --verbose 细节，
 *   error 不受级别影响，任何级别下错误都可读。
 * - 初始级别取环境变量 HTMLMINI_LOG，CLI 的 --quiet/--verbose 可覆盖（MCP 侧只认环境变量）。
 *
 * 阶段标签沿用既有 `htmlmini: [render] …` 约定：read / parse / extract / format / write / render。
 * 每行行首带方括号包住的本地时间戳（`[YYYY-MM-DD HH:mm:ss,SSS]`，与 Python logging 的 asctime 同形），
 * 便于对照网络/渲染耗时与多行日志排序；`HTMLMINI_LOG_TIME=0` 可关掉以兼容按行首匹配的旧脚本。
 */

const LEVELS = { quiet: 0, info: 1, debug: 2 };
const NAMES = Object.keys(LEVELS);

let level = LEVELS.info;

const envLevel = process.env.HTMLMINI_LOG;
if (envLevel && envLevel in LEVELS) level = LEVELS[envLevel];

/** 设置日志级别。非法级别抛错（由调用方决定是退出还是忽略）。 */
export function setLogLevel(name) {
  if (!(name in LEVELS)) {
    throw new Error(`unknown log level "${name}"（可选: ${NAMES.join(', ')}）`);
  }
  level = LEVELS[name];
}

export function logLevel() {
  return NAMES.find((n) => LEVELS[n] === level) ?? 'info';
}

const enabled = (n) => level >= LEVELS[n];

// 与 Python logging 的 asctime 同形：本地时间 `[2026-10-20 16:21:40,123]`。
// 时间戳按写入时刻取，不用进程启动时间——日志的用途就是量各阶段相隔多久。
const withTime = process.env.HTMLMINI_LOG_TIME !== '0';

const pad = (n, width = 2) => String(n).padStart(width, '0');

export function timestamp(d = new Date()) {
  return (
    `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ` +
    `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())},` +
    `${pad(d.getMilliseconds(), 3)}`
  );
}

function emit(tag, msg) {
  const head = `htmlmini:${tag ? ` [${tag}]` : ''}`;
  // 子进程转发的多行输出逐行加时间戳，避免只有首行带时间、后续行排序困难。
  const lines = String(msg).replace(/\n+$/, '').split('\n');
  const body = lines
    .map((line, i) => {
      const text = `${i === 0 ? `${head} ${line}` : line}`;
      return withTime ? `[${timestamp()}] ${text}` : text;
    })
    .join('\n');
  process.stderr.write(`${body}\n`);
}

export const log = {
  /** 阶段级进度：默认可见。 */
  info: (tag, msg) => {
    if (enabled('info')) emit(tag, msg);
  },
  /** 细节：仅 --verbose / HTMLMINI_LOG=debug。 */
  debug: (tag, msg) => {
    if (enabled('debug')) emit(tag, msg);
  },
  /** 错误：不受级别影响（--quiet 下也要能看见失败原因）。 */
  error: (msg) => emit(null, msg),
};

/** 字节数人类可读：512 B / 24.1 KB / 1.25 MB。 */
export function fmtBytes(n) {
  if (!Number.isFinite(n)) return '?';
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 / 1024).toFixed(2)} MB`;
}

/** 耗时人类可读：820ms / 2.84s。 */
export function fmtMs(ms) {
  return ms < 1000 ? `${Math.round(ms)}ms` : `${(ms / 1000).toFixed(2)}s`;
}

/**
 * 状态码着色：2xx 绿、3xx 黄、4xx 红、5xx 洋红、未知暗色。
 * 只在 stderr 是终端且未设 NO_COLOR 时生效，重定向到文件/管道时保持纯文本。
 */
export function paintStatus(text, status) {
  if (!process.stderr.isTTY || process.env.NO_COLOR) return text;
  const code = !Number.isFinite(status)
    ? '2'
    : status < 300
      ? '32'
      : status < 400
        ? '33'
        : status < 500
          ? '31'
          : '35';
  return `\x1b[${code}m${text}\x1b[0m`;
}
