#!/usr/bin/env node
/**
 * session-search：跨全部项目列出或检索 OpenCode 本地会话历史。
 *
 * 数据来源与边界：
 * - 默认读取 `~/.local/share/opencode/opencode.db`，可用 `--db` 或 `OPENCODE_DB` 覆盖。
 * - 只读打开数据库，OpenCode 运行中也能查询，不写库、不加锁。
 * - V2 会话在 `session_v2` + `session_message`；V1 旧会话在 `session` + `part`。
 * - 标题搜索与正文搜索分开统计；正文只取消息文本，不扫工具调用元数据。
 *
 * 用法与示例见 `--help`。
 */
'use strict';

const path = require('node:path');
const { parseArgs } = require('node:util');

const VERSION = '2026.11.20.0843';
const DEFAULT_LIMIT = 20;
const DEFAULT_RADIUS = 40;
const EXIT_ERROR = 2;

let helpers;
try {
  helpers = require('./session-db.js');
} catch (error) {
  fail(error.message);
}
const { resolveDbPath, openDatabase, hasTable, formatTime } = helpers;

const OPTIONS = {
  help: { type: 'boolean', short: 'h' },
  version: { type: 'boolean', short: 'V' },
  limit: { type: 'string', short: 'n' },
  dir: { type: 'string' },
  project: { type: 'string' },
  scope: { type: 'string' },
  days: { type: 'string' },
  'roots-only': { type: 'boolean' },
  archived: { type: 'boolean' },
  any: { type: 'boolean' },
  'max-snippet': { type: 'string' },
  'no-legacy': { type: 'boolean' },
  db: { type: 'string' },
  json: { type: 'boolean' },
};

const HELP = `用法: session-search [查询词...] [选项]

跨全部项目列出或检索 OpenCode 本地会话（只读）。无查询词时列出最近的会话；
有查询词时同时匹配标题与正文，多个词默认 AND（--any 改为 OR）。

选项:
  -n, --limit <n>       最多返回 n 个会话（默认 ${DEFAULT_LIMIT}；0 表示不限）
      --dir <文本>      只看目录包含该文本的会话（大小写不敏感）
      --project <文本>  只看项目 ID、路径或名称匹配的会话
      --scope <模式>    title | content | all（默认 all）
      --days <n>        只看最近 n 天更新过的会话
      --roots-only      排除子会话（subagent）
      --archived        包含已归档会话
      --any             多个查询词改为 OR（默认 AND）
      --max-snippet <n> 片段上下文长度，单位字符（默认 ${DEFAULT_RADIUS}）
      --no-legacy       不查 V1 旧表（session/part）
      --db <路径>       覆盖数据库路径（默认 $OPENCODE_DB 或 ~/.local/share/opencode/opencode.db）
      --json            输出 JSON（stdout 只放 JSON）
  -V, --version         显示版本
  -h, --help            显示本帮助

示例:
  session-search                              # 最近 20 个会话，覆盖所有目录
  session-search carapace                     # 标题或正文含 carapace
  session-search git 补全 --dir scripts       # 两个词都命中，且目录含 scripts
  session-search --days 7 --roots-only        # 最近 7 天的主会话
  session-search --json --limit 0             # 全量 JSON

退出码: 0 正常（含无匹配）；${EXIT_ERROR} 参数或读取错误。
`;

main(process.argv.slice(2));

function main(argv) {
  let parsed;
  try {
    parsed = parseArgs({ args: argv, options: OPTIONS, allowPositionals: true });
  } catch (error) {
    fail(error.message, true);
  }

  const { values, positionals } = parsed;
  if (values.help) {
    process.stdout.write(HELP);
    return;
  }
  if (values.version) {
    process.stdout.write(VERSION + '\n');
    return;
  }

  const options = normalizeOptions(values, positionals);
  if (!options) return;

  const dbPath = resolveDbPath(values.db);
  let db;
  try {
    db = openDatabase(dbPath);
  } catch (error) {
    fail(error.message);
  }

  try {
    const sessions = loadSessions(db, options.includeLegacy);
    const filtered = filterSessions(sessions, options);
    const results = options.terms.length
      ? searchSessions(db, filtered, options)
      : listSessions(filtered, options);

    if (options.json) {
      const payload = {
        db: dbPath,
        query: options.terms,
        count: results.length,
        results,
      };
      process.stdout.write(JSON.stringify(payload, null, 2) + '\n');
      return;
    }

    printResults(results, options);
  } finally {
    db.close();
  }
}

