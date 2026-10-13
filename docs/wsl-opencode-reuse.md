## WSL 复用 Windows 侧 OpenCode 配置

WSL 与 Windows 是两套彼此独立的 OpenCode 实例：配置目录、数据目录互不相通，但 Windows 用户目录在 WSL 中可经 `/mnt/c/Users/<用户>` 直接读取。本文让 WSL 一次补齐 Windows 侧完整配置（含模型配置）。skill 分发不走本文，仍由仓库链接脚本负责（见 README「部署清单」）。

顺序：先完成部署清单步骤 1–2（skill 链接、`AGENTS.md`、`cli.json`），再做本文步骤，最后回清单做校验。本文只处理模型相关的三件套，不重复部署清单已对齐项。

### 完整清单：什么算“完整”

| 类别 | 文件与关键字段 | WSL 侧获取方式 |
| --- | --- | --- |
| 默认模型与供应商目录（模型配置核心） | `opencode.json`：`model`、`providers.<providerID>.models`（含各模型 `limit`）、`mcp`（如有） | 本文步骤 1：整份复制，平台相关字段逐项核对 |
| 密钥与代理 | `service.json` 的 `env` 块：各 `*_API_KEY`、`HTTPS_PROXY` / `HTTP_PROXY` / `NO_PROXY` | 本文步骤 2：只合并 `env`，保留 WSL 本机的 `password` / `port` |
| 登录态 | 数据目录 `auth.json` 内各条目 | 本文步骤 3：缺失条目重登或按条目补齐，不复制整个数据目录 |
| TUI 偏好 | `cli.json` | 部署清单步骤 1（`--apply-recommended-cli`），不从 Windows 复制 |
| 全局 `AGENTS.md` | `~/.config/opencode/AGENTS.md` | 部署清单步骤 2，不从 Windows 复制 |
| skill 实体 | 各 harness `skills/` 链接 | 链接脚本，不从 Windows 复制 |
| 数据目录（`opencode.db`、会话、快照、日志） | 各自系统独占 | **不复用**：内含本机绝对路径、锁文件与跨平台差异 |
| `node_modules`（插件依赖） | 各自安装 | **不复用**：原生二进制不跨平台，由本机 `opencode` 自行安装 |

“完整”即前三行对齐：`model` 与供应商、模型目录一致，`env` 键齐全，登录态缺失项补齐。后五行的获取方式不变，本文不再重复。

目录对照：

| 用途 | Windows | WSL |
| --- | --- | --- |
| 配置 | `%USERPROFILE%\.config\opencode` | `~/.config/opencode` |
| 数据 | `%USERPROFILE%\.local\share\opencode` | `~/.local/share/opencode` |

### 方式选型

1. **一次性复制/合并（推荐）**：把 Windows 侧配置取到 WSL 侧，两份此后各自演化。适合密钥与 providers 这类低频变更项，无跨文件系统耦合，出问题可各自回退。其中 `opencode.json` 整份复制，`service.json` 只合并 `env`（见步骤 2，不覆盖本机 `password` / `port`）。
2. **符号链接到 `/mnt/c`**：活同步，但 WSL 读写 Windows 盘（DrvFs）的性能与锁行为受限，两侧同时运行 OpenCode 并改写同一文件有损坏风险；仅适合纯只读参考，`service.json`、`auth.json` 一律不采用。
3. **按 skill 重配**：不依赖 Windows 侧文件，按 `opencode-provider-config` 重新拉取模型列表、写 providers、设置服务环境变量。适合借迁移清理配置、或两侧需要不同模型方案的场景。

### 前置检查

```bash
WIN_CFG=/mnt/c/Users/<Windows用户名>/.config/opencode
WIN_DATA=/mnt/c/Users/<Windows用户名>/.local/share/opencode
DST="$HOME/.config/opencode"
test -f "$WIN_CFG/opencode.json" || { echo "未找到 $WIN_CFG/opencode.json，先确认 Windows 用户名与 /mnt/c 可读" >&2; exit 1; }
mkdir -p "$DST"
```

`<Windows用户名>` 按实际替换（如 `ls /mnt/c/Users` 所见）。部署清单步骤 1–2 应已完成；若 `~/.config/opencode/skills`、`AGENTS.md`、`cli.json` 还没对齐，先回清单处理。

### 一次性复用步骤（推荐）

步骤 1——`opencode.json` 整份复制（含默认模型与模型目录）：

```bash
[ -f "$DST/opencode.json" ] && cp -p "$DST/opencode.json" "$DST/opencode.json.bak-$(date +%Y%m%d-%H%M%S)"
cp "$WIN_CFG/opencode.json" "$DST/opencode.json"
# 同目录若残留裸 `opencode.jsonc`（仅含 $schema），与新复制的 json 并存会造成两份配置：仅当确认无实质内容后删除
python3 -X utf8 - "$DST/opencode.jsonc" <<'PY' 2>/dev/null
import json, sys
try:
    d = json.load(open(sys.argv[1], encoding="utf-8"))
except (FileNotFoundError, ValueError):
    sys.exit(1)
sys.exit(0 if set(d.keys()) == {"$schema"} else 1)
PY
[ $? -eq 0 ] && rm "$DST/opencode.jsonc" || true
```

复制后逐项核对 `opencode.json` 内与平台相关的字段（路径、命令、文件位置等），不假定原样可用；两侧仓库路径本就可以不同。`model` 与 `providers` 原样保留，这就是模型配置本体。

