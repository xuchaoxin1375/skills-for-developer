> 本文件是 `scripting-best-practices` 的按需参考，只在处理对应语言时读取。通用约束、工作流程与验证协议仍以 [SKILL.md](../SKILL.md) 为准。

# Shell (Bash) 规范

## 头部与严格模式

每个 Bash 脚本**必须**以以下两行开头：

```bash
#!/usr/bin/env bash
set -euo pipefail
```

| 选项 | 作用 | 说明 |
| ---- | ---- | ---- |
| `set -e` | 命令返回非零退出码时**立即终止** | 避免错误被静默忽略 |
| `set -u` | 引用**未定义变量**时报错并终止 | 杜绝拼错变量名带来的隐蔽 bug |
| `set -o pipefail` | 管道中**任一命令**失败则整条管道失败 | 默认仅看最后一条命令的退出码 |

**关键辨析**：`bash` vs `sh`。需要数组、`[[ ]]`、`local` 等 Bash 特性时用 `#!/usr/bin/env bash`（经 `PATH` 查找，兼容 Homebrew 等非常规安装路径）；
追求最大可移植且只用 POSIX 语法时才用 `#!/bin/sh`。在多数发行版上 `/bin/sh` 指向 `dash`，Bash 专有语法行为会不同，因此**依赖 Bash 特性的脚本禁止使用 `#!/bin/sh`**。

**为什么必须**（反面教材）：

```bash
backup_dir="/data/backup"
cd "$backup_dir"        # 若目录不存在：有 set -e 时立即退出；
rm -f *.log.old         # 无 set -e 时在当前目录继续 rm，后果可能是灾难性的
```

允许失败的命令局部放行：`some_optional_step || true`。

## 脚本骨架

```bash
#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# 脚本名称: deploy_app.sh
# 功能描述: 将应用部署到目标服务器
# 用法:     ./deploy_app.sh <环境名> [版本号]
# =============================================================================

readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

log()  { printf '[%s] INFO:  %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*"; }
warn() { printf '[%s] WARN:  %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*" >&2; }
die()  { printf '[%s] ERROR: %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*" >&2; exit 1; }

check_dependencies() {
    local deps=("$@")
    local dep
    for dep in "${deps[@]}"; do
        command -v "$dep" > /dev/null 2>&1 \
            || die "缺少依赖: $dep，请先安装"
    done
}

cleanup() {
    # 在此添加清理逻辑（如 rm -rf "$TMPDIR"）
    :
}
trap cleanup EXIT

usage() {
    cat <<EOF
用法: $(basename "$0") <环境名> [版本号]

参数:
  环境名    部署目标环境（dev / staging / prod）
  版本号    可选，默认部署最新版本

示例:
  $(basename "$0") staging v2.1.0
EOF
    exit 1
}

main() {
    [[ $# -lt 1 ]] && usage
    local env="$1"
    local version="${2:-latest}"

    check_dependencies git docker curl

    log "开始部署: 环境=$env, 版本=$version"
    # ... 实际逻辑 ...
    log "部署完成"
}

main "$@"
```

设计要点：`main "$@"` 收口全部逻辑；`readonly` 保护路径类常量；
依赖检测用 POSIX 内建 `command -v`（禁止 `which`）；错误与警告走 stderr。

## 强制规则

| 规则 | 说明 |
| ---- | ---- |
| **始终给变量加双引号** | `"$var"`，防止词分割和通配符展开（Bash bug 最常见的单一来源） |
| **用 `[[ ]]` 代替 `[ ]`** | Bash 内建，更安全，支持 `&&`、正则等 |
| **用 `$(cmd)` 代替反引号** | 可嵌套，可读性好 |
| **用 `printf` 代替 `echo`** | 行为更可预测、更可移植 |
| **用 `command -v` 代替 `which`** | POSIX 标准，更可靠 |
| **用 `readonly` 声明常量** | 防止意外覆写 |
| **`local` 声明和赋值分两行** | `local var` 然后 `var=$(cmd)`；写在一行时 `local` 会掩盖命令退出码 |
| **遍历文件用 glob 不用 `ls`** | `for f in *.log; do`，禁止 `for f in $(ls *.log)` |
| **禁止使用 `eval`** | 除非完全理解安全影响并有充分理由 |
| **`cd` 后检查退出码** | `cd "$dir" \|\| die "无法进入目录"` |

引号反面教材：`filename="my file.txt"; rm $filename` 实际执行 `rm my file.txt`；
`headline="* Headline *"` 不加引号时 `*` 会展开为当前目录文件列表。
**规则：除非明确需要词分割或通配符展开，否则永远加双引号。**

### 交给远端登录 shell 执行的脚本

管理员主机的登录 shell 可能是 bash、zsh 或 sh，`ssh host '...'` 的整段命令由登录 shell 解析。

