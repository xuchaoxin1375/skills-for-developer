## 错误处理与输出契约

### 非终止错误与原生命令退出码

`try/catch` 捕获终止错误。cmdlet 默认的非终止错误可以写到错误流后继续执行；原生 EXE 的退出码又是另一层，不能把这两类失败都交给一个 `catch`。

以下用于复现，假定目标文件不存在：

```powershell
try {
  Get-Item -LiteralPath '.workspaces/absent-probe.txt'
  'CONTINUED'
} catch {
  'CAUGHT'
}
```

默认会报错并继续输出 `CONTINUED`。该操作必须成功时，使用 `-ErrorAction Stop`，即可进入 `catch`；批量处理允许部分失败时，可以逐项收集错误并报告，不必把所有 cmdlet 全局改为终止错误。

原生程序最小复现：

```powershell
$ErrorActionPreference = 'Stop'
try {
  python -c 'import sys; sys.exit(7)'
  $nativeExit = $LASTEXITCODE
  "CONTINUED:$nativeExit"
} catch {
  'CAUGHT'
}
```

5.1 以及未启用相应原生错误偏好的 pwsh 中，可能输出 `CONTINUED:7`。支持 `$PSNativeCommandUseErrorActionPreference` 的 pwsh 可改变该行为；兼容代码仍应明确检查退出码，不把本机偏好当跨版本保证。

```powershell
python -c 'import sys; sys.exit(7)'
$nativeExit = $LASTEXITCODE
if ($nativeExit -ne 0) {
  throw "External command failed with exit code $nativeExit"
}
```

上述示例以 0 为唯一成功值；实际工具按其退出码契约判断，例如搜索无匹配可以是预期分支。捕获码应紧跟调用：其他原生命令可能覆盖 `$LASTEXITCODE`；`$?` 只表示最近执行状态，输出一条日志后就可能由失败变成功。不以 stderr 有无、启动成功或子进程存在代替退出码和预期结果。

合并且 stderr 会绕过这套退出码分支：`$ErrorActionPreference = 'Stop'` 下写 `$out = & tool ... 2>&1`，5.1 把合并进来的 stderr 记录当成终止错误（`NativeCommandError`），批量处理在第一次失败处就中断，后面的 `$LASTEXITCODE` 判断根本执行不到。2026-10-28 实测：同一函数在 5.1 的顺序分支直接终止，同一份代码在 7.5.4 正常返回。要靠退出码决定"单台失败继续下一台"的逻辑，进入这段前把 `$ErrorActionPreference` 在脚本块或函数作用域内局部降为 `Continue`，失败统一由 `$LASTEXITCODE` 判定。

### 函数的成功输出流

```powershell
function Get-Probe {
  Write-Output 'debug message'
  return 42
}
$result = @(Get-Probe)
$result.Count  # 2：日志和数值都成了返回结果
```

返回数据的函数用 `Write-Verbose`、`Write-Debug` 等诊断流记录日志；无用的集合/方法返回值用 `$null = ...` 或适当的 `Out-Null` 消化。整条 CLI 若有机器读取 stdout 的契约，也应分离诊断与结果；合并 `*>&1` 等输出流会重新混合，不能在合并后假设只有业务对象。

`Format-Table`/`Format-List` 返回展示用格式对象；对象应先筛选、导出或序列化，最后才格式化给人看。已有文本捕获契约可使用文本输出，不把“所有输出必须是对象”当通用要求。

### 执行策略、脚本调用与诊断

- 被执行策略拒绝时先用 `Get-ExecutionPolicy -List` 核对生效范围和脚本来源；确需临时放行可信脚本时才使用进程级 `-ExecutionPolicy Bypass`。不默认修改全局策略；该参数不授予管理员权限，也不能覆盖组策略。
- `powershell -File s.ps1 -VerifyOnly -Include name`：`-File` 后参数直传给脚本，
  `[switch]` 开关照常用。
- `exit N` 即进程退出码，外层用 `$LASTEXITCODE` 读。`-File` 模式退出码可以正常透出；
  "退出码 0 但无输出"仍需核对实际执行结果，并检查[版本差异与脚本 BOM](startup-and-version.md#版本差异出大头的地方)。
- 独立诊断探针可用 `Write-Output` 提供可捕获结果；返回业务对象的函数应分离诊断流，不能把日志混入成功输出。`Write-Host` 用于宿主展示，其捕获取决于宿主与输出流设置。

### 静默失败逐段定位

1. hello-world 对照：`Write-Output AAA` 的 tmp 脚本能跑，说明外壳与调用方式没问题。
2. 从 `param()` 块后逐段插 `Write-Output PROBE-<位置>`，看断在哪两行之间。
3. 断点前后加变量值探针（如 `"DIR=" + $skillsDir`），注意探针字符串本身别引入新的插值坑。
4. 探针与重定向输出放临时或被忽略的工作目录，不混入交付；清理时只处理本任务创建的文件。

### 验证记录

2026-10-11，在 Windows PowerShell 5.1 与 pwsh 7.5.3 的隔离子进程中复现：默认 cmdlet 错误后继续、`-ErrorAction Stop` 进入 catch、原生返回 7 后继续及显式检查后进入 catch、后续日志改写 `$?`、函数日志令结果数量从 1 变 2。测试原生错误偏好时在支持的版本显式关闭该偏好，不推定所有 pwsh 默认配置相同。

这些证据验证错误与输出机制，不证明项目自己的成功码策略、错误恢复或所有原生程序已通过验证。