步骤 2——`service.json` 只合并 `env`（保留本机 `password` / `port`）：

```bash
[ -f "$DST/service.json" ] && cp -p "$DST/service.json" "$DST/service.json.bak-$(date +%Y%m%d-%H%M%S)"
python3 -X utf8 - "$WIN_CFG/service.json" "$DST/service.json" <<'PY'
import json, sys
win = json.load(open(sys.argv[1], encoding="utf-8"))
try:
    dst = json.load(open(sys.argv[2], encoding="utf-8"))
except FileNotFoundError:
    dst = {}
win_env = win.get("env") or {}
dst_env = dst.get("env") or {}
merged = dict(dst_env)
merged.update(win_env)  # 同名键以 Windows 侧为准，WSL 独有键保留
dst["env"] = merged
# password / port 等其他顶层键保留 WSL 本机值，不从 Windows 覆盖
json.dump(dst, open(sys.argv[2], "w", encoding="utf-8"), ensure_ascii=False, indent=2)
PY
chmod 600 "$DST/service.json"
```

整份 `cp service.json` 会覆盖本机 `password` / `port`，不要这样做。合并脚本只读写文件、不打印变量值。

代理注意：`env` 中代理若写 `127.0.0.1:<port>`，在 WSL 内指向 WSL 自身，未必可达 Windows 侧代理；出网前按 `network-access` 核验实际出口，必要时在 WSL 单独配置代理。

步骤 3——`auth.json` 缺失条目补齐（二选一，推荐重登）：

```bash
WIN_AUTH="$WIN_DATA/auth.json"
DST_AUTH="$HOME/.local/share/opencode/auth.json"
```

- 首选 `opencode auth login` 在 WSL 侧重登缺失的登录态，不跨机复制令牌。
- 确实无法重登时才从 Windows 侧取对应条目：先备份 WSL 侧 `auth.json`，合并缺失条目（或经 `auth export` / `auth import` 中转），合并后 `chmod 600`。只动 `auth.json` 单文件，不复制 `opencode.db` 及整个数据目录。

步骤 4——平台差异核对：`opencode.json` 内的路径、命令按 WSL 环境逐项确认；仓库路径两侧可以不同，不强求一致。

### 密钥红线

- `service.json`、`auth.json` 含明文密钥与令牌：只在本机文件系统内复制，**不入 git 仓库、不写进文档、不作为示例输出**；复制/合并后确认权限为 `600`。
- 合并与核验命令只输出变量名、条目名，不输出变量值；`service get env` 原样输出含密钥，展示前先打码或改用本文的只列键名片段。
- 本仓库 `config/` 只收非密配置（`cli.json`、`global-AGENTS.md`）。providers 与密钥的配置方法沉淀在 `opencode-provider-config`，本机密钥与具体端点不写进任何 skill 正文。

### 验证：到配置一致为止，不测活

```bash
opencode reload      # 或重启 TUI；重扫异步，等约 5 秒再查，紧跟查询可能读到中间态
sleep 5
# 以下四项同一次调用一次跑完；models 单次约数秒是最贵一项，落盘一次、反复 grep，不重复拉
opencode models > "${TMPDIR:-/tmp}/opencode-models.txt"
grep <providerID> "${TMPDIR:-/tmp}/opencode-models.txt"   # 只看列表出现，不做真实调用
opencode auth list   # 只看条目是否补齐
# 只列键名，不输出值
opencode service get env | python3 -X utf8 -c "import json,sys; print(sorted(json.load(sys.stdin).keys()))"
# 默认模型与供应商 ID 与 Windows 侧一致（只比 ID，不贴端点与密钥）
python3 -X utf8 -c "import json; d=json.load(open('$HOME/.config/opencode/opencode.json',encoding='utf-8')); print(d.get('model'), sorted(d.get('providers',{}).keys()))"
```

核对一律走后台服务，不加 `--standalone`（另起私有服务更慢，且结果不在后台服务上，会误导）。

skill 计数与真源对照见 README「结构校验」末尾片段：`missing` 须为 `none`、`in-source` 为满额。

复用完成即结束，**默认不主动测试模型可用性**：不跑 `opencode run`，不直接打 `/v1/chat/completions`，不逐一遍历分组内模型测速。`opencode-provider-config` 第 5 步的端到端验证只适用于新建/改动供应商，不适用于本次复用。只有用户明确要求测活时，才按该 skill 的收敛规则执行（只测要用的模型，默认限时 10 秒）。

回退：覆盖前均已备份（`*.bak-<时间戳>`），出问题把备份拷回并 `opencode reload` 即可。

### 本机实测差距（2026-10-13，仅作参照）

- 未复用前 WSL `opencode.jsonc` 只剩 `$schema` 无 providers，`opencode models` 不含 Windows 侧第三方 provider；`service.json` 只有本机 `password` 与 `port`，无任何密钥或代理 env。
- 整份复制 `service.json` 会丢 WSL 本机 `port` 并覆盖 `password`，故本文改为只合并 `env`。
- WSL `auth.json` 曾缺 Windows 侧部分登录条目，需按步骤 3 单独补齐；`opencode.db` 等数据目录始终不复制。
- 全局 `AGENTS.md`、`cli.json` 与全部真源 skill 链接已随部署清单对齐，无需再从 Windows 复制。