function normalizeOptions(values, terms) {
  const limit = parseInteger(values.limit, DEFAULT_LIMIT, '--limit', 0);
  if (limit === null) return null;

  const days = values.days === undefined ? 0 : parseInteger(values.days, 0, '--days', 1);
  if (days === null) return null;

  const radius = parseInteger(values['max-snippet'], DEFAULT_RADIUS, '--max-snippet', 10);
  if (radius === null) return null;

  const scope = values.scope || 'all';
  if (!['all', 'title', 'content'].includes(scope)) {
    fail(`--scope 只接受 title、content 或 all，收到: ${values.scope}`, true);
  }

  return {
    terms: terms.filter((term) => term.trim() !== '').map((term) => term.trim()),
    limit,
    days,
    radius,
    scope,
    dir: values.dir || '',
    project: values.project || '',
    rootsOnly: Boolean(values['roots-only']),
    includeArchived: Boolean(values.archived),
    matchAny: Boolean(values.any),
    includeLegacy: !values['no-legacy'],
    json: Boolean(values.json),
  };
}

function parseInteger(raw, fallback, flag, min) {
  if (raw === undefined) return fallback;
  const value = Number(raw);
  if (!Number.isInteger(value) || value < min) {
    fail(`${flag} 需要一个不小于 ${min} 的整数，收到: ${raw}`, true);
    return null;
  }
  return value;
}

function loadSessions(db, includeLegacy) {
  const hasV2 = hasTable(db, 'session_v2');
  const hasV1 = hasTable(db, 'session');
  if (!hasV2 && !hasV1) {
    fail('数据库里没有 session_v2 或 session 表，请确认 --db 指向 OpenCode 的 opencode.db。');
  }

  const sessions = [];
  if (hasV2) sessions.push(...querySessions(db, 'session_v2', false));
  if (includeLegacy && hasV1) sessions.push(...querySessions(db, 'session', true));

  const seen = new Set();
  return sessions.filter((session) => {
    if (seen.has(session.id)) return false;
    seen.add(session.id);
    return true;
  });
}

function querySessions(db, table, legacy) {
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
    legacy,
    titleMatches: 0,
    contentMatches: 0,
    totalMatches: 0,
    snippet: '',
  }));
}

function filterSessions(sessions, options) {
  const cutoff = options.days > 0 ? Date.now() - options.days * 86400000 : 0;
  const dir = options.dir.toLowerCase();
  const project = options.project.toLowerCase();

  return sessions.filter((session) => {
    if (!options.includeArchived && session.archived) return false;
    if (options.rootsOnly && session.parentID) return false;
    if (cutoff && session.updated < cutoff) return false;
    if (dir && !session.directory.toLowerCase().includes(dir)) return false;
    if (project) {
      const idHit = session.projectID.toLowerCase().includes(project);
      const pathHit = session.projectPath.toLowerCase().includes(project);
      const nameHit = session.projectName.toLowerCase().includes(project);
      if (!idHit && !pathHit && !nameHit) return false;
    }
    return true;
  });
}

function listSessions(sessions, options) {
  return sortByUpdated(sessions).slice(0, options.limit || sessions.length);
}

function searchSessions(db, sessions, options) {
  const perTerm = options.terms.map(() => new Map());

  options.terms.forEach((term, index) => {
    const bucket = perTerm[index];

    if (options.scope !== 'content') {
      for (const session of sessions) {
        const count = countOccurrences(session.title, term);
        if (count > 0) addMatch(bucket, session.id, 'title', count, '');
      }
    }

    if (options.scope !== 'title') {
      for (const source of messageSources(db, options.includeLegacy)) {
        const like = `%${escapeLike(term)}%`;
        for (const row of source.statement.all(like)) {
          const texts = extractTexts(row.data);
          let count = 0;
          let snippet = '';
          for (const text of texts) {
            const hits = countOccurrences(text, term);
            if (hits > 0) {
              count += hits;
              if (!snippet) snippet = snippetAround(text, term, options.radius);
            }
          }
          if (count > 0) addMatch(bucket, row.session_id, 'content', count, snippet);
        }
      }
    }
  });

  const results = [];
  for (const session of sessions) {
    const termMatches = options.terms.map((term, index) => perTerm[index].get(session.id) || null);
    const matched = options.matchAny
      ? termMatches.some(Boolean)
      : termMatches.every(Boolean);
    if (!matched) continue;

    const result = { ...session };
    let snippet = '';
    for (const match of termMatches) {
      if (!match) continue;
      result.titleMatches += match.title || 0;
      result.contentMatches += match.content || 0;
      if (!snippet && match.snippet) snippet = match.snippet;
    }
    result.totalMatches = result.titleMatches + result.contentMatches;
    result.snippet = snippet;
    results.push(result);
  }

  return sortByUpdated(results).slice(0, options.limit || results.length);
}

