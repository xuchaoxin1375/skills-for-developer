# bash 与其他 POSIX 壳

> 本文件是 `shell-pitfalls` 的按需参考，只在执行 bash/Git Bash 或排查其启动、路径、编码与交互问题时读取。脚本编写与风格规范见 [Shell (Bash) 规范](../../scripting-best-practices/references/shell.md)，两处不重复。

## 适用

- 在 Windows 上用 Git Bash 跑仓库脚本、POSIX 工具或补全验证。
- 在 Linux/macOS/容器里执行 bash，或排查 `ssh`、`docker exec` 下的行为差异。
- 只关心"这条命令怎么跑、为什么没按预期执行"；写新脚本、严格模式设计走 `scripting-best-practices`。

## 启动方式与 rc

| 调用 | 类型 | 读取的启动文件 |
| --- | --- | --- |
| `bash -lc '<cmd>'` | 登录、非交互 | `/etc/profile`，再取 `~/.bash_profile`、`~/.bash_login`、`~/.profile` 中第一个存在的 |
| `bash -c '<cmd>'` | 非登录、非交互 | 默认不读 rc；设置了 `$BASH_ENV` 时读它 |
| `bash -ic '<cmd>'` | 非登录、交互 | `~/.bashrc`（Debian/Ubuntu 的 `~/.profile` 也会 source 它） |
| `bash -i` / 正常打开 Git Bash | 交互 | 同 `-ic`；Git Bash 默认以登录交互方式启动 |

- 需要别名、补全函数、`PATH` 增补等交互配置时显式 `-ic`；用 `-c` 验证后声称"配置没生效"多半是没读 rc。
- 登录 shell 会打印 job control 警告（`no job control in this shell`），非交互验证时可忽略；不要为消警告去改用户 rc。
- 验证 rc 是否加载，先跑 `bash -ic 'type <函数名>'` 或 `bash -lic 'command -v <命令>'`，分别对应非登录与登录场景，不凭一次结果外推另一种。
- 调试启动慢：`bash -x -ic true`（或 `PS4='+ $EPOCHREALTIME '`）看 rc 逐行耗时；不要用空 `-c` 的成败判断启动链路。

## 退出码与管道

- `$?` 只保留上一条命令的退出码；`echo $?` 本身会覆盖它，需要时先存变量。
- 管道默认取最后一段的退出码。任一段失败即判失败用 `set -o pipefail`；已有 `set -euo pipefail` 的脚本不用重复设置，交互会话可临时 `set -o pipefail`。
- 逐段状态看 `PIPESTATUS`：`cmd1 | cmd2; echo "${PIPESTATUS[@]}"`。它在下一条命令后即被覆盖，必须紧跟管道读取。
- `set -e` 的边界：出现在 `if`/`while` 条件、`!` 取反、`&&`/`||` 的非末位、管道非末段（未开 `pipefail`）时不会退出；`local x=$(cmd)` 这类声明会掩盖命令退出码。
- 原生命令失败后立即判断，不让后续成功命令掩盖；需要显式分支时写 `if ! cmd; then ...; fi`，不用 `|| true` 掩盖真实故障。
- `exit` 只影响当前 shell；`bash -c` 的退出码会回传给调用方，调用方仍要检查。

## 引号与参数

- 从 PowerShell 或 Windows 命令行调 bash 时，先分清哪一层在解析引号：外层负责分组与转义，`bash -c` 内部再解析一次。含中文、`$`、反引号、通配符的命令写成 `.sh` 文件再执行，最省事。
- `"$@"` 保留参数边界，`"$*"` 会合并成一个词；遍历参数用 `for a in "$@"; do`。
- 变量默认加双引号；需要原样输出时用 `printf '%s\n' "$var"`，不用 `echo` 处理以 `-` 开头或以 `\` 结尾的内容。
- 不把用户输入拼进 `eval`；需要动态执行时改数组或 `bash -c` 配合显式参数。
- 单引号内不做任何展开；需要字面 `$`、`!` 时优先单引号，不用层层反斜杠。

## 路径转换（Git Bash / MSYS）

- Git Bash 内 `/c/<目录>/...` 对应 `C:\<目录>\...`；`/` 在 bash 视角是 MSYS 根，不等于 `C:\`。
- 调用原生 Windows 程序时，MSYS 会把看起来像路径的参数转成 Windows 形式；不需要时按前缀排除：`MSYS2_ARG_CONV_EXCL='/foo;/bar'`，整体关闭用 `*`；旧版 Git Bash 用 `MSYS_NO_PATHCONV=1`。环境变量转换用 `MSYS2_ENV_CONV_EXCL`。
- 显式转换用 `cygpath -w <POSIX 路径>` 或 `cygpath -u '<Windows 路径>'`；脚本里不要手写盘符与斜杠的替换。
- PATH 分隔符：MSYS 内是 `:`，PowerShell/Windows 是 `;`。把 Windows 风格 PATH 直接赋给 bash 会让首项失效，反向也会破坏 Windows 程序查找。
- `cmd` 内建命令经 Git Bash 调用要写 `cmd //c '<命令>'`（双斜杠避免被当成路径转换）；能用 Windows 原生程序就不要绕 `cmd`。
- 符号链接、执行权限在 MSYS 下受挂载选项影响；脚本用 `bash <脚本>` 调用可直接绕开 `chmod +x` 与 shebang 问题。

