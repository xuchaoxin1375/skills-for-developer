/** 载荷外围的展示层：来源哨兵行与终端留白。纯函数，便于单测（cli.js 只负责决定何时用）。 */

/**
 * 用起止注释行包住载荷，标出来源、状态码、抓取方式与时刻；正文本身一字不改。
 * 选 HTML 注释而不是 ASCII 哨兵：markdown 渲染后不可见，落盘 .md 也不多出可见噪声；
 * 一行一条，grep 与按行剥离同样方便。默认不加，需要时 --source-marks 显式打开。
 */
export function markSource(out, info) {
  const status = Number.isFinite(info.status) ? String(info.status) : info.rendered ? 'unknown' : 'n/a';
  const via = info.rendered ? 'browser' : 'static';
  const body = out.replace(/\n+$/, '');
  const begin = `<!-- htmlmini:source begin status=${status} url=${info.source} render=${via} fetched=${info.fetchedAt} -->`;
  const end = `<!-- htmlmini:source end url=${info.source} -->`;
  return body ? `${begin}\n${body}\n${end}` : `${begin}\n${end}`;
}

/**
 * 在载荷上下各留一行空白：终端里正文不至于紧贴 `[read]` / `[write]` 日志行。
 * 只在 stdout 是终端且没加哨兵行时用；管道、重定向与 `-o` 写纯载荷。
 */
export function padPayload(out) {
  const body = out.replace(/\n+$/, '');
  return body ? `\n${body}\n\n` : out;
}
