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

function emit(tag, msg) {
  process.stderr.write(`htmlmini:${tag ? ` [${tag}]` : ''} ${msg}\n`);
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