## 换行、编码与 locale

- `.sh` 必须 LF。CRLF 的 shebang 报 `/usr/bin/env: 'bash\r': No such file or directory`；heredoc 结束符带 `\r` 时还会多出空行或语法错误。从 Windows 侧生成时明确写 LF，不用编辑器默认换行。
- 判断是否 CRLF：`file <脚本>` 或 `sed -n '1p' <脚本> | od -c | head`；修正在副本上做，不整仓转换。
- Git Bash 通常使用 UTF-8 locale（`LANG`/`LC_ALL` 形如 `*.UTF-8`）；`locale` 可确认。`LC_ALL=C` 会让非 ASCII 排序、大小写与字符类按字节处理。
- 中文乱码先分层：文件本身编码、locale、控制台代码页、输出经过的 PowerShell 文本层。分别用 `file`、`locale`、`chcp`（Windows 控制台）核对，再决定是否 `chcp 65001` 或显式转码。
- 原生 Windows 程序（如 `git`、`python.exe`）从 bash 启动时，输出编码由程序自身与代码页决定，不由 bash 决定；`iconv` 只在明确知道源编码时用。
- Python 统一 `python -X utf8`；Node 与自研 CLI 的输出编码问题按 [编码分层与校准](encoding-read.md) 定位。

## TTY 与交互

- mintty（`git-bash.exe` 默认终端）不是 Windows 控制台：`AttachConsole` 附加不上，读取屏幕缓冲区也无效。需要模拟按键复验时改用 `bin\bash.exe` 或 Windows Terminal 中的 bash，见[交互式控制台验证](interactive-console-verification.md)的 Git Bash 一节。
- `bin\bash.exe` 可能只是启动器，交互 shell 是它拉起的 `usr\bin\bash.exe` 子进程；直接附加启动器读不到提示符。按 `ParentProcessId` 找子进程。
- 需要读终端尺寸、做全屏菜单或交互输入的程序在无 TTY 环境会失败或退化；`winpty <命令>` 可在 mintty 中补一个伪终端，但解决不了 CI、重定向与管道场景。
- `docker exec` 不带 `-t` 时没有 TTY，`ssh` 不带 `-t` 同理；需要交互界面时显式加，纯自动化不要加。
- 补全验证：bash 多候选时第一次 Tab 只补公共前缀或响铃，第二次才列候选；候选数超过 `completion-query-items` 会先问 `Display all ...? (y or n)`。不要以一次 Tab 没有列表判定补全失效。

## 其他 POSIX 壳

- macOS 自带 `/bin/bash` 是 3.2，`#!/usr/bin/env bash` 需要 PATH 里先有 Homebrew bash；`-o pipefail` 可用，但关联数组、`mapfile` 等 4.x 特性不可用。
- macOS 默认交互 shell 是 zsh，读取的是 `~/.zshrc` 而不是 `~/.bashrc`；验证"补全为什么没生效"先确认当前 shell 与 rc 文件。
- WSL 的 bash 在虚拟机内，与 Windows 控制台不在同一进程树；`wsl.exe bash -lc '<命令>'` 适合非交互验证，附加控制台注入按键未实测，需要窗口级验证时在 WSL 终端内按 Linux 方式处理。
- POSIX `sh`（dash）不支持 `[[ ]]`、数组与 `mapfile`；`local` 等扩展随实现而异，不把它当作 POSIX 保证。用 `sh -n` 只证明语法，不证明行为与 bash 一致。

## 已知未验证

- Git Bash 下用探针注入按键复验补全：仓库脚本的附加与注入流程尚未在 bash 实测，启动差异与预期见[交互式控制台验证](interactive-console-verification.md)。
- WSL 与容器内的窗口级按键注入未验证，只用过非交互入口。
- mintty 下的 `winpty` 行为随 Git for Windows 版本变化，遇到差异以实际输出为准。
