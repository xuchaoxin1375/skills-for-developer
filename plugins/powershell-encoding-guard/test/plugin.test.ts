/**
 * 插件逻辑测试：node --test
 * 只用标准库，不依赖 OpenCode 运行时；钩子用假 ctx 驱动。
 *
 * 注意：Node 24 下 `node --test test/` 会把目录当入口模块解析并报 MODULE_NOT_FOUND，
 * 只能不带参数跑（自动发现）或直接指定测试文件。
 */
import test from "node:test";
import assert from "node:assert/strict";

import plugin, {
  DEFAULT_PREAMBLE,
  PLUGIN_ID,
  buildPreamble,
  findRisks,
  hasPreamble,
  isPowerShell,
  resolveLocationKey,
  riskNote,
} from "../index.ts";

type AnyHook = (event: any) => void;

function createCtx(options: Record<string, unknown> = {}) {
  const hooks: { shell: Record<string, AnyHook>; tool: Record<string, AnyHook> } = {
    shell: {},
    tool: {},
  };
  const registration = { dispose: async () => {} };
  const ctx = {
    options,
    // 与宿主一致：location 是会话所在目录，插件用它区分实例
    location: { directory: "C:/repo" },
    shell: {
      hook(name: string, cb: AnyHook) {
        hooks.shell[name] = cb;
        return Promise.resolve(registration);
      },
    },
    tool: {
      hook(name: string, cb: AnyHook) {
        hooks.tool[name] = cb;
        return Promise.resolve(registration);
      },
    },
  };
  return { ctx, hooks };
}

async function setup(options: Record<string, unknown> = {}) {
  const { ctx, hooks } = createCtx(options);
  await plugin.setup(ctx as never);
  return hooks;
}

function shellEvent(command: string, shell = "pwsh") {
  return {
    command,
    cwd: "C:/repo",
    timeout: 1000,
    shell,
    env: {} as Record<string, string | undefined>,
  };
}

test("isPowerShell 识别 pwsh / powershell / 完整路径", async () => {
  assert.equal(isPowerShell("pwsh"), true);
  assert.equal(isPowerShell("powershell.exe"), true);
  assert.equal(isPowerShell("C:/Program Files/PowerShell/7/pwsh.exe"), true);
  assert.equal(isPowerShell("C:/Program Files/Git/bin/bash.exe"), false);
  assert.equal(isPowerShell(""), false);
});

test("前置语句幂等：已有则不重复注入", async () => {
  assert.equal(hasPreamble(DEFAULT_PREAMBLE), true);
  const once = buildPreamble("Get-Content -LiteralPath 'a.md'");
  assert.ok(once.startsWith(DEFAULT_PREAMBLE));
  assert.equal(buildPreamble(once), once);
});

test("Windows 的 PowerShell 调用自动前置编码语句与 PYTHONUTF8", async () => {
  const hooks = await setup({ platform: "win32" });
  const event = shellEvent("Get-Content -LiteralPath 'a.md'");
  hooks.shell["create.before"](event);
  assert.ok(event.command.startsWith(DEFAULT_PREAMBLE));
  assert.ok(event.command.endsWith("Get-Content -LiteralPath 'a.md'"));
  assert.equal(event.env.PYTHONUTF8, "1");
});

test("已含前置语句的命令不被二次注入，但仍补 PYTHONUTF8", async () => {
  const hooks = await setup({ platform: "win32" });
  const event = shellEvent(`${DEFAULT_PREAMBLE}\nGet-Content 'a.md'`);
  hooks.shell["create.before"](event);
  assert.equal(event.command, `${DEFAULT_PREAMBLE}\nGet-Content 'a.md'`);
  assert.equal(event.env.PYTHONUTF8, "1");
});

test("非 PowerShell 外壳不注入", async () => {
  const hooks = await setup({ platform: "win32" });
  const event = shellEvent("git status", "C:/Program Files/Git/bin/bash.exe");
  hooks.shell["create.before"](event);
  assert.equal(event.command, "git status");
});

