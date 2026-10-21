/**
 * PowerShell 编码守卫（OpenCode 插件）
 *
 * 职责：把 `skills/powershell-pitfalls` 中"每次 shell 调用都要做"的机械步骤前置到 shell 钩子：
 *   1. Windows 上的 PowerShell 调用自动前置编码语句（同次调用内、第一次输出之前）。
 *   2. 原生命令输出经 PowerShell 文本层（管道/重定向）时，给出可执行的替代建议。
 *
 * 明确不做的事：判断类规则（何时加 `-ErrorAction Stop`、退出码契约、落盘链路设计、
 * 何时改用原生 read 工具）仍由 skill 维护。插件不替代理做判读，也不改写命令结构，
 * 不自动补 `-Encoding UTF8`（GBK/ANSI 文件会被改坏），不自动重排管道。
 *
 * 规则出处与实测证据见 skills/powershell-pitfalls（含 references/encoding-read.md）。
 */

import { appendFileSync, existsSync, mkdirSync, statSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";

export const PLUGIN_ID = "powershell-encoding-guard";

export type GuardMode = "off" | "warn" | "enforce";

export interface GuardOptions {
  /** off=不动作；warn=前置编码 + 风险提示（默认）；enforce=风险形态直接拒绝执行 */
  mode?: GuardMode;
  /** 未识别到外壳时按 PowerShell 处理（默认 false：Git Bash 下不能注入 PowerShell 语句） */
  assumePowerShell?: boolean;
  /** 非 Windows 平台也注入（默认 false：pwsh 7 默认即 UTF-8） */
  injectOnPosix?: boolean;
  /** 覆盖默认前置语句 */
  preamble?: string;
  /** 仅供测试覆盖平台判定 */
  platform?: string;
}

/** 默认前置语句：与 skill 的"安全前缀"一致，幂等。 */
export const DEFAULT_PREAMBLE = [
  "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8",
  "$OutputEncoding = [System.Text.Encoding]::UTF8",
].join("\n");

const PREAMBLE_MARKERS = [/\[Console\]::OutputEncoding/, /\$OutputEncoding\s*=/];

/**
 * 进程级注册表（记录各 location 的钩子句柄，供重复装载时注销旧钩子）。
 *
 * 键用 `Symbol.for` 而不是字符串：宿主会在 `globalThis[插件 id]` 上挂自己的东西，
 * 早期实现用字符串键当注册表，宿主写入后 `registry.get` 不再是函数，setup 直接抛错，
 * 表现为"插件静默失效、热重载后钩子全没了"（日志里是 `failed to load plugin`）。
 */
const REGISTRY_KEY = Symbol.for("opencode.plugin-registry.powershell-encoding-guard");

type RegistryEntry = { dispose: () => Promise<void> };

function getRegistry(): Map<string | symbol, RegistryEntry> {
  const scope = globalThis as unknown as Record<symbol, unknown>;
  const existing = scope[REGISTRY_KEY];
  if (existing instanceof Map) return existing as Map<string | symbol, RegistryEntry>;
  const created = new Map<string | symbol, RegistryEntry>();
  scope[REGISTRY_KEY] = created;
  return created;
}

/** 诊断日志文件：宿主静默吞掉装载失败，这里留一条可查的痕迹。 */
const DIAG_FILE = join(tmpdir(), "opencode", "powershell-encoding-guard.log");
const DIAG_MAX_BYTES = 512 * 1024;

export function writeDiagnostic(line: string): void {
  try {
    mkdirSync(dirname(DIAG_FILE), { recursive: true });
    const size = existsSync(DIAG_FILE) ? statSync(DIAG_FILE).size : 0;
    if (size > DIAG_MAX_BYTES) {
      // 超限就清空重来，避免临时文件无限增长
      writeFileSync(DIAG_FILE, "", "utf8");
    }
    appendFileSync(DIAG_FILE, `${new Date().toISOString()} ${line}\n`, "utf8");
  } catch {
    /* 诊断通道失败不影响插件主流程 */
  }
}

/**
 * 原生命令清单：输出会经过 PowerShell 文本层的可执行文件。
 *
 * 刻意排除 PowerShell 内置别名（cat/ls/cp/mv/rm/sort/where/tee/clear/write/echo…）：
 * 它们在 PowerShell 里是 cmdlet，别名走 .NET 字符串，不属于本插件要提示的形态。
 * Windows 自带的原生 exe（findstr/fc 等）与 Unix 工具同等对待，一并列入。
 * 注意 `where` / `sort` 在 Windows 上仍是别名（Where-Object / Sort-Object），不要加进来。
 */
const NATIVE_COMMANDS = new Set([
  // 版本控制 / 协作
  "git", "gh", "glab", "svn", "hg", "hg.exe",
  // 运行时与包管理
  "node", "npm", "npx", "pnpm", "yarn", "bun", "deno", "tsx", "tsc", "eslint", "prettier",
  "python", "python3", "py", "pip", "pip3", "pipx", "uv", "poetry", "conda",
  "java", "javac", "mvn", "gradle", "kotlin", "kotlinc", "scala", "dotnet", "go", "cargo",
  "rustc", "ruby", "php", "perl", "lua", "dart", "flutter", "swift",
  // 检索与文本
  "rg", "ag", "grep", "egrep", "fgrep", "find", "sed", "awk", "uniq", "wc", "head", "tail",
  "cut", "tr", "jq", "yq", "diff", "patch", "xargs", "less", "more",
  "findstr", "fc",
  // 网络
  "curl", "wget", "ssh", "scp", "sftp", "rsync", "ping", "nslookup", "dig", "host",
  // 容器与基础设施
  "docker", "kubectl", "helm", "terraform", "ansible", "vagrant", "make", "cmake", "ninja",
  // 媒体与数据库
  "ffmpeg", "sqlite3", "psql", "mysql", "redis-cli",
  // 归档与磁盘
  "tar", "zip", "unzip", "gzip", "gunzip", "zstd", "7z", "du", "df", "stat", "file",
  // shell 与系统命令
  "pwsh", "powershell", "cmd", "cmd.exe", "bash", "sh", "zsh", "fish", "wsl",
  "whoami", "systeminfo", "tasklist", "ipconfig", "netstat", "ss", "nslookup",
]);

/** 判定为"可能产出 shell 命令"的工具名（OpenCode 的 shell 工具 id 依版本而异）。 */
const SHELL_TOOL_PATTERN = /^(bash|shell|ps|powershell|cmd|terminal|run_shell|sh)$/i;

export interface RiskFinding {
  kind: "pipe" | "redirect";
  detail: string;
}

export interface ShellCreateBefore {
  command: string;
  cwd: string;
  timeout: number;
  shell: string;
  env: Record<string, string | undefined>;
}

export interface ToolResultLike {
  content?: string | ReadonlyArray<{ type: string; text?: string }>;
  metadata?: Record<string, unknown>;
}

/** 判断外壳是否 PowerShell（pwsh / powershell，含 .exe 与完整路径）。 */
export function isPowerShell(shell: string): boolean {
  const value = (shell ?? "").trim();
  if (!value) return false;
  const base = value.split(/[\\/]/).pop() ?? value;
  return /^(pwsh|powershell)(\.exe)?$/i.test(base);
}

/** 命令里是否已经设置过编码（幂等判定）。 */
export function hasPreamble(command: string): boolean {
  return PREAMBLE_MARKERS.some((rx) => rx.test(command));
}

/** 返回注入前置后的命令；已含前置则原样返回。 */
export function buildPreamble(command: string, preamble: string = DEFAULT_PREAMBLE): string {
  if (hasPreamble(command)) return command;
  return `${preamble}\n${command}`;
}

/** 把引号内内容替换成空格，避免把字符串里的 | 和 > 当成语法。 */
function maskQuoted(text: string): string {
  let out = "";
  let quote: string | null = null;
  for (const ch of text) {
    if (quote) {
      if (ch === quote) {
        quote = null;
        out += " ";
      } else {
        out += " ";
      }
      continue;
    }
    if (ch === "'" || ch === '"') {
      quote = ch;
      out += " ";
      continue;
    }
    out += ch;
  }
  return out;
}

/** 按行与顶层分号切分语句。 */
function splitStatements(command: string): string[] {
  return maskQuoted(command)
    .split(/[\r\n;]+/)
    .map((s) => s.trim())
    .filter(Boolean);
}

/** 取语句头部命令名（小写、去扩展名、去路径）。 */
function headCommand(statement: string): string {
  const value = statement.trim();
  const match = value.match(/^(?:&\s*)?(?:'([^']+)'|"([^"]+)"|([^\s|&<>]+))/);
  if (!match) return "";
  const raw = (match[1] ?? match[2] ?? match[3] ?? "").trim();
  const base = raw.split(/[\\/]/).pop() ?? raw;
  return base.replace(/\.(exe|cmd|bat|com)$/i, "").toLowerCase();
}

/** 语句头不是原生命令时，尝试从赋值右侧再取一次（`$x = git log` 这类写法）。 */
function resolveHead(statement: string): string {
  const head = headCommand(statement);
  if (head && NATIVE_COMMANDS.has(head)) return head;
  const assigned = statement.match(/=\s*([^\s|&<>]+)/);
  if (!assigned) return head;
  const candidate = (assigned[1] ?? "").split(/[\\/]/).pop() ?? "";
  return candidate.replace(/\.(exe|cmd|bat|com)$/i, "").toLowerCase();
}

/**
 * 找出"原生命令输出经 PowerShell 文本层"的高危形态：
 *   - 原生命令 → PowerShell cmdlet 的管道（cmdlet 消费的是已解码字符串）；
 *   - 原生命令 → 文件的 stdout 重定向（先解码再按目标编码写回）。
 * 原生命令 → 原生命令的管道保持字节，不提示。
 */
/**
 * 拆分管道段：忽略 PowerShell 7 的条件运算符 `||`（右侧仅在左侧失败时执行，不是数据管道）。
 */
function splitPipe(statement: string): string[] {
  const parts: string[] = [];
  let current = "";
  for (let i = 0; i < statement.length; i++) {
    const ch = statement[i];
    if (ch === "|" && statement[i + 1] === "|") {
      current += "||";
      i++;
      continue;
    }
    if (ch === "|") {
      parts.push(current);
      current = "";
      continue;
    }
    current += ch;
  }
  parts.push(current);
  return parts;
}

/**
 * 是否存在 stdout 重定向。
 *
 * `> file`、`1> file`、`&> file`（含全部流）都要算：它们把子进程字节先经 .NET 文本层
 * 再写回文件，属于高危形态。`2> file`（仅 stderr）与 `2>&1`（并入 stdout）不算。
 */
function hasStdoutRedirect(statement: string): boolean {
  for (let i = 0; i < statement.length; i++) {
    if (statement[i] !== ">") continue;
    const prev = statement[i - 1];
    if (prev === "2") continue; // 2> 只重定向 stderr
    if (prev === "&" && statement[i - 2] === "2") continue; // 2>&1
    return true;
  }
  return false;
}

export function findRisks(command: string): RiskFinding[] {
  const findings: RiskFinding[] = [];
  for (const statement of splitStatements(command)) {
    const head = resolveHead(statement);
    if (!head || !NATIVE_COMMANDS.has(head)) continue;

    const parts = splitPipe(statement);
    if (parts.length > 1) {
      const right = parts.slice(1).join("|");
      const rightHead = headCommand(right);
      if (!rightHead || !NATIVE_COMMANDS.has(rightHead)) {
        findings.push({ kind: "pipe", detail: `${head} | ${rightHead || "…"}` });
      }
    }

    if (hasStdoutRedirect(statement)) {
      findings.push({ kind: "redirect", detail: `${head} > 文件` });
    }
  }
  return findings;
}

/** 风险提示文案：给出可执行替代，不下"命令错了"的结论。 */
export function riskNote(findings: RiskFinding[]): string {
  const list = findings.map((f) => f.detail).join("、");
  return [
    `[${PLUGIN_ID}] 原生命令输出经 PowerShell 文本层（管道/重定向）：${list}。`,
    "这类链路的输出保真不稳定（实测出现过\"设了编码反而更乱\"），退出码 0 或纯英文输出不能证明读取正确。",
    "替代做法：让程序自己筛选（--format / 原生 grep）、用程序自带的 --out 落盘，或改走字节闸门；",
    "判读与排障见 skills/powershell-pitfalls（references/encoding-read.md）。",
  ].join("\n");
}

/** 拒绝执行时的报错文案。 */
export function riskError(findings: RiskFinding[]): string {
  const list = findings.map((f) => f.detail).join("、");
  return [
    `[${PLUGIN_ID}] 拒绝执行：原生命令输出经 PowerShell 文本层（管道/重定向）：${list}。`,
    "请改为：让程序自己筛选（--format / 原生 grep）、用程序自带的 --out 落盘，或改走字节闸门；",
    "确需该形态时改用 warn 模式。判读与排障见 skills/powershell-pitfalls。",
  ].join("\n");
}

function isShellTool(tool: string): boolean {
  return SHELL_TOOL_PATTERN.test(tool ?? "");
}

function resolveOptions(ctx: { options?: unknown }): Required<GuardOptions> {
  const raw = (ctx?.options ?? {}) as GuardOptions;
  const envMode = process.env.OPENCODE_PS_GUARD_MODE;
  const mode = (raw.mode ?? envMode ?? "warn") as GuardMode;
  return {
    mode: mode === "off" || mode === "enforce" || mode === "warn" ? mode : "warn",
    assumePowerShell: raw.assumePowerShell === true,
    injectOnPosix: raw.injectOnPosix === true,
    preamble: typeof raw.preamble === "string" && raw.preamble.trim() ? raw.preamble : DEFAULT_PREAMBLE,
    platform: typeof raw.platform === "string" ? raw.platform : process.platform,
  };
}

/**
 * 解析 location 标识：用于按 location 记账钩子句柄。
 * 各版本宿主暴露的位置信息位置不一（location.directory / location.project.canonical /
 * project.canonical / directory），逐个探测；都拿不到时返回 null。
 */
export function resolveLocationKey(ctx: unknown): string | null {
  const c = (ctx ?? {}) as {
    location?: { directory?: string; project?: { canonical?: string; worktree?: string } };
    directory?: string;
    project?: { canonical?: string; worktree?: string };
  };
  const candidates = [
    c.location?.project?.canonical,
    c.location?.project?.worktree,
    c.location?.directory,
    c.project?.canonical,
    c.project?.worktree,
    c.directory,
  ];
  for (const value of candidates) {
    if (typeof value === "string" && value.trim()) return value;
  }
  return null;
}

/** 描述宿主在 globalThis[插件 id] 上放了什么，便于排查键冲突。 */
function describeHostValue(): string {
  const value = (globalThis as unknown as Record<string, unknown>)[PLUGIN_ID];
  if (value === undefined) return "undefined";
  if (value === null) return "null";
  if (value instanceof Map) return `Map(${value.size})`;
  if (value instanceof Set) return `Set(${value.size})`;
  const type = typeof value;
  if (type === "object") {
    const keys = Object.keys(value as object);
    return `object{${keys.slice(0, 5).join(",")}${keys.length > 5 ? ",…" : ""}}`;
  }
  return type;
}

/**
 * 插件入口。
 *
 * 钩子分工：
 *   - shell "create.before"：知道实际外壳，负责注入编码前置并记录风险形态；
 *   - tool "execute.before"：记录原始命令；enforce 模式下直接拒绝高危形态；
 *   - tool "execute.after"：把风险提示追加到工具结果，让代理看到替代方案。
 *
 * 装载与卸载：同一进程内可能被重复装载（自动发现 + 配置条目）或重新装载（配置热重载）。
 * 因此把钩子句柄记在进程级注册表里，重复装载时先注销旧钩子再注册新的，
 * 避免"旧实例被卸载、新实例跳过注册"导致钩子静默失效。
 * 注册表键用 `Symbol.for`，不用字符串：宿主会在 `globalThis[插件 id]` 上挂自己的值，
 * 字符串键会被覆盖成非 Map 对象，`registry.get` 随即不是函数，setup 抛错后插件静默失效。
 */
const plugin = {
  id: PLUGIN_ID,
  async setup(ctx: {
    options?: unknown;
    shell: {
      hook: (
        name: "create.before",
        cb: (event: ShellCreateBefore) => void,
      ) => Promise<{ dispose: () => Promise<void> }>;
    };
    tool: {
      hook: (
        name: "execute.before" | "execute.after",
        cb: (event: {
          tool: string;
          id: string;
          input: unknown;
          status?: string;
          result?: ToolResultLike;
        }) => void,
      ) => Promise<{ dispose: () => Promise<void> }>;
    };
  }) {
    const options = resolveOptions(ctx);
    if (options.mode === "off") return;

    // 服务端按 location 各装载一份插件实例（同一进程、同一模块）。
    const registry = getRegistry();
    const locationKey = resolveLocationKey(ctx);
    // 拿不到 location 就用一次性符号做键。
    const key: string | symbol = locationKey ?? Symbol(`${PLUGIN_ID}-instance`);
    // **不要在这里注销上一个实例的钩子**：宿主把 shell 事件路由到哪个实例，
    // 由它自己的加载顺序决定，我们无法可靠判断被注销的那个是不是"正在被路由"的那个。
    // 实测：注销之后该 location 的 shell 事件全部失联（插件静默失效）。
    // 旧实例留着也无害——注入幂等、提示按标记去重，多份实例行为一致。
    // 想彻底清掉旧实例，重启服务即可（宿主会重新装载）。
    const previous = registry.get(key);
    console.log(
      `[${PLUGIN_ID}] loaded, mode=${options.mode}, location=${locationKey ?? "unknown"}` +
        (previous ? ", replaced an older instance" : ""),
    );
    writeDiagnostic(
      `setup mode=${options.mode} location=${locationKey ?? "unknown"} ` +
        `ctxKeys=${Object.keys(ctx as object).join(",")} ` +
        `host.globalThis[${PLUGIN_ID}]=${describeHostValue()}`,
    );

    const calls = new Map<string, string>(); // tool call id -> 原始命令
    const shells = new Map<string, { shell: string; risks: RiskFinding[] }>(); // 原始命令 -> 外壳与风险
    const registrations: Array<{ dispose: () => Promise<void> }> = [];
    // 包一层诊断：宿主直接注销钩子句柄时（热重载路径），这里是唯一的痕迹。
    const track = (registration: { dispose: () => Promise<void> }) => ({
      dispose: async () => {
        writeDiagnostic(`hook disposed location=${locationKey ?? "unknown"}`);
        await registration.dispose();
      },
    });

    registrations.push(
      track(
        await ctx.shell.hook("create.before", (event) => {
      const command = event?.command ?? "";
      const shell = event?.shell ?? "";
      const powershell = isPowerShell(shell) || (options.assumePowerShell && options.platform === "win32");
      writeDiagnostic(
        `shell.create.before location=${locationKey ?? "unknown"} shell=${JSON.stringify(shell)} ` +
          `powershell=${powershell} hasPreamble=${hasPreamble(command)} ` +
          `cmd=${JSON.stringify(command.slice(0, 60))}`,
      );
      if (!powershell) return;

      const risks = findRisks(command);
      shells.set(command, { shell, risks });
      // 命令量大的会话里避免无界增长：只保留最近若干条
      if (shells.size > 100) {
        const oldest = shells.keys().next();
        if (!oldest.done) shells.delete(oldest.value);
      }

      const shouldInject =
        options.platform === "win32" || options.injectOnPosix === true;
      if (!shouldInject) return;

      // 环境变量与命令文本分开处理：命令里已写过前置语句时不再重复插入，
      // 但 Python 的 UTF-8 模式仍要设（否则子进程依旧按控制台代码页输出）。
      if (event.env && typeof event.env === "object") {
        // Python 侧统一走 UTF-8 模式（等价于 python -X utf8）
        if (event.env.PYTHONUTF8 === undefined) event.env.PYTHONUTF8 = "1";
      }
      if (hasPreamble(command)) return;

      event.command = `${options.preamble}\n${command}`;
      writeDiagnostic(
        `shell.injected location=${locationKey ?? "unknown"} cmd=${JSON.stringify(command.slice(0, 60))}`,
      );
        }),
      ),
    );

    registrations.push(
      track(
        await ctx.tool.hook("execute.before", (event) => {
      const tool = event?.tool ?? "";
      if (!isShellTool(tool)) return;
      const input = event?.input as { command?: unknown } | undefined;
      const command = typeof input?.command === "string" ? input.command : "";
      if (!command) return;

      calls.set(event.id, command);

      if (options.mode !== "enforce") return;
      // 执行前拿不到实际外壳（shell 钩子在工具执行后才回调），因此按平台取保守立场：
      // Windows 上 OpenCode 的 shell 工具默认就是 PowerShell；其他平台只拦
      // "native → cmdlet 管道"这种在 bash 下不可能出现的形态。
      const risks = findRisks(command);
      const assumePowerShell = options.platform === "win32" || options.assumePowerShell === true;
      const blocking = assumePowerShell ? risks : risks.filter((f) => f.kind === "pipe");
      if (!blocking.length) return;
      throw new Error(riskError(blocking));
        }),
      ),
    );

    registrations.push(
      track(
        await ctx.tool.hook("execute.after", (event) => {
      const tool = event?.tool ?? "";
      if (!isShellTool(tool)) return;
      const command = calls.get(event.id);
      if (!command) return;
      calls.delete(event.id);

      const info = shells.get(command);
      shells.delete(command);
      if (!info) return;
      if (!isPowerShell(info.shell)) return;
      if (!info.risks.length) return;

      const note = riskNote(info.risks);
      const result = event.result;
      if (!result) return;
      const content = result.content;
      // 同一命令可能被多个 location 实例各处理一次，按标记去重，避免重复提示
      const already = JSON.stringify(content ?? "").includes(`[${PLUGIN_ID}]`);
      if (already) return;
      const parts = Array.isArray(content)
        ? [...content, { type: "text", text: note }]
        : typeof content === "string"
          ? [
              { type: "text", text: content },
              { type: "text", text: note },
            ]
          : [{ type: "text", text: note }];
      event.result = { ...result, content: parts };
        }),
      ),
    );

    // 记下句柄：只作为记录，**不自动注销**（见上面 setup 里的说明）。
    // 需要彻底清理时重启服务即可。
    registry.set(key, {
      dispose: async () => {
        writeDiagnostic(`dispose instance location=${locationKey ?? "unknown"}`);
        for (const registration of registrations) {
          try {
            await registration.dispose();
          } catch {
            /* 句柄已失效时忽略 */
          }
        }
      },
    });  },
};

export default plugin;
