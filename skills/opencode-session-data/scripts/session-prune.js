#!/usr/bin/env node
/**
 * session-prune：按“最后更新时间”清理超过指定时长的 OpenCode 会话。
 *
 * 默认只预览，不改库；加 `--apply` 才执行。只处理根会话：
 * - 根会话及其子会话家族里只要有一个仍在运行，或最近有更新，就跳过整个家族；
 * - 默认跳过已归档会话（`--include-archived` 才纳入）；
 * - 删除会连带删除子会话；归档只隐藏，不释放空间；
 * - `--export <目录>` 在删除/归档前逐个调用服务端导出，导出失败则跳过该会话。
 *
 * 用法与示例见 `--help`。
 */
'use strict';

const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { parseArgs } = require('node:util');

const VERSION = '2026.11.20.0920';
const DEFAULT_OLDER = '7d';
const EXIT_PARTIAL = 1;
const EXIT_ERROR = 2;

let helpers;
try {
  helpers = require('./session-db.js');
} catch (error) {
  process.stderr.write(error.message + '\n');
  process.exit(EXIT_ERROR);
}
const { resolveDbPath, openDatabase, hasTable, formatTime } = helpers;

const OPTIONS = {
  help: { type: 'boolean', short: 'h' },
  version: { type: 'boolean', short: 'V' },
  'older-than': { type: 'string' },
  apply: { type: 'boolean' },
  archive: { type: 'boolean' },
  export: { type: 'string' },
  dir: { type: 'string' },
  project: { type: 'string' },
  'include-archived': { type: 'boolean' },
  limit: { type: 'string', short: 'n' },
  db: { type: 'string' },
  json: { type: 'boolean' },
};

const HELP = `用法: session-prune [选项]

按最后更新时间清理 OpenCode 会话。默认只预览（dry-run），加 --apply 才执行。
只处理根会话；家族里只要还有运行中或最近更新的成员，就跳过整个家族。

选项:
      --older-than <时长>  超过多久未更新才算候选，支持 h/d/w（默认 ${DEFAULT_OLDER}）
      --apply              执行删除（默认只预览）
      --archive            改为归档而不是删除；不释放磁盘空间
      --export <目录>      执行前导出根会话及其子会话为 JSON（服务端 sanitize）
      --dir <文本>         只看目录包含该文本的会话
      --project <文本>     只看项目 ID、路径或名称匹配的会话
      --include-archived   把已归档会话也纳入候选
  -n, --limit <n>          最多处理 n 个根会话（默认全部，0 表示不限）
      --db <路径>          覆盖数据库路径（默认 $OPENCODE_DB 或 ~/.local/share/opencode/opencode.db）
      --json               输出 JSON（stdout 只放 JSON）
  -V, --version            显示版本
  -h, --help               显示本帮助

示例:
  session-prune                                      # 预览超过 7 天未更新的会话
  session-prune --older-than 30d                     # 预览超过 30 天的会话
  session-prune --older-than 7d --apply              # 执行删除
  session-prune --older-than 7d --apply --archive    # 改为归档
  session-prune --apply --export ./session-backup    # 先导出再删除
  session-prune --older-than 7d --dir repos --apply  # 只处理目录含 repos 的会话

边界:
  - dry-run 只读数据库，不需要 OpenCode 服务；
  - --apply 需要本机后台服务（service.json）可用；导出/删除/归档都走服务端 API；
  - 删除不可恢复；归档不会释放空间；删除后数据库文件需 VACUUM 才会缩小。

退出码: 0 正常；${EXIT_PARTIAL} 部分失败；${EXIT_ERROR} 参数或执行错误。
`;

main(process.argv.slice(2));