test("非 Windows 平台默认不注入", async () => {
  const hooks = await setup({ platform: "linux" });
  const event = shellEvent("Get-Content 'a.md'");
  hooks.shell["create.before"](event);
  assert.equal(event.command, "Get-Content 'a.md'");
});

test("高危形态识别：native→cmdlet 管道与 stdout 重定向", async () => {
  const pipe = findRisks("git log | Select-String 'fix'");
  assert.equal(pipe.length, 1);
  assert.equal(pipe[0].kind, "pipe");

  const redirect = findRisks("git log > out.txt");
  assert.equal(redirect.length, 1);
  assert.equal(redirect[0].kind, "redirect");

  const stderr = findRisks("git log 2>&1");
  assert.equal(stderr.length, 0);
});

test("不误报：cmdlet 之间的管道、native→native 管道", async () => {
  assert.equal(findRisks("Get-Content -LiteralPath 'a.md' | Select-String 'x'").length, 0);
  assert.equal(findRisks("git log | rg 'fix'").length, 0);
});

test("不误报：字符串里的管道与重定向符号", async () => {
  assert.equal(findRisks("python -c \"print('a|b')\" | Out-String").length, 1);
  assert.equal(findRisks("rg 'a>b' --files").length, 0);
});

test("native→native 不误报：findstr / fc 属于原生清单", async () => {
  assert.equal(findRisks("git log | findstr fix").length, 0);
  assert.equal(findRisks("git log | fc a b").length, 0);
});

test("清单外的原生 exe 保守按风险处理（提示方向偏多，不漏报）", async () => {
  assert.equal(findRisks("git log | certutil x").length, 1);
});

test("stdout 重定向识别：1> 与 &> 算高危，2> 与 2>&1 不算", async () => {
  assert.equal(findRisks("git log 1> out.txt").length, 1);
  assert.equal(findRisks("git log &> out.txt").length, 1);
  assert.equal(findRisks("git log 2> err.txt").length, 0);
  assert.equal(findRisks("git log 2>&1").length, 0);
});

test("PowerShell 条件运算符 || 不算数据管道", async () => {
  assert.equal(findRisks("git log || echo failed").length, 0);
});

test("warn 模式：默认不往工具结果追加提示，只记诊断日志", async () => {
  const hooks = await setup({ platform: "win32", mode: "warn" });
  const command = "git log | Select-String 'fix'";

  const before = { tool: "bash", id: "call-1", input: { command } };
  hooks.tool["execute.before"](before);

  const shell = shellEvent(command);
  hooks.shell["create.before"](shell);

  const after: any = {
    tool: "bash",
    id: "call-1",
    input: { command },
    status: "completed",
    result: { content: [{ type: "text", text: "log output" }] },
  };
  hooks.tool["execute.after"](after);

  const parts = after.result.content as Array<{ type: string; text?: string }>;
  assert.equal(parts.length, 1);
  assert.equal(parts[0].text, "log output");
});

test("appendNote 打开时才把风险提示追加到工具结果", async () => {
  const hooks = await setup({ platform: "win32", mode: "warn", appendNote: true });
  const command = "git log | Select-String 'fix'";

  hooks.tool["execute.before"]({ tool: "bash", id: "call-1b", input: { command } });
  hooks.shell["create.before"](shellEvent(command));

  const after: any = {
    tool: "bash",
    id: "call-1b",
    input: { command },
    status: "completed",
    result: { content: [{ type: "text", text: "log output" }] },
  };
  hooks.tool["execute.after"](after);

  const parts = after.result.content as Array<{ type: string; text?: string }>;
  assert.equal(parts.length, 2);
  assert.equal(parts[0].text, "log output");
  assert.match(parts[1].text ?? "", /powershell-encoding-guard/);
});

