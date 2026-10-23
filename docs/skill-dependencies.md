# Skill 依赖声明与检查

各 skill 的外部依赖写在 `skills/<name>/dependencies.json`，供仓库脚本直接扫描；脚本不读 `SKILL.md` 正文猜依赖。

## 何时声明

- skill 的核心流程或随 skill 分发的脚本，需要某个运行时、命令、浏览器或环境变量才能运行时。
- 纯提示、规范或方法类 skill 没有固定外部依赖，不建文件。
- 目标项目自身的框架、数据库、测试栈不在 skill 依赖里声明；用 `resource-inventory/scripts/inventory.py --project <目录>` 查。
- `package.json` 仍负责 Node 包安装；`dependencies.json` 只回答“这台机器有没有可运行的前提”，两者可以同时存在。
- `config/recommended-skills.txt` 决定链接脚本要安装哪些包/命令；本文件只声明运行前提，两者职责不同，可以重叠（如 htmlmini）。

## 文件格式

最小示例：

```json
{
  "schemaVersion": 1,
  "requirements": [
    {
      "id": "python",
      "kind": "runtime",
      "name": "python",
      "minVersion": "3.9",
      "required": true,
      "hint": "预检脚本需要 Python 3.9+"
    },
    {
      "id": "renderer",
      "required": true,
      "alternatives": [
        { "kind": "command", "name": "mmdc" },
        { "kind": "browser" }
      ],
      "hint": "mmdc 或本机浏览器；都不可用时联网走 kroki"
    }
  ]
}
```

字段：

| 字段 | 规则 |
|---|---|
| `schemaVersion` | 固定 `1` |
| `requirements` | 非空数组，每项一个依赖或一组替代 |
| `id` | 必填，kebab-case，同一文件内唯一 |
| `required` | 可选，默认 `true`；`false` 表示可选能力，缺失只警告 |
| `kind` | `runtime` / `command` / `browser` / `env` / `network` |
| `name` | `runtime`、`command`、`env` 必填；`browser`、`network` 禁止 |
| `minVersion` | 仅 `runtime`/`command`，点分数字；版本无法解析时按未知处理 |
| `url` | 仅 `network`，记录参考地址，不联网探测 |
| `alternatives` | 数组，至少一个；满足任一项即可，选项内不能再嵌套 |
| `hint` | 缺失时给出的下一步，不写自动安装命令 |

`kind` 的含义：

| kind | 判据 |
|---|---|
| `runtime` | PATH 上的运行时（node/python/pnpm 等），有 `minVersion` 时比较版本 |
| `command` | PATH 上可执行命令，只查存在性 |
| `browser` | 任意一个可用 Chrome/Edge/Chromium |
| `env` | 环境变量非空 |
| `network` | 需要联网的能力；默认只报 `unknown`，不发起请求 |

## 检查

```bash
python -X utf8 scripts/check-skill-deps.py
python -X utf8 scripts/check-skill-deps.py --json
python -X utf8 scripts/check-skill-deps.py --skill mermaid-render-fix,htmlmini
python -X utf8 scripts/check-skill-deps.py --strict
```

检查复用 `skills/resource-inventory/scripts/inventory.py --json` 的运行时与浏览器结果，不重复检测规则；不安装依赖、不联网。`network` 项与无法解析的版本会报 `unknown`，需要联网或换环境判断时按 `network-access` / `resource-inventory` 处理。

退出码：`0` 必需依赖满足；`1` 有缺失或版本不符（`--strict` 下 `unknown` 与可选缺失也算）；`2` 声明或探测本身失败。

## 维护

- 新增或修改依赖时同步更新 `dependencies.json` 与 `hint`，不要只改正文；正文与声明各写一次时，以 `dependencies.json` 为机器检查口径。
- `scripts/check-skills.py` 会校验 JSON 结构与字段；格式错误计入错误，含 `package.json` 却缺声明时给出提醒。
- 检查失败不等于 skill 不可用：可选依赖缺失只警告；准备完整环境时才用 `--strict`。
- 链接脚本只负责 `package.json` 依赖安装和命令 shim；不读取本文件，也不自动安装。