async function main(argv) {
  let parsed;
  try {
    parsed = parseArgs({ args: argv, options: OPTIONS, allowPositionals: true });
  } catch (error) {
    fail(error.message, true);
  }

  const { values, positionals } = parsed;
  if (positionals.length > 0) fail('不接受位置参数；用 --older-than、--dir 等选项。', true);
  if (values.help) {
    process.stdout.write(HELP);
    return;
  }
  if (values.version) {
    process.stdout.write(VERSION + '\n');
    return;
  }

  const options = normalizeOptions(values);
  const dbPath = resolveDbPath(values.db);
  let db;
  try {
    db = openDatabase(dbPath);
  } catch (error) {
    fail(error.message);
  }

  try {
    const sessions = loadSessions(db);
    const cutoff = Date.now() - options.olderMs;
    const active = await loadActiveSessions(options.apply);
    const candidates = selectCandidates(sessions, options, cutoff, active);

    const messageBytes = estimateMessageBytes(db, sessions, candidates);

    if (options.exportDir && !options.apply) {
      fail('--export 只能和 --apply 一起使用，避免只导出但没执行。', true);
    }

    const payload = {
      database: dbPath,
      olderThan: options.olderThan,
      cutoff,
      apply: options.apply,
      archive: options.archive,
      count: candidates.length,
      messageBytes,
      candidates: candidates.map((session) => ({
        id: session.id,
        title: session.title,
        directory: session.directory,
        updated: session.updated,
        updatedAt: formatTime(session.updated),
        parentID: session.parentID,
        archived: Boolean(session.archived),
        familySize: session.familyIDs ? session.familyIDs.length : 1,
      })),
      results: [],
      failures: 0,
    };

    if (!options.apply) {
      if (options.json) {
        process.stdout.write(JSON.stringify(payload, null, 2) + '\n');
      } else {
        printPreview(payload, options);
      }
      return;
    }

    const applied = await applyCandidates(candidates, options);
    payload.results = applied.results;
    payload.failures = applied.failures;

    if (options.json) {
      process.stdout.write(JSON.stringify(payload, null, 2) + '\n');
    } else {
      printApplySummary(payload, options);
    }

    process.exitCode = applied.failures > 0 ? EXIT_PARTIAL : 0;
  } finally {
    db.close();
  }
}

function normalizeOptions(values) {
  const olderThan = values['older-than'] || DEFAULT_OLDER;
  const olderMs = parseDuration(olderThan);
  const limit = parseInteger(values.limit, 0, '--limit', 0);

  return {
    olderThan,
    olderMs,
    apply: Boolean(values.apply),
    archive: Boolean(values.archive),
    exportDir: values.export ? path.resolve(values.export) : '',
    dir: (values.dir || '').toLowerCase(),
    project: (values.project || '').toLowerCase(),
    includeArchived: Boolean(values['include-archived']),
    limit,
    json: Boolean(values.json),
  };
}

function parseDuration(value) {
  const match = /^(\d+)([hdw])$/.exec(String(value).trim());
  if (!match) fail(`--older-than 需要 7d、24h 或 2w 这样的格式，收到: ${value}`, true);
  const amount = Number(match[1]);
  if (!Number.isInteger(amount) || amount < 1) fail('--older-than 必须是正整数。', true);
  const unit = { h: 3600000, d: 86400000, w: 604800000 }[match[2]];
  return amount * unit;
}

function parseInteger(raw, fallback, flag, min) {
  if (raw === undefined) return fallback;
  const value = Number(raw);
  if (!Number.isInteger(value) || value < min) {
    fail(`${flag} 需要一个不小于 ${min} 的整数，收到: ${raw}`, true);
  }
  return value;
}

function loadSessions(db) {
  const table = hasTable(db, 'session_v2') ? 'session_v2' : (hasTable(db, 'session') ? 'session' : '');
  if (!table) {
    fail('数据库里没有 session_v2 或 session 表，请确认 --db 指向 OpenCode 的 opencode.db。');
  }

  const projectPath = hasTable(db, 'project')
    ? '(select p.worktree from project p where p.id = s.project_id)'
    : 'null';
  const sql = `select s.id as id, s.parent_id as parentID, s.title as title,
      s.directory as directory, s.project_id as projectID,
      ${projectPath} as projectPath,
      s.time_created as created, s.time_updated as updated,
      s.time_archived as archived
    from ${table} s`;

  return db.prepare(sql).all().map((row) => ({
    id: row.id,
    parentID: row.parentID || '',
    title: row.title || '',
    directory: row.directory || '',
    projectID: row.projectID || '',
    projectPath: row.projectPath || '',
    projectName: row.projectPath ? path.basename(row.projectPath) : '',
    created: Number(row.created) || 0,
    updated: Number(row.updated) || 0,
    archived: row.archived === null || row.archived === undefined ? 0 : Number(row.archived),
  }));
}

