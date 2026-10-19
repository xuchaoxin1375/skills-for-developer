> 本文件是 `scripting-best-practices` 的按需参考，只在处理对应语言时读取。通用约束、工作流程与验证协议仍以 [SKILL.md](../SKILL.md) 为准。

# Node.js (CLI 工具) 规范

单文件或小目录的 Node CLI（`.mjs` 优先 ESM），与 MCP server、构建脚本同理。

## 头部与入口

```js
#!/usr/bin/env node
// tool.mjs - 一句话功能描述，用法见 --help。
```

## 脚本骨架（标准库优先）

```js
#!/usr/bin/env node
import { readFile, writeFile } from 'node:fs/promises';

const HELP = `tool - 一句话功能描述

USAGE
  tool <必填> [选项]
OPTIONS
  --mode <name>  取值说明
  -o, --output <f>  写文件而非 stdout
  -h, --help
`;

const args = parseArgs(process.argv.slice(2)); // 支持 --opt value 与 --opt=value
validateOrExit(args); // 非法输入：stderr 提示 + exit 2，先于业务执行

try {
  const out = await run(args);
  process.stdout.write(out + '\n');
} catch (err) {
  console.error(`tool: ${err.message}`);
  process.exit(1);
}
```

设计要点：参数解析与业务分离（`parseArgs` 可单测）；`--help` 自带完整用法；
退出码固定含义——`0` 成功、`1` 运行失败、`2` 用法错误；错误带工具名前缀走 stderr，stdout 保持可管道化。

## 强制规则

| 规则 | 说明 |
| ---- | ---- |
| **退出码三档** | `0` 成功、`1` 运行失败、`2` 用法错误；用量校验先于业务执行 |
| **错误走 stderr** | `console.error('tool: ...')`，stdout 只放可管道化的结果 |
| **子进程数组传参** | `spawn/execFile` 用参数数组，不拼接 shell 字符串；Windows 下用户触发的子进程加 `windowsHide` |
| **解码显式** | 文件与子进程字节显式解码；中文 Windows 按“本地工具：文件遍历与子进程”第 3 条双解码 |
| **避免全局可变状态** | 配置经函数参数传递；可复用逻辑导出函数而非仅 CLI 可用 |
| **依赖锁定** | 有第三方依赖则 `package.json` + lock 文件进版本控制；无依赖优先标准库 |

## 质量工具

- **`node --check <script>`**：语法检查，改完必跑。
- **既有测试套件**：有 smoke/可靠性测试的仓库按其命令全跑（如 `pnpm test`）；无架子时至少覆盖正常路径与一个异常路径，断言退出码与输出。

---

## 反模式自检清单

- [ ] 非法参数是否 exit 2 且先于业务执行？
- [ ] 错误是否走 stderr（带工具名前缀），stdout 是否保持可管道化？
- [ ] 退出码是否为 0/1/2 三档含义？
- [ ] 临时文件是否 `try/finally` 清理？
- [ ] 子进程是否数组传参、无拼接，Windows 下是否 `windowsHide`？
- [ ] 文本解码是否显式（非 ASCII 必测）？
- [ ] 是否跑过 `node --check` 与正/异常路径测试？
