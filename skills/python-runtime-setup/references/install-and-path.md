# 安装与 PATH

命令中的 `<version>`、`<minor>` 用实际值替换。改 PATH、装全局工具或动执行策略前先说明影响；优先用户级，不默认要求管理员。

## 先复用已有安装

1. 运行 `uv --version`、`uvx --version`、`python -m uv --version`。
2. Windows 用 `where.exe uv`、`where.exe uvx`；Linux/macOS 用 `command -v uv`、`command -v uvx`。
3. 如果 `uv` 找不到但 `python -m uv` 可用，说明 uv 二进制通常已随 Python 包装在用户脚本目录，只是目录不在 PATH：
   - Windows：通常为 `%APPDATA%\Python\Python3<minor>\Scripts`；
   - Linux/macOS：通常为 `~/.local/bin`。
   先补 PATH，不重装。
4. 如果两处版本不同，保留一套；不要继续叠加安装。

`python -m uv` 是启动器，会在已知脚本目录中寻找 `uv` 二进制；它不是第二个 uv。移动或删除二进制后，启动器可能失效。

## Windows

### standalone 安装器

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

安装到 `%USERPROFILE%\.local\bin`；安装器通常会处理 PATH。新开终端后验证：

```powershell
uv --version
uvx --version
where.exe uv
```

更新用 `uv self update`。卸载时删除 `uv.exe`、`uvx.exe`、`uvw.exe`；缓存和工具目录按需清理。

### winget

```powershell
winget install --id=astral-sh.uv -e
winget upgrade --id=astral-sh.uv -e
```

### Scoop

```powershell
scoop install main/uv
scoop update uv
```

Scoop 的 shim 在用户或全局 Scoop 的 `shims` 目录，通常已在 PATH。不要与 standalone 同时保留。

### pipx

```powershell
pipx install uv
pipx upgrade uv
```

### pip --user

```powershell
python -m pip install --user uv
python -m pip install --user --upgrade uv
```

二进制通常落在 `%APPDATA%\Python\Python3<minor>\Scripts`，该目录默认不一定在 PATH。需要时把该目录加入用户 PATH；不要把 uv 安装到每个项目 venv。

### PATH 追加（用户级）

先备份当前用户 PATH，再追加；把 `<minor>` 替换为实际 Python 版本：

```powershell
$dir = Join-Path $env:APPDATA 'Python\Python3<minor>\Scripts'
$current = [Environment]::GetEnvironmentVariable('PATH', 'User')
if (($current -split ';') -notcontains $dir) {
    [Environment]::SetEnvironmentVariable('PATH', ($current.TrimEnd(';') + ';' + $dir), 'User')
}
```

新开终端生效。若 PATH 含 `%VAR%` 展开项，改用注册表 `HKCU:\Environment` 的 `Path` 并保留 `ExpandString` 类型，避免把变量展开成固定值。

## Linux / macOS

### standalone 安装器

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

安装到 `~/.local/bin`；确认该目录在 PATH：

```bash
export PATH="$HOME/.local/bin:$PATH"   # 写入 ~/.bashrc 或 ~/.zshrc 后重开 shell
uv --version
command -v uv
```

更新用 `uv self update`。

### Homebrew

```bash
brew install uv
brew upgrade uv
```

### pipx / pip --user

```bash
pipx install uv
pipx upgrade uv
# 或
python3 -m pip install --user uv
python3 -m pip install --user --upgrade uv
```

pip --user 的脚本目录通常是 `~/.local/bin`；确认其在 PATH。

## 工具可执行目录

`uv tool install` 的可执行文件必须在 PATH 才能直接调用。用 `uv tool dir --bin` 查看目录；不在 PATH 时，可运行 `uv tool update-shell` 写入常见 shell 配置，或手动把该目录加入 PATH。`uv tool update-shell` 会修改 shell 配置文件，执行前确认影响。

## 验收

```powershell
uv --version
uvx --version
python -m uv --version
uv cache dir
where.exe uv
```

```bash
uv --version
uvx --version
python3 -m uv --version
uv cache dir
command -v uv
```

- `uv` 与 `python -m uv` 版本应一致；不一致说明有两套安装。
- `where.exe uv` / `command -v uv` 应只指向计划保留的一套；多个结果先清理再继续。
- PATH 修改后必须新开终端；已打开的进程不会自动刷新。
- 不把 uv 装进项目 venv；项目环境只装项目依赖。