function selectCandidates(sessions, options, cutoff, active) {
  const byId = new Map(sessions.map((session) => [session.id, session]));
  const children = new Map();
  for (const session of sessions) {
    if (!session.parentID) continue;
    const list = children.get(session.parentID) || [];
    list.push(session);
    children.set(session.parentID, list);
  }

  const currentID = process.env.OPENCODE_SESSION_ID || '';
  const currentRoot = currentID ? rootOf(currentID, byId) : '';
  const families = new Map();
  const familyOf = (root) => {
    if (families.has(root.id)) return families.get(root.id);
    const members = [];
    const stack = [root];
    while (stack.length > 0) {
      const current = stack.pop();
      members.push(current);
      for (const child of children.get(current.id) || []) stack.push(child);
    }
    families.set(root.id, members);
    return members;
  };

  const candidates = [];
  for (const session of sessions) {
    if (session.parentID) continue;
    if (currentRoot && session.id === currentRoot) continue;

    const family = familyOf(session);
    if (currentID && family.some((member) => member.id === currentID)) continue;
    if (family.some((member) => active.has(member.id))) continue;
    if (!options.includeArchived && session.archived) continue;
    if (options.dir && !session.directory.toLowerCase().includes(options.dir)) continue;
    if (options.project) {
      const haystack = [
        session.projectID,
        session.projectPath,
        session.projectName,
      ].join('\n').toLowerCase();
      if (!haystack.includes(options.project)) continue;
    }
    if (family.some((member) => member.updated >= cutoff)) continue;

    session.familyIDs = family.map((member) => member.id);
    candidates.push(session);
  }

  candidates.sort((left, right) => left.updated - right.updated);
  return options.limit > 0 ? candidates.slice(0, options.limit) : candidates;
}

function rootOf(sessionID, byId) {
  let current = byId.get(sessionID);
  while (current && current.parentID && byId.has(current.parentID)) {
    current = byId.get(current.parentID);
  }
  return current ? current.id : '';
}

function estimateMessageBytes(db, sessions, roots) {
  const table = hasTable(db, 'session_message')
    ? 'session_message'
    : (hasTable(db, 'part') ? 'part' : '');
  if (!table || roots.length === 0) return 0;

  const ids = roots.flatMap((root) => (root.familyIDs && root.familyIDs.length > 0 ? root.familyIDs : [root.id]));
  let total = 0;
  for (let index = 0; index < ids.length; index += 400) {
    const chunk = ids.slice(index, index + 400);
    const placeholders = chunk.map(() => '?').join(',');
    const row = db.prepare(
      `select coalesce(sum(length(data)), 0) as bytes from ${table} where session_id in (${placeholders})`,
    ).get(...chunk);
    total += Number(row.bytes) || 0;
  }
  return total;
}

async function loadActiveSessions(required) {
  try {
    const payload = await apiJSON('/api/session/active');
    return new Set(Object.keys(payload.data || {}));
  } catch (error) {
    if (required) {
      fail('无法读取运行中的会话，已停止执行。请确认 OpenCode 后台服务在运行。\n' + error.message);
    }
    process.stderr.write('提示: 无法读取活动会话，预览可能包含正在运行的会话；执行前请启动 OpenCode 服务。\n');
    return new Set();
  }
}

async function applyCandidates(candidates, options) {
  const results = [];
  let failures = 0;

  for (const session of candidates) {
    const result = {
      id: session.id,
      title: session.title,
      directory: session.directory,
      action: options.archive ? 'archive' : 'delete',
      status: 'ok',
      error: '',
    };

    try {
      if (options.exportDir) {
        for (const id of session.familyIDs && session.familyIDs.length > 0 ? session.familyIDs : [session.id]) {
          await exportSession(id, options.exportDir);
        }
      }
      if (options.archive) {
        await apiRequest(`/api/session/${encodeURIComponent(session.id)}`, {
          method: 'PATCH',
          body: JSON.stringify({ archived: true }),
        });
      } else {
        await apiRequest(`/api/session/${encodeURIComponent(session.id)}`, { method: 'DELETE' });
      }
    } catch (error) {
      if (isNotFound(error)) {
        result.status = 'skipped';
        result.error = '会话已不存在';
      } else {
        result.status = 'failed';
        result.error = error.message;
        failures += 1;
      }
    }

    results.push(result);
    if (!options.json) {
      const label = result.status === 'ok' ? (options.archive ? '已归档' : '已删除') : result.status;
      process.stdout.write(`[${label}] ${session.title || '(无标题)'}  ${session.id}`);
      if (result.error) process.stdout.write(`  ${result.error}`);
      process.stdout.write('\n');
    }
  }

  return { results, failures };
}

