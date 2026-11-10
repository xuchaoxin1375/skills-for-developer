# 服务端环境变量与代理排障

> 本文件是 `opencode-provider-config` 的按需参考，只在配置或排查 OpenCode 服务端 env、代理与重启问题时读取。主流程和验证顺序仍以 [SKILL.md](../SKILL.md) 为准。

## 脚本入口（推荐）

`scripts/opencode_proxy.py` 把本节的手工序列合成一条命令：三层对照（存储层 / live 进程 / 当前 shell）、变量名审计、`NO_PROXY` 分隔符与回环检查、有界 TCP 探活；写入时先审计再落盘，避免"配了代理却不生效"。

```bash
python3 -X utf8 scripts/opencode_proxy.py status                    # 只读；退出码 0 正常 / 1 有问题
python3 -X utf8 scripts/opencode_proxy.py status --json --no-probe  # 机器可读、不出网
python3 -X utf8 scripts/opencode_proxy.py set http://127.0.0.1:<port> [--no-proxy <放行域名>] [--no-restart]
python3 -X utf8 scripts/opencode_proxy.py unset [--all] [--no-restart]
```

- **写入**：读改写 `service.json`（同目录备份 + 临时文件原子替换 + 权限 600），代理变量只增合并不覆盖，其他 env 原样保留且不打印；`env` 若还是字符串（旧格式或手工写入的 Python dict 串）会解析后迁移成标准对象；`set` 会顺手移除拼错的代理变量名（如 `HPPTS_PROXY`），避免写入成功但依旧直连。
- **重启**：默认 detached 重启一次，轮询 `/api/info` 的 pid 变化，再核验新进程环境；`--no-restart` 只写存储层，适合在 OpenCode 会话内执行（重启会打断当前命令）。
- **降级**：Windows 无法读取其他进程环境，核验只报告"新进程已就绪、未能核验"，需配合启动时间或一次真实请求判断。macOS 用 `ps eww` 读取，值含空格时可能截断（代理 URL 与 `NO_PROXY` 不含空格，够用）；Linux 走 `/proc/<pid>/environ`。
- **退出码**：0 正常；1 发现问题或核验未通过；2 用法/IO 错误；3 `service.json` 的 `env` 格式不受支持（此时改用 `opencode service set env` 重写）。

脚本只处理代理类变量；密钥仍走 `opencode service set env`，不要因为脚本能写 env 就把密钥塞进它的调用。

## 按域名分流代理

代理是进程级的，JSON 配置无法按 provider 配代理（源码的 `options.fetch` 是函数，写不进配置文件）。同一供应商有多个入口域名、部分直连部分被阻断时，用服务端全局代理 + `NO_PROXY` 分流：直连可达的域名加进 `NO_PROXY`，其余域名自动走代理。例：域名 A 直连、域名 B 被阻断，则 `NO_PROXY` 加 A，两套 provider 配置共用同一服务端代理即可自动分流，启动时无需设置任何环境变量。

## 代理的其余前提

- **前台进程不吃服务端 env**：`--standalone` 与 `serve` 读自身进程环境，代理要写进启动那条命令；`service set env` 只对托管的后台服务生效。
- **代理认证**：账号密码写进代理 URL 并对 `@`、`:`、`/` 等百分号编码（如 `http://user:p%40ssword@127.0.0.1:<port>`）；网关回 `407 Proxy Authentication Required` 即属此情形。
- **TLS 解密**：代理或杀软做 HTTPS 扫描时报 `SELF_SIGNED_CERT_IN_CHAIN`、`CERT_NOT_YET_VALID`、`CERT_SIGNATURE_FAILURE`，先把 `opencode.ai`、`*.opencode.ai` 与 provider 域名排除扫描，其次导出其 CA 为 PEM 设 `NODE_EXTRA_CA_CERTS`，随服务持久化后重启生效。
- **撤销**：`opencode service unset env HTTPS_PROXY`（`HTTP_PROXY` 同理）。删除同样只改存储层，旧快照要等下一次服务重启才消失。

