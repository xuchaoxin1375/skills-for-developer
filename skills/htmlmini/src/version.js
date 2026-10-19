import { createRequire } from 'node:module';

// 版本号唯一真源是 package.json 的 version 字段（由 scripts/stamp-version.mjs 按日期时间写入）。
// 运行时读一次，避免在 cli/mcp/UA 里各写一份而漂移。
const require = createRequire(import.meta.url);
const pkg = require('../package.json');

export const VERSION = String(pkg.version || '0.0.0');

/** 一行式版本标识，供 --version 与 MCP serverInfo 使用。 */
export const VERSION_LINE = `htmlmini ${VERSION}`;