test("warn 模式：无风险时不追加提示", async () => {
  const hooks = await setup({ platform: "win32", mode: "warn" });
  const command = "git status";

  hooks.tool["execute.before"]({ tool: "bash", id: "call-2", input: { command } });
  hooks.shell["create.before"](shellEvent(command));
  const after: any = {
    tool: "bash",
    id: "call-2",
    input: { command },
    status: "completed",
    result: { content: [{ type: "text", text: "clean" }] },
  };
  hooks.tool["execute.after"](after);

  const parts = after.result.content as Array<{ type: string; text?: string }>;
  assert.equal(parts.length, 1);
});

test("enforce 模式：高危形态直接拒绝执行", async () => {
  const hooks = await setup({ platform: "win32", mode: "enforce" });
  assert.throws(
    () =>
      hooks.tool["execute.before"]({
        tool: "bash",
        id: "call-3",
        input: { command: "git log > out.txt" },
      }),
    /拒绝执行/,
  );
});

test("enforce 模式：低风险命令放行", async () => {
  const hooks = await setup({ platform: "win32", mode: "enforce" });
  hooks.tool["execute.before"]({
    tool: "bash",
    id: "call-4",
    input: { command: "git status" },
  });
});

test("off 模式：不注册任何钩子", async () => {
  const hooks = await setup({ platform: "win32", mode: "off" });
  assert.equal(Object.keys(hooks.shell).length, 0);
  assert.equal(Object.keys(hooks.tool).length, 0);
});

test("风险提示文案给出可执行替代方案", async () => {
  const note = riskNote([{ kind: "pipe", detail: "git | Select-String" }]);
  assert.match(note, /--out|字节闸门/);
});

test("宿主占用 globalThis[插件 id] 时仍能装载（注册表用 Symbol 键）", async () => {
  // 回归用例：早期实现用字符串键当注册表，宿主在同名键上挂值后
  // registry.get 不是函数，setup 抛错，插件静默失效（宿主日志里是 failed to load plugin）。
  (globalThis as Record<string, unknown>)[PLUGIN_ID] = { host: "value" };
  try {
    const hooks = await setup({ platform: "win32" });
    const event = shellEvent("Get-Content -LiteralPath 'a.md'");
    hooks.shell["create.before"](event);
    assert.ok(event.command.startsWith(DEFAULT_PREAMBLE));
    assert.equal(event.env.PYTHONUTF8, "1");
  } finally {
    delete (globalThis as Record<string, unknown>)[PLUGIN_ID];
  }
});

test("location 标识解析：多种上下文形态都能取到，取不到时返回 null", async () => {
  assert.equal(resolveLocationKey({ location: { directory: "C:/repo" } }), "C:/repo");
  assert.equal(
    resolveLocationKey({ location: { project: { canonical: "C:/repo.git" } } }),
    "C:/repo.git",
  );
  assert.equal(resolveLocationKey({ project: { canonical: "C:/repo.git" } }), "C:/repo.git");
  assert.equal(resolveLocationKey({ directory: "C:/repo" }), "C:/repo");
  assert.equal(resolveLocationKey({}), null);
});

test("同一 location 重复装载时不注销上一个实例的钩子", async () => {
  // 回归用例：旧实现会在新实例 setup 时注销同 location 旧实例的钩子，
  // 而宿主把 shell 事件路由到哪份实例由它自己的加载顺序决定——注销掉的
  // 很可能正是被路由的那份，结果该 location 的 shell 事件全部失联。
  const first = await setup({ platform: "win32" });
  const firstEvent = shellEvent("Get-Content -LiteralPath 'a.md'");
  first.shell["create.before"](firstEvent);
  assert.ok(firstEvent.command.startsWith(DEFAULT_PREAMBLE));

  const second = await setup({ platform: "win32" });
  const secondEvent = shellEvent("Get-Content -LiteralPath 'b.md'");
  second.shell["create.before"](secondEvent);
  assert.ok(secondEvent.command.startsWith(DEFAULT_PREAMBLE));

  // 第一个实例仍然可用
  const thirdEvent = shellEvent("Get-Content -LiteralPath 'c.md'");
  first.shell["create.before"](thirdEvent);
  assert.ok(thirdEvent.command.startsWith(DEFAULT_PREAMBLE));
});