- 这类脚本只用 POSIX 子集（`[ ]`、`$( )`、`printf`、`command -v`），不用 `[[ ]]`、数组、`local -n` 等 bash 扩展；确实需要 bash 特性时显式走 `bash -s`，并把该前提写进脚本注释。
- 下发前把**真实字节**分别过 `bash -n`、`zsh -n`、`sh -n`；本机只有 bash 就只验一种，等于把另一类机器的解析问题留到线上。
- 换行必须是 LF、引号不依赖外层命令行解析：从 Windows 侧生成这段文本时按 [文件与程序调用](../../powershell-pitfalls/references/files-and-invocation.md) 的换行与传参规则处理。
- 参数不要有空值：`ssh host bash -s -- "$a" "$b"` 的参数会被 ssh 拼成一行交给远端 shell 重新解析，空字符串直接消失，远端 `set -u` 下报 `$2: unbound variable`。可能为空的参数用占位值（例如 `-`）并在远端还原，或先编码成不含空白与换行的文本再传。
- **假 `ssh`/`scp` 做端到端回归**：把两个命令换成同名函数或 PATH 前置的桩，把远端脚本转发到本机 WSL/容器执行，就能在无真实主机时验证预检、重复执行幂等与错误分支。断言对象是“文件内容哈希 + 权限 + 状态行”，不要只看退出码。
- **桩只在同进程生效**：函数型桩对 `Start-Job`/`Start-ThreadJob` 的新 runspace 无效，并发路径仍会调真实二进制。顺序路径（如 `-ThrottleLimit 1`）全绿不等于并发路径也通过，交付时要写明哪条路径实测过、哪条只是复用既有实现。
- **模拟一台机器不等于多台**：多台“主机”指向同一个容器时，第二台会读到第一台写下的文件并返回“跳过”，这是正常现象，不是缺陷；要覆盖多机独立状态，给每台设不同的目标路径。

## 跨平台要点

| 差异点 | Linux (GNU) | macOS (BSD) | 兼容方案 |
| ------ | ----------- | ----------- | -------- |
| `sed` 原地编辑 | `sed -i 's/.../'` | `sed -i '' 's/.../'` | 统一用 `sed -i.bak` 后删除备份，或安装 `gnu-sed` |
| `date` 相对日期 | `date -d '1 day ago'` | `date -v-1d` | 用 `gdate`（Homebrew `coreutils`） |
| `readlink -f` | 支持 | 不支持 | `realpath` 或 `cd + pwd` 范式 |

## 质量工具

- **ShellCheck**：静态分析找 bug，`shellcheck script.sh`，以零告警为目标。
- **shfmt**：自动格式化，推荐 `shfmt -w -i 2 -ci -s script.sh`（CI 检查用 `shfmt -d` 只看差异）。
- 两者互补（前者查正确性，后者管格式），均接入 CI；VS Code 可装对应扩展获得实时反馈。

---

## Tab 补全

推荐：为需要补全的脚本提供配套补全脚本 `<脚本名>-completion.bash`，遵循以下固定模式：

```bash
#!/usr/bin/env bash
# deploy.sh 的 Tab 补全：source 本文件临时加载，
# 或写入 ~/.bashrc 持久加载，或复制到 /etc/bash_completion.d/ 供所有用户使用
_deploy_completions() {
    local cur prev
    cur="${COMP_WORDS[COMP_CWORD]}"
    prev="${COMP_WORDS[COMP_CWORD-1]}"

    case "$prev" in
        --version)
            # 取值型选项后补全候选值：优先动态获取
            local versions
            versions=$(git tag --list 'v*' 2>/dev/null)
            COMPREPLY=( $(compgen -W "$versions" -- "$cur") )
            return
            ;;
        --config)
            COMPREPLY=( $(compgen -f -X '!*.yaml' -- "$cur") )
            return
            ;;
    esac

    if [[ "$cur" == -* ]]; then
        COMPREPLY=( $(compgen -W "--version --config --dry-run --help" -- "$cur") )
    else
        local envs=()
        local f
        for f in configs/*.yaml; do
            [[ -e "$f" ]] || continue
            envs+=("$(basename "$f" .yaml)")
        done
        COMPREPLY=( $(compgen -W "${envs[*]}" -- "$cur") )
    fi
}
complete -F _deploy_completions deploy.sh
```

机制速查：`complete -F <函数> <命令>` 注册规则；用户按 Tab 时 Shell 设置
`COMP_WORDS`（当前命令行全部词）与 `COMP_CWORD`（光标所在词的索引），
补全函数把候选写入 `COMPREPLY` 数组。`compgen` 常用选项：
`-W` 按词列表匹配，`-f`/`-d` 匹配文件/目录，`-X` 按模式排除，`-c` 匹配可执行命令。

规则：

- 必须：补全函数命名为 `_<脚本名>_completions`，避免与用户环境中的函数冲突。
- 推荐：候选值动态获取（git tag、配置目录内容、API），而非写死静态列表。
- 必须：`COMPREPLY=( $(compgen ...) )` 是“永远加双引号”规则的**唯一例外**——此处需要词分割生成数组元素。
- 必须：补全脚本与主脚本同目录、纳入版本控制，并在 `usage()` 或 README 中说明安装方式。

## 反模式自检清单

- [ ] 是否缺少 `set -euo pipefail`？
- [ ] 变量是否全部加了双引号？
- [ ] 是否有 `for f in $(ls ...)`？改用 glob。
- [ ] `cd` 后是否检查了退出码？
- [ ] 是否使用了 `trap ... EXIT` 清理资源？
- [ ] 是否通过 ShellCheck 零告警？
- [ ] 需要补全时是否有配套 `<脚本名>-completion.bash`（同目录、已纳入版本控制、安装方式已写入 `usage()` 或 README）？