function messageSources(db, includeLegacy) {
  const sources = [];
  if (hasTable(db, 'session_message')) {
    sources.push({
      statement: db.prepare("select session_id, data from session_message where data like ? escape '\\'"),
    });
  }
  if (includeLegacy && hasTable(db, 'part')) {
    // 迁移过的会话两处都有消息；只对没有 session_message 的会话查旧表，避免重复计数。
    const skipMigrated = hasTable(db, 'session_message')
      ? ' and session_id not in (select session_id from session_message)'
      : '';
    sources.push({
      statement: db.prepare(
        "select session_id, data from part where data like ? escape '\\'" + skipMigrated),
    });
  }
  return sources;
}

function escapeLike(value) {
  return value.replace(/[\\%_]/g, (char) => '\\' + char);
}

function addMatch(bucket, sessionID, kind, count, snippet) {
  const current = bucket.get(sessionID) || { title: 0, content: 0, snippet: '' };
  current[kind] += count;
  if (!current.snippet && snippet) current.snippet = snippet;
  bucket.set(sessionID, current);
}

function extractTexts(raw) {
  let data;
  try {
    data = JSON.parse(raw);
  } catch {
    return [String(raw)];
  }
  if (!data || typeof data !== 'object') return [];

  const texts = [];
  if (typeof data.text === 'string') texts.push(data.text);
  if (Array.isArray(data.content)) {
    for (const part of data.content) {
      if (part && part.type === 'text' && typeof part.text === 'string') texts.push(part.text);
    }
  }
  return texts;
}

function countOccurrences(text, term) {
  const haystack = String(text).toLowerCase();
  const needle = term.toLowerCase();
  if (!needle) return 0;
  let count = 0;
  let index = 0;
  while ((index = haystack.indexOf(needle, index)) !== -1) {
    count += 1;
    index += needle.length;
  }
  return count;
}

function snippetAround(text, term, radius) {
  const flat = String(text).replace(/\s+/g, ' ').trim();
  const index = flat.toLowerCase().indexOf(term.toLowerCase());
  if (index === -1) return '';
  const start = Math.max(0, index - radius);
  const end = Math.min(flat.length, index + term.length + radius);
  const prefix = start > 0 ? '…' : '';
  const suffix = end < flat.length ? '…' : '';
  return prefix + flat.slice(start, end).trim() + suffix;
}

function sortByUpdated(sessions) {
  return sessions.slice().sort((a, b) => b.updated - a.updated);
}

function printResults(results, options) {
  if (results.length === 0) {
    process.stderr.write('未找到匹配的会话。\n');
    return;
  }

  for (const result of results) {
    const hits = options.terms.length ? `  ${result.totalMatches} 处命中` : '';
    const flags = [
      result.legacy ? 'V1' : '',
      result.parentID ? '子会话' : '',
      result.archived ? '已归档' : '',
    ].filter(Boolean).join(' · ');

    process.stdout.write(`${formatTime(result.updated)}${hits}  ${result.title || '(无标题)'}\n`);
    process.stdout.write(`  ${result.directory || '(未知目录)'}  ·  ${result.id}${flags ? '  ·  ' + flags : ''}\n`);
    if (result.snippet) process.stdout.write(`  ${result.snippet}\n`);
    process.stdout.write('\n');
  }

  if (options.terms.length) {
    process.stderr.write(`共 ${results.length} 个会话。\n`);
  }
}

function fail(message, usage = false) {
  process.stderr.write(message + '\n');
  if (usage) process.stderr.write('\n用 --help 查看用法。\n');
  process.exit(EXIT_ERROR);
}