## 密钥错位排查

同一 provider 下所有模型均报网关侧“无可用渠道”，但配置文件与单模型直连测试均正常时，应优先怀疑实际生效的密钥与本次配置的密钥不一致（多会话共用同一后台服务时易发生混用）。以下命令仅输出 `True`/`False`，不打印密钥明文：

```bash
python3 -c "import os; print(os.environ.get('<PROVIDER>_API_KEY','') == '<KEY>')"
```

输出 `False` 即确认错位：不同密钥对应不同的网关账号，其模型目录与分组权限各自独立。此时换用正确的密钥并重启服务即可恢复，无需修改 provider 配置。

## 变量名占用前置检查

定 `env` 变量名前，先查四层是否已有同名（`service get env`、当前 shell 进程、Windows `User`/`Machine` 注册表），任一层有值且与本次密钥不同即视为占用，必须换名，不得覆盖用户既有变量。以下命令只查有无，不输出值：

```powershell
[Environment]::GetEnvironmentVariable("<NAME>","User")
[Environment]::GetEnvironmentVariable("<NAME>","Machine")
```

任一返回非空即占用。`providerID` 同理：不得与内置供应商同名（内置改 `baseURL` 只覆盖 `settings.baseURL`，见主文件的适用范围）。

## 大小写代理变量

shell 环境中通常仅存在小写 `http_proxy` 系变量，但部分 HTTP 客户端仅识别大写变量。恢复代理时，应以 `env | grep -i proxy` 的实测值为准补齐大写三变量（端口照抄实测值，不得臆造；写入方式见主文件的 env 模板），`NO_PROXY` 保持逗号分隔。

Windows 另有一层：变量**存储名取首次创建时的大小写**，此后换大小写赋值只改值不改名，子进程继承的仍是旧名。`$env:HTTPS_PROXY` 回读有值不能作通过依据，要用 `Get-ChildItem Env:` 或 `cmd /c 'set | findstr /i proxy'` 看真实名字；修复先 `Remove-Item Env:https_proxy` 再以大写名重建。

与大小写相邻的另一个坑是**拼写**：`HPPTS_PROXY`、`HPPT_PROXY` 会完整落盘、出现在 `get env` 与进程环境里，但任何 HTTP 客户端都不会读取，`service set env` 也不会报错。`service get env` 只能证明"写了"，不能证明"会被读"，判定仍以 `scripts/opencode_proxy.py status` 的变量名审计与 live 对照为准。

## 已知行为：set env 会重启服务

每次 `service set env` 都会重启后台服务，导致正在执行的 shell 命令以 "Tool execution interrupted"（导出日志中也显示为 "Command cancelled"）中断——这不是失败，变量已写入。变量名与取值全部定稿后再写入，`set env` 次数即重启次数，能少一次就少一次；逐条设置、每条跑完重新确认即可；确认用只读的 `opencode service get env`（输出含密钥，展示前先打码）。

## 例外：写入丢失

经由服务端派生的 shell 执行 `set env` 时，服务重启可能先于 CLI 完成写入即将其终止，导致写入丢失（`get env` 仍为空）。若多次重试后 `get env` 依然为空，即属此情形，应改用 detached 方式执行，并以只读命令确认：

```bash
setsid nohup opencode service set env <KEY_NAME> <KEY_VALUE> >"$HOME/setenv.log" 2>&1 < /dev/null &
sleep 75
opencode service get env                                        # 只读确认已落盘（输出含密钥，展示前打码）
ps -o pid,ppid,lstart,cmd $(pgrep -f "serve --service")         # 以 STARTED 时间最新者为当前服务进程
```

