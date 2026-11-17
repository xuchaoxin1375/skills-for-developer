# 环境与依赖

## 依赖清单

| 依赖 | 用途 | 要求 | 缺失表现 |
| --- | --- | --- | --- |
| ffmpeg / ffprobe | 解码 mp3/flac、重编码、静音裁剪、验收探测 | ≥ 5，带 `libmp3lame` | `trim_silence.py` 报找不到 ffmpeg；`--mp3` 输出失败 |
| Python | 跑 demucs 与两个脚本 | 3.10–3.13 | 3.14 装 torch 会找不到 wheel |
| demucs | 分离模型与推理 | 4.x（4.1 实测） | `demucs: command not found` |
| torch | demucs 推理后端 | 2.x，随 demucs 装上 | 导入报错 |
| numpy | demucs 运行时硬依赖 | 任意 1.24+ / 2.x | `ModuleNotFoundError: No module named 'numpy'` |
| 网络 | 首次装依赖、下载模型 | 仅首次 | 见下文“网络与镜像” |

`trim_silence.py` 只用标准库，但需要 ffmpeg 解码与编码；`fetch_model.py` 只用标准库，运行在装了 demucs 的解释器里（它从 demucs 包里读模型清单）。

## 隔离安装

模型和 torch 加起来体积不小，装进系统 Python 会污染全局并可能顶掉别的项目依赖。

macOS / Linux：

```bash
python3 -m venv .venv-demucs
. .venv-demucs/bin/activate
python -m pip install -U pip demucs numpy
```

Windows PowerShell：

```powershell
py -3.12 -m venv .venv-demucs
.venv-demucs\Scripts\Activate.ps1
python -m pip install -U pip demucs numpy
```

系统 Python 版本过新（3.14）或过旧时改用 conda，锁一个受支持的版本：

```bash
conda create -n demucs python=3.11 -y
conda activate demucs
python -m pip install -U demucs numpy
```

**判据**：`python -m pip show demucs` 的 `Location` 必须落在刚建的 venv/conda 环境里。若落在 `~/.local/lib/python3.x/site-packages`，说明 pip 走了 user site，隔离没生效，用 `python -m pip install --no-user demucs` 或检查 `PIP_USER` / pip 配置。

## 平台差异

| 项目 | macOS | Linux | Windows |
| --- | --- | --- | --- |
| ffmpeg | `brew install ffmpeg` | `sudo apt install ffmpeg` | `winget install Gyan.FFmpeg` 或 `scoop install ffmpeg` |
| Python | `brew install python@3.12` | `sudo apt install python3 python3-venv` | `winget install Python.Python.3.12` |
| 激活环境 | `. .venv/bin/activate` | 同 macOS | `.venv\Scripts\Activate.ps1`（PowerShell 5.1 不支持 `&&`） |
| 推理设备 | 只有 CPU，没有 MPS | CPU 或 `-d cuda` | CPU 或 `-d cuda`（需 CUDA 版 torch，默认 wheel 可能不带） |
| 长路径 | — | — | 深层目录 + 中文名可能触发路径长度问题，分离时把工作目录放在浅层 |

- **Apple Silicon**：demucs 不接 MPS，`-d mps` 直接失败，只能 `-d cpu`；M 系列核心多，实际耗时仍以 CPU 线程数为准。
- **WSL**：装在 WSL 自己的发行版里，别用 `/mnt/c` 下的 Windows 解释器；音频放 WSL 文件系统，放 `/mnt/c` 会有明显 IO 开销。
- **Linux + NVIDIA**：需要 CUDA 版 torch，`pip install torch --index-url https://download.pytorch.org/whl/cu124` 之后再装 demucs，否则 `-d cuda` 报 `Torch not compiled with CUDA enabled`。

## 网络与镜像

- **PyPI**：默认源在很多国内网络下可用；明显卡在依赖下载时再换镜像，例如 `-i https://pypi.tuna.tsinghua.edu.cn/simple`。torch wheel 体积大，镜像只解决速度，不解决不可达。
- **HuggingFace**：demucs 4.1 的 `get_model` 先走 HF（`hdemucs` 等 bag 配置在那里），HF 不通时会在 `Retrying in 1s [Retry 1/5]` 之间静默等待，看起来像卡死。本 skill 的做法是绕过它：模型文件从 `dl.fbaipublicfiles.com` 直接取（实测可直连），再用 `--repo` 指本地目录离线加载。
- **两个源都不通**：设置 `HF_ENDPOINT=https://hf-mirror.com` 让 demucs 走镜像；或按 `network-access` 配代理后重试，并把结果记入本次结论，不要假设下次仍可用。
- **校验**：`fetch_model.py` 会核对文件名里的 sha256 前 8 位，校验不过直接删文件报错，不会留下半个模型让 demucs 加载失败。

## 性能与资源

实测（Apple M5，16 核 CPU，torch 2.15，`htdemucs`，5:39 的 320kbps mp3）：

| 阶段 | 耗时 | 备注 |
| --- | --- | --- |
| 模型下载 | 约 15 秒（84MB） | 直连 fbaipublicfiles |
| 环境安装 | 3–5 分钟 | 主要是 torch |
| 分离 | 约 37 分钟 | 约 6.5× 实时，CPU 满载 |

- 耗时大致随音频时长线性增长，先拿 30 秒片段试跑可估算整首。
- 内存峰值约 2–4GB（单曲、`htdemucs`）；多文件并行 `-j N` 会按倍数放大。
- 磁盘：venv 约 1.5GB，每个模型约 84MB，输出 mp3 与源文件同量级。
- 想提速：换量化模型（`mdx_q` / `mdx_extra_q`，体积与耗时更小、质量略降）、缩小 `--segment`、或有 CUDA 时用 `-d cuda`。

## 清理

```bash
rm -rf .venv-demucs ~/.cache/demucs-models   # 环境与模型一起清掉，不影响系统 Python
```
