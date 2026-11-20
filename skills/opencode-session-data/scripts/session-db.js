'use strict';

/**
 * session-search / session-prune 共用的只读数据库入口。
 *
 * - 默认库路径 `~/.local/share/opencode/opencode.db`，可用 `--db` 或 `OPENCODE_DB` 覆盖；
 * - 默认路径不存在时询问 `opencode debug paths db`，兼容 beta/dev 渠道；
 * - 只读打开，不写库、不加锁。
 */
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { spawnSync } = require('node:child_process');

// node:sqlite 仍带实验特性警告；先拦住它，避免污染命令输出。
const originalEmitWarning = process.emitWarning;
process.emitWarning = function emitWarning(warning, ...args) {
  const type = typeof warning === 'object' ? warning.name : args[0];
  const message = typeof warning === 'object' ? String(warning.message || '') : String(warning);
  if (String(type).includes('ExperimentalWarning') && /SQLite/i.test(message)) return;
  return originalEmitWarning.call(process, warning, ...args);
};

let DatabaseSync;
try {
  ({ DatabaseSync } = require('node:sqlite'));
} catch {
  throw new Error('需要 Node.js 22.13 及以上版本（node:sqlite）。当前版本：' + process.version);
}

function resolveDbPath(explicit) {
  if (explicit) return path.resolve(expandHome(explicit));
  if (process.env.OPENCODE_DB) {
    const fromEnv = process.env.OPENCODE_DB;
    if (path.isAbsolute(fromEnv)) return fromEnv;
    // OpenCode 把相对 OPENCODE_DB 解析到数据目录下。
    return path.join(os.homedir(), '.local', 'share', 'opencode', fromEnv);
  }

  const fallback = path.join(os.homedir(), '.local', 'share', 'opencode', 'opencode.db');
  if (fs.existsSync(fallback)) return fallback;

  const reported = queryOpencodeDbPath();
  return reported || fallback;
}

function openDatabase(dbPath) {
  if (!fs.existsSync(dbPath)) {
    throw new Error(`找不到 OpenCode 数据库: ${dbPath}\n` +
      '用 --db 或环境变量 OPENCODE_DB 指向其他位置；数据库通常随 OpenCode 服务创建。');
  }
  try {
    return new DatabaseSync(dbPath, { readOnly: true });
  } catch (error) {
    throw new Error(`无法只读打开数据库: ${dbPath}\n${error.message}`);
  }
}

function hasTable(db, name) {
  return Boolean(db.prepare(
    "select 1 from sqlite_master where type = 'table' and name = ?").get(name));
}

function formatTime(milliseconds) {
  const date = new Date(milliseconds);
  if (Number.isNaN(date.getTime())) return '未知时间';
  const pad = (value) => String(value).padStart(2, '0');
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ` +
    `${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

function expandHome(target) {
  if (target === '~' || target.startsWith('~/') || target.startsWith('~\\')) {
    return path.join(os.homedir(), target.slice(1));
  }
  return target;
}

function queryOpencodeDbPath() {
  try {
    const options = { encoding: 'utf8', timeout: 5000, windowsHide: true };
    const result = process.platform === 'win32'
      ? spawnSync(process.env.ComSpec || 'cmd.exe',
        ['/d', '/s', '/c', 'opencode debug paths db'], options)
      : spawnSync('opencode', ['debug', 'paths', 'db'], options);
    if (result.status !== 0 || !result.stdout) return '';
    const line = result.stdout.trim().split(/\r?\n/).pop().trim();
    return line && fs.existsSync(line) ? line : '';
  } catch {
    return '';
  }
}

module.exports = { resolveDbPath, openDatabase, hasTable, formatTime };
