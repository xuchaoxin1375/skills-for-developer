#!/usr/bin/env node
// 按日期时间给 htmlmini 打版本号：YYYY.MM.DD.HHmm（本地时间）。
// 版本号唯一真源是 package.json 的 version，这里只写它；cli/mcp/UA 运行时读取。
//
//   node scripts/stamp-version.mjs              # 用当前本地时间
//   node scripts/stamp-version.mjs 2026.10.19.1805
//   pnpm stamp                                  # 同上（见 package.json scripts）
import { readFile, writeFile } from 'node:fs/promises';

const pkgUrl = new URL('../package.json', import.meta.url);
const pad = (n) => String(n).padStart(2, '0');

export function stampVersion(d = new Date()) {
  return `${d.getFullYear()}.${pad(d.getMonth() + 1)}.${pad(d.getDate())}.${pad(d.getHours())}${pad(d.getMinutes())}`;
}

const arg = process.argv[2];
const version = arg ?? stampVersion();

if (!/^\d{4}\.\d{2}\.\d{2}\.\d{4}$/.test(version)) {
  console.error(`version must look like YYYY.MM.DD.HHmm, got "${version}"`);
  process.exit(2);
}

const pkg = JSON.parse(await readFile(pkgUrl, 'utf8'));
pkg.version = version;
await writeFile(pkgUrl, `${JSON.stringify(pkg, null, 2)}\n`, 'utf8');
console.log(`htmlmini ${version}`);
