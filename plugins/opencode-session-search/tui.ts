/**
 * 跨项目会话检索（OpenCode TUI 插件）
 *
 * 行为：
 * - 在命令面板或输入 `/session-search` 时打开一个关键词输入框；
 * - 用 `session-search` CLI 跨全部项目检索标题与正文（留空则列最近会话）；
 * - 结果放进可继续过滤的选择列表，选中后直接跳转到该会话。
 *
 * 全程不提交提示词、不调用模型。CLI 不可用时退化为服务端标题检索。
 */
import { execFile } from "node:child_process";
import { appendFileSync, existsSync, readFileSync } from "node:fs";
import { homedir, tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { promisify } from "node:util";

const execFileAsync = promisify(execFile);

type SessionResult = {
  id: string;
  title?: string;
  directory?: string;
  updated?: number;
  parentID?: string;
  totalMatches?: number;
  snippet?: string;
};

type ClientSession = {
  id: string;
  title?: string;
  parentID?: string;
  time?: { updated?: number };
  location?: { directory?: string };
};

type SelectOption = {
  title: string;
  value: string;
  description?: string;
  category?: string;
};

type PluginContext = {
  options?: Record<string, unknown>;
  ui: {
    dialog: {
      prompt(options: {
        title: string;
        description?: string;
        placeholder?: string;
        value?: string;
      }): Promise<string | undefined>;
      select(options: {
        title: string;
        placeholder?: string;
        options: readonly SelectOption[];
        search?: (query: string, options: readonly SelectOption[]) => readonly SelectOption[];
      }): Promise<string | undefined>;
    };
    toast: {
      show(options: { message: string; variant?: "info" | "success" | "warning" | "error" }): void;
    };
    router: {
      navigate(destination: { type: "session"; sessionID: string }): void;
    };
  };
  keymap: {
    layer(factory: () => {
      mode?: string;
      priority?: number;
      commands?: readonly {
        id: string;
        title?: string;
        group?: string;
        slash?: { name: string; aliases?: string[] };
        palette?: true;
        suggested?: boolean;
        run: (input?: string) => void | Promise<void>;
      }[];
    }): void;
  };
  client: {
    session: {
      list(input?: { limit?: number; order?: "asc" | "desc" }): Promise<{ data: ClientSession[] }>;
    };
  };
};

export default {
  id: "opencode.session-search",
  setup(context: PluginContext): void {
    diagnostic(`tui setup runtime=${runtime()}`);
    context.keymap.layer(() => ({
      mode: "global",
      priority: 20,
      commands: [
        {
          id: "opencode.session-search",
          title: "搜索历史会话（跨项目）",
          group: "Session",
          slash: { name: "session-search" },
          palette: true,
          suggested: true,
          run: () => openSearch(context),
        },
      ],
    }));
  },
};

export async function openSearch(context: PluginContext): Promise<void> {
  const query = await context.ui.dialog.prompt({
    title: "搜索历史会话",
    description: "跨全部项目；留空浏览最近会话",
    placeholder: "关键词，多个词用空格分隔",
  });
  if (query === undefined) return;

  const trimmed = query.trim();
  let results: SessionResult[];
  try {
    results = await search(context, trimmed);
    diagnostic(`query=${JSON.stringify(trimmed)} results=${results.length} runtime=${runtime()}`);
  } catch (error) {
    diagnostic(`query=${JSON.stringify(trimmed)} error=${errorMessage(error)} runtime=${runtime()}`);
    context.ui.toast.show({
      message: `会话检索失败：${errorMessage(error)}`,
      variant: "error",
    });
    return;
  }

  if (results.length === 0) {
    context.ui.toast.show({ message: "没有匹配的会话", variant: "warning" });
    return;
  }

  const selected = await context.ui.dialog.select({
    title: trimmed ? `会话：${trimmed}` : "最近会话",
    placeholder: "继续输入以过滤标题、目录或片段",
    options: results.map(toOption),
    search: (text, options) => {
      const needle = text.trim().toLowerCase();
      if (!needle) return options;
      return options.filter((option) =>
        `${option.title}\n${option.description ?? ""}`.toLowerCase().includes(needle));
    },
  });

  if (selected) context.ui.router.navigate({ type: "session", sessionID: selected });
}

async function search(context: PluginContext, query: string): Promise<SessionResult[]> {
  const injected = context.options?.search;
  if (typeof injected === "function") {
    return (injected as (value: string) => Promise<SessionResult[]>)(query);
  }

  const script = resolveSearchScript();
  if (script) {
    try {
      return await runSessionSearch(script, query);
    } catch {
      // CLI 失败时退回服务端标题检索，至少还能按标题/目录找。
    }
  }

  return searchViaClient(context, query);
}

function resolveSearchScript(): string | undefined {
  const fromShim = readShimScript();
  if (fromShim) return fromShim;

  const here = dirname(fileURLToPath(import.meta.url));
  const candidate = resolve(here, "..", "..", "skills", "opencode-session-data", "scripts", "session-search.js");
  return existsSync(candidate) ? candidate : undefined;
}

function readShimScript(): string | undefined {
  const shim = process.platform === "win32"
    ? join(homedir(), ".local", "bin", "session-search.cmd")
    : join(homedir(), ".local", "bin", "session-search");
  try {
    const content = readFileSync(shim, "utf8");
    const match = content.match(/["']([^"']*session-search\.js)["']/);
    return match && existsSync(match[1]) ? match[1] : undefined;
  } catch {
    return undefined;
  }
}

async function runSessionSearch(script: string, query: string): Promise<SessionResult[]> {
  const terms = query.split(/\s+/).filter(Boolean);
  const args = [script, ...terms, "--json", "--limit", "50"];
  const node = process.env.OPENCODE_NODE || "node";
  const result = await execFileAsync(node, args, {
    encoding: "utf8",
    timeout: 15000,
    windowsHide: true,
    maxBuffer: 20 * 1024 * 1024,
  });

  const parsed = JSON.parse(result.stdout) as { results?: SessionResult[] };
  if (!Array.isArray(parsed.results)) throw new Error("session-search 返回格式不正确");
  return parsed.results;
}

async function searchViaClient(context: PluginContext, query: string): Promise<SessionResult[]> {
  const response = await context.client.session.list({ limit: 200, order: "desc" });
  const sessions = Array.isArray(response.data) ? response.data : [];
  const terms = query.toLowerCase().split(/\s+/).filter(Boolean);

  return sessions
    .filter((session) => {
      if (terms.length === 0) return true;
      const haystack = `${session.title ?? ""}\n${session.location?.directory ?? ""}`.toLowerCase();
      return terms.every((term) => haystack.includes(term));
    })
    .map((session) => ({
      id: session.id,
      title: session.title,
      directory: session.location?.directory,
      updated: session.time?.updated,
      parentID: session.parentID,
    }));
}

function toOption(result: SessionResult): SelectOption {
  const time = result.updated ? formatTime(result.updated) : "未知时间";
  const directory = result.directory || "(未知目录)";
  const hits = result.totalMatches ? ` · ${result.totalMatches} 处命中` : "";
  const snippet = result.snippet ? ` · ${result.snippet.slice(0, 80)}` : "";

  return {
    title: result.title || "(无标题)",
    value: result.id,
    description: `${time} · ${directory}${hits}${snippet}`,
    category: result.parentID ? "子会话" : undefined,
  };
}

function formatTime(milliseconds: number): string {
  const date = new Date(milliseconds);
  if (Number.isNaN(date.getTime())) return "未知时间";
  const pad = (value: number) => String(value).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ` +
    `${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

/** 装载失败时界面无提示；写一行到临时目录，供排查“插件没生效”。 */
function diagnostic(message: string): void {
  try {
    appendFileSync(
      join(tmpdir(), "opencode-session-search.log"),
      `${new Date().toISOString()} ${message}\n`,
    );
  } catch {
    // 诊断失败不能影响检索本身。
  }
}

function runtime(): string {
  const versions = process.versions as Record<string, string | undefined>;
  return versions.bun ? `bun ${versions.bun}` : `node ${process.version}`;
}
