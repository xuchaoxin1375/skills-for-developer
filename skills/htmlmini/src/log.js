/**
 * 统一日志出口：所有进度/诊断都从这里出去。
 *
 * 约定
 * - 只写 stderr。stdout 留给载荷，`htmlmini page.html -t | ...` 这类管道不会被日志污染。
 * - 级别 quiet < info < debug：info 是阶段级进度（默认），debug 是 --verbose 细节，
 *   error 不受级别影响，任何级别下错误都可读。
 * - 初始级别取环境变量 HTMLMINI_LOG，CLI 的 --quiet/--verbose 可覆盖（MCP 侧只认环境变量）。
 * - `--log` 另存完整日志（debug 级也写入），文件行始终带时间戳；默认不建文件。
 *   默认目录是系统临时目录的 htmlmini-logs/，只保留最近 20 份与 7 天内的文件。
 *
 * 阶段标签沿用既有 `htmlmini: [render] …` 约定：read / parse / extract / format / write / render。
 * 每行行首带方括号包住的本地时间戳（`[YYYY-MM-DD HH:mm:ss,SSS]`，与 Python logging 的 asctime 同形），
 * 便于对照网络/渲染耗时与多行日志排序；`HTMLMINI_LOG_TIME=0` 可关掉以兼容按行首匹配的旧脚本。
 */

import { appendFileSync, mkdirSync, readdirSync, rmSync, statSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';

const LEVELS = { quiet: 0, info: 1, debug: 2 };
const NAMES = Object.keys(LEVELS);

let level = LEVELS.info;

const envLevel = process.env.HTMLMINI_LOG;
if (envLevel && envLevel in LEVELS) level = LEVELS[envLevel];

/** 文件 sink：null = 不写文件（默认）；字符串 = 正在写的日志路径。 */
let logPath = null;
/** 落盘失败后停写：日志问题不拖垮主流程，也不逐行重试。 */
let fileBroken = false;

const LOG_DIR = join(tmpdir(), 'htmlmini-logs');
const LOG_KEEP = 20;
const LOG_MAX_AGE_MS = 7 * 24 * 60 * 60 * 1000;

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

/** 默认日志文件：系统临时目录 htmlmini-logs/，文件名带时间与 pid，并发运行不互相覆盖。 */
export function defaultLogPath(d = new Date()) {
  const stamp =
    `${d.getFullYear()}${pad(d.getMonth() + 1)}${pad(d.getDate())}-` +
    `${pad(d.getHours())}${pad(d.getMinutes())}${pad(d.getSeconds())}`;
  return join(LOG_DIR, `htmlmini-${stamp}-${process.pid}.log`);
}

/** 默认目录只留最近 LOG_KEEP 份、且不超过 LOG_MAX_AGE_MS；自定义路径不碰同目录其他文件。 */
function pruneLogDir(dir) {
  let names;
  try {
    names = readdirSync(dir);
  } catch {
    return;
  }
  const now = Date.now();
  const files = names
    .filter((name) => /^htmlmini-\d{8}-\d{6}-\d+\.log$/.test(name))
    .map((name) => {
      const path = join(dir, name);
      try {
        return { path, mtime: statSync(path).mtimeMs };
      } catch {
        return null;
      }
    })
    .filter(Boolean)
    .sort((a, b) => b.mtime - a.mtime);
  files.forEach((file, i) => {
    if (file.path === logPath) return;
    if (i < LOG_KEEP && now - file.mtime <= LOG_MAX_AGE_MS) return;
    try {
      rmSync(file.path, { force: true });
    } catch {
      // 清理失败不影响本次日志写入。
    }
  });
}

/**
 * 打开日志文件 sink。target 省略时用默认路径并剪枝；返回实际路径。
 * 创建失败直接抛错，由 CLI 决定提示后继续（日志不可用不该中断提取）。
 */
export function enableLogFile(target) {
  const path = target || defaultLogPath();
  mkdirSync(dirname(path), { recursive: true });
  // 先建文件：剪枝时本次文件已在目录里，按"最近 N 份"保留时不会把它算漏。
  appendFileSync(path, '', 'utf8');
  logPath = path;
  fileBroken = false;
  if (!target) pruneLogDir(LOG_DIR);
  return path;
}

/** 当前日志文件路径；未启用或已写失败时为 null。 */
export function logFilePath() {
  return logPath && !fileBroken ? logPath : null;
}

function format(tag, msg, withTimeStamp) {
  const head = `htmlmini:${tag ? ` [${tag}]` : ''}`;
  // 子进程转发的多行输出逐行加时间戳，避免只有首行带时间、后续行排序困难。
  const lines = String(msg).replace(/\n+$/, '').split('\n');
  return lines
    .map((line, i) => {
      const text = `${i === 0 ? `${head} ${line}` : line}`;
      return withTimeStamp ? `[${timestamp()}] ${text}` : text;
    })
    .join('\n');
}

function writeLogFile(text) {
  if (!logPath || fileBroken) return;
  try {
    appendFileSync(logPath, `${text}\n`, 'utf8');
  } catch {
    fileBroken = true;
  }
}

function emit(tag, msg, levelName) {
  // 文件 sink 记全量（debug 也写），与 stderr 的级别过滤互不影响；文件始终带时间戳。
  if (logPath && !fileBroken) writeLogFile(format(tag, msg, true));
  if (levelName !== 'error' && !enabled(levelName)) return;
  process.stderr.write(`${format(tag, msg, withTime)}\n`);
}

export const log = {
  /** 阶段级进度：默认可见。 */
  info: (tag, msg) => emit(tag, msg, 'info'),
  /** 细节：仅 --verbose / HTMLMINI_LOG=debug；--log 的文件里始终记录。 */
  debug: (tag, msg) => emit(tag, msg, 'debug'),
  /** 错误：不受级别影响（--quiet 下也要能看见失败原因）。 */
  error: (msg) => emit(null, msg, 'error'),
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