async function exportSession(sessionID, directory) {
  fs.mkdirSync(directory, { recursive: true });
  const response = await apiRequest(
    `/api/experimental/session/${encodeURIComponent(sessionID)}/export?sanitize=true`,
  );
  const payload = await response.json();
  fs.writeFileSync(path.join(directory, `${sessionID}.json`), JSON.stringify(payload, null, 2) + '\n', 'utf8');
}

function readService() {
  const file = path.join(os.homedir(), '.config', 'opencode', 'service.json');
  let data;
  try {
    data = JSON.parse(fs.readFileSync(file, 'utf8'));
  } catch (error) {
    throw new Error(`无法读取 ${file}：${error.message}\n请先启动 OpenCode 后台服务。`);
  }
  if (!data.port || !data.password) {
    throw new Error(`${file} 缺少 port/password；请先启动 OpenCode 后台服务。`);
  }
  return {
    base: `http://127.0.0.1:${data.port}`,
    headers: {
      Authorization: 'Basic ' + Buffer.from(`opencode:${data.password}`).toString('base64'),
    },
  };
}

async function apiJSON(pathname, init) {
  const response = await apiRequest(pathname, init);
  return response.json();
}

async function apiRequest(pathname, init = {}) {
  const service = readService();
  let response;
  try {
    response = await fetch(service.base + pathname, {
      ...init,
      headers: {
        ...service.headers,
        ...(init.body ? { 'Content-Type': 'application/json' } : {}),
        ...(init.headers || {}),
      },
      signal: AbortSignal.timeout(15000),
    });
  } catch (error) {
    throw new Error(`请求 OpenCode 服务失败：${error.message}`);
  }
  if (!response.ok) {
    const text = await response.text().catch(() => '');
    const error = new Error(`HTTP ${response.status} ${pathname}${text ? '\n' + text.slice(0, 300) : ''}`);
    error.status = response.status;
    throw error;
  }
  return response;
}

function isNotFound(error) {
  return error && Number(error.status) === 404;
}

function printPreview(payload, options) {
  process.stdout.write(
    `早于 ${options.olderThan}（${formatTime(payload.cutoff)}）的根会话：${payload.count} 个，` +
    `约 ${formatBytes(payload.messageBytes)} 消息数据\n\n`,
  );

  for (const candidate of payload.candidates) {
    process.stdout.write(
      `${candidate.updatedAt}  ${candidate.title || '(无标题)'}\n` +
      `  ${candidate.directory || '(未知目录)'}  ·  ${candidate.id}` +
      `${candidate.familySize > 1 ? `  ·  含 ${candidate.familySize - 1} 个子会话` : ''}` +
      `${candidate.archived ? '  ·  已归档' : ''}\n`,
    );
  }

  if (payload.count === 0) process.stdout.write('没有符合条件的会话。\n');
  process.stdout.write(
    '\n[DRY-RUN] 未修改任何会话。' +
    `${options.archive ? '加 --apply 执行归档。' : '加 --apply 执行删除；加 --archive 改为归档。'}\n`,
  );
}

function printApplySummary(payload, options) {
  const ok = payload.results.filter((result) => result.status === 'ok').length;
  const skipped = payload.results.filter((result) => result.status === 'skipped').length;
  process.stdout.write(
    `\n完成：${ok} 个${options.archive ? '已归档' : '已删除'}，` +
    `${skipped} 个跳过，${payload.failures} 个失败。\n`,
  );
  if (!options.archive && ok > 0) {
    process.stdout.write('删除后数据库文件不会自动缩小；需要时停服务后执行 VACUUM。\n');
  }
}

function formatBytes(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function fail(message, usage = false) {
  process.stderr.write(message + '\n');
  if (usage) process.stderr.write('\n用 --help 查看用法。\n');
  process.exit(EXIT_ERROR);
}
