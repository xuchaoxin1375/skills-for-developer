import assert from "node:assert/strict";
import { test } from "node:test";

import plugin, { openSearch } from "../tui.ts";

type Call = Record<string, any>;

function makeContext(options: Record<string, unknown> = {}) {
  const calls: Call[] = [];
  let layer: any;

  const context = {
    options,
    ui: {
      dialog: {
        prompt: async () => "carapace",
        select: async (input: any) => {
          calls.push({ type: "select", input });
          return input.options[0]?.value;
        },
      },
      toast: {
        show: (toast: any) => calls.push({ type: "toast", toast }),
      },
      router: {
        navigate: (destination: any) => calls.push({ type: "navigate", destination }),
      },
    },
    keymap: {
      layer: (factory: () => any) => {
        layer = factory();
      },
    },
    client: {
      session: {
        list: async () => ({ data: [] }),
      },
    },
  };

  return { context, calls, getLayer: () => layer };
}

test("注册 /session-search 斜杠命令", () => {
  const { context, getLayer } = makeContext();
  plugin.setup(context);

  const registered = getLayer();
  assert.equal(registered.mode, "global");
  assert.equal(registered.commands.length, 1);
  assert.equal(registered.commands[0].slash.name, "session-search");
  assert.equal(registered.commands[0].palette, true);
});

test("选中结果后跳转到对应会话", async () => {
  const { context, calls } = makeContext({
    search: async (query: string) => {
      assert.equal(query, "carapace");
      return [
        {
          id: "ses_a",
          title: "A",
          directory: "C:/a",
          updated: 1,
          totalMatches: 2,
          snippet: "命中片段",
        },
        {
          id: "ses_b",
          title: "B",
          directory: "C:/b",
          updated: 2,
          parentID: "ses_a",
        },
      ];
    },
  });

  await openSearch(context);

  const select = calls.find((call) => call.type === "select");
  assert.equal(select.input.options.length, 2);
  assert.equal(select.input.options[1].category, "子会话");
  assert.match(select.input.options[0].description, /2 处命中/);

  const filtered = select.input.search("b", select.input.options);
  assert.equal(filtered.length, 1);
  assert.equal(filtered[0].value, "ses_b");

  const navigate = calls.find((call) => call.type === "navigate");
  assert.deepEqual(navigate.destination, { type: "session", sessionID: "ses_a" });
});

test("取消输入时不打开列表", async () => {
  const { context, calls } = makeContext();
  context.ui.dialog.prompt = async () => undefined;

  await openSearch(context);

  assert.equal(calls.length, 0);
});

test("没有结果时给出提示", async () => {
  const { context, calls } = makeContext({ search: async () => [] });

  await openSearch(context);

  const toast = calls.find((call) => call.type === "toast");
  assert.equal(toast.toast.variant, "warning");
  assert.equal(calls.some((call) => call.type === "select"), false);
});