`service restart` 完全生效约需 1 分钟：重启后不得以 pgrep 返回的第一个 PID 为准（该进程可能处于正在退出的瞬态），必须以上述 `ps` 输出中 `STARTED` 时间最新者为准，再对其核验环境变量。

Windows 没有 `/proc` 与进程组连带终止：`set env` 的写入通常已落盘，被打断的是同一条命令里后续的 `service start`，表现为只写进一半变量。把成串操作交给脱离服务进程树的子进程一次做完，再用只读命令确认：

```powershell
Start-Process pwsh -ArgumentList '-NoLogo','-NoProfile','-Command','opencode service set env <VAR> <VALUE>; Start-Sleep -Seconds 2; opencode service start' -WindowStyle Hidden
opencode service get env        # 只读确认（输出含密钥，展示前打码）
```

## 重启时的竞态

`service stop` 只杀服务进程；空窗期里其他存活的客户端（另一窗口的会话、编辑器扩展）发现服务不可用会自行拉起一个，并沿用**它自己**的环境，随后执行的 `service start` 因服务已存活而成为空操作——代理是否跟得上取决于谁先抢到。要可控就二选一：把变量写进持久化 `env`（`set env`），或关掉所有入口再 `stop`/`start`。

## 存储与生效分离

环境变量有三层——shell 里 export 的临时变量（对服务进程无效，见第 2 步结论）、`get env` 读的持久化存储（`service.json` 的 `env` 块）、运行中服务进程启动时继承的快照（读法 `tr '\0' '\n' < /proc/<PID>/environ`）。三者可各自不同步；`get env` 为空并不代表服务进程中无此变量——修改服务级 env 之前，除 `get env` 外，还应查询 live 服务进程的环境（密钥经掩码处理，不输出明文）：

```bash
SERV_PID=$(pgrep -f "serve --service" | head -n 1)
tr '\0' '\n' < /proc/$SERV_PID/environ | grep -E "PROXY|_API_KEY" | sed -E 's/(sk-)[A-Za-z0-9]+/\1****/g'
```

修改存储后，必须重启服务一次，新进程才会继承更新后的变量；多次 `set env` 意味着多次重启并多次打断用户会话，因此应一次合并写好 `env` 块，再执行单次 restart。重启本身有风险：只存在于旧进程 environ 快照、未持久化的代理变量会随旧进程消失，任何重启前先双查（`get env`＋live environ），缺的先补持久化再重启；从服务派生的 shell 里直接跑 `service restart` 可能被重启连带打断，用 detached 方式（`setsid nohup … &`）执行，重启后按 STARTED 时间定位新进程并核验 PROXY 变量仍在。

## live 未生效的判定与隔离验证

Windows 无 `/proc` 时，以对照与隔离为准。`service status` 端口与 `opencode.log` 中 `spawning process` 的 `run=` 是否变化，是重启是否真正生效的判据；两者不变即 live 仍是旧快照，此时重复 `set env`/`restart` 只是空转，应停手。也可用启动时间佐证：`opencode api get /api/info` 返回的 `pid` 用 `(Get-Process -Id <pid>).StartTime` 读出，晚于最后一次 `set env` 即新快照。Windows 没有内置命令读别的进程 environ；同权限进程可用 PEB + `ReadProcessMemory` 读环境块取精确证据，常规以「新进程启动时间 + 回环健康 + 代理可达 + 一次真实请求」判断。用已知正常模型做对照：已知模型 `run` 正常、新模型报缺 key，即 live 陈旧而非配置错。先用 `run --standalone` 隔离验证（私有服务继承当前 shell 环境，同条命令内设变量并验证，密钥不落盘到配置文件）：

```powershell
$env:<VAR_NAME> = "<KEY>"; opencode run --standalone -m <providerID>/<modelID> "reply with exactly: OK"
```

通过即证明配置与密钥无误；后台服务侧改用会话外部重启（新开终端、任务管理器、重启机器）后再按第 5 步重验，不在会话内空转重试。
