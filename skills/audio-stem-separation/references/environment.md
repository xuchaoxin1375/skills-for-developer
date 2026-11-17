# 环境与依赖

## 依赖清单

| 依赖 | 用途 | 要求 | 缺失表现 |
| --- | --- | --- | --- |
| ffmpeg / ffprobe | 解码 mp3/flac、重编码、静音裁剪、验收探测 | ≥ 5，带 `libmp3lame` | `trim_silence.py` 报找不到 ffmpeg；`--mp3` 输出失败 |
| Python | 跑 demucs 与两个脚本 | 3.10–3.13 | 3.14 装 torch 会找不到 wheel |
| demucs | 分离模型与推理 | 4.1+（自动 MPS） | `demucs: command not found` |
| torch | demucs 推理后端 | 2.x，随 demucs 装上 | 导入报错 |
| numpy | demucs 运行时硬依赖；`check_audio_quality.py` 的频谱分析 | 任意 1.24+ / 2.x | `ModuleNotFoundError: No module named 'numpy'` |
| MLX 分离器（可选） | Apple Silicon 原生加速 | `demucs-mlx` 或 `mlx-audio-separator`；macOS 26.2+ 吃 M5 矩阵单元 | 未装时走 Demucs 的 MPS/CPU 路径 |
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
| 推理设备 | Demucs 4.1+ 自动 MPS；旧版 CPU-only；可选用 MLX | CPU 或 `-d cuda` | CPU 或 `-d cuda`（需 CUDA 版 torch，默认 wheel 可能不带） |
| 长路径 | — | — | 深层目录 + 中文名可能触发路径长度问题，分离时把工作目录放在浅层 |

- **Apple Silicon**：Demucs 4.1+ 自动使用 MPS（[macOS support](https://github.com/adefossez/demucs/blob/main/docs/mac.md)），不要固定 `-d cpu`；只有 MPS 报错或旧版 Demucs 才回退 `-d cpu`。MPS 已比 CPU 快一个数量级，但仍不如 MLX 原生实现；追求速度用 `demucs-mlx`（4 轨）或 `mlx-audio-separator`（2 轨/RoFormer）。MLX 要 macOS 26.2+ 才能启用 M5 的 GPU Neural Accelerators。
- **WSL**：装在 WSL 自己的发行版里，别用 `/mnt/c` 下的 Windows 解释器；音频放 WSL 文件系统，放 `/mnt/c` 会有明显 IO 开销。
- **Linux + NVIDIA**：需要 CUDA 版 torch，`pip install torch --index-url https://download.pytorch.org/whl/cu124` 之后再装 demucs，否则 `-d cuda` 报 `Torch not compiled with CUDA enabled`。

## 网络与镜像

- **PyPI**：默认源在很多国内网络下可用；明显卡在依赖下载时再换镜像，例如 `-i https://pypi.tuna.tsinghua.edu.cn/simple`。torch wheel 体积大，镜像只解决速度，不解决不可达。
- **HuggingFace**：demucs 4.1 的 `get_model` 先走 HF（`hdemucs` 等 bag 配置在那里），HF 不通时会在 `Retrying in 1s [Retry 1/5]` 之间静默等待，看起来像卡死。本 skill 的做法是绕过它：模型文件从 `dl.fbaipublicfiles.com` 直接取（实测可直连），再用 `--repo` 指本地目录离线加载。
- **MLX 模型**：`demucs-mlx` 首次从 HuggingFace 下载（htdemucs 约 160MB）；`mlx-audio-separator` 也从 HF/模型源拉取。它们不走 `fetch_model.py` 的 fbaipublicfiles 路径；HF 不通时设 `HF_ENDPOINT=https://hf-mirror.com`，或用各自的下载/预热参数先取模型。
- **两个源都不通**：设置 `HF_ENDPOINT=https://hf-mirror.com` 让 demucs 走镜像；或按 `network-access` 配代理后重试，并把结果记入本次结论，不要假设下次仍可用。
- **校验**：`fetch_model.py` 会核对文件名里的 sha256 前 8 位，校验不过直接删文件报错，不会留下半个模型让 demucs 加载失败。

## 性能与资源

实测（Apple M5，16GB 内存，torch 2.15，`htdemucs`，30 秒 mp3 片段）：

| 阶段 | 耗时 | 备注 |
| --- | --- | --- |
| 模型下载 | 约 15 秒（84MB） | 直连 fbaipublicfiles，按带宽浮动 |
| 模型加载 | 约 2.5 秒 | 每次进程启动一次 |
| 推理 | 13 秒 / 30 秒音频 | 约 2.6× 实时，≈0.4× 音频时长 |
| 环境安装 | 3–5 分钟 | 主要是 torch 下载 |

- 整首按 0.4× 时长估算：5 分钟的歌约 2–3 分钟（含加载）。耗时随音频时长线性增长，先拿 30 秒片段试跑即可定价。
- **别用长任务的总时长当性能基准**：macOS 合盖休眠会暂停进程、笔记本降频、容器 CPU 配额都会让 wall-clock 严重失真。判断推理速度看进度条里的 `x seconds/s`（每秒处理多少秒音频），或测时用 `caffeinate -i`（macOS）/ 关闭休眠（Linux）/ 电源计划设为高性能（Windows）。
- 进程被 SIGTERM 或休眠打断时会在原目录留下半成品，重跑前清掉输出目录。
- 内存峰值约 2–4GB（单曲、`htdemucs`）；多文件并行 `-j N` 会按倍数放大。
- 磁盘：venv 约 1.5GB，每个模型约 84MB，输出 mp3 与源文件同量级。
- 想更省时：Apple Silicon 用 Demucs 4.1+ 的 MPS 或 MLX；换量化模型（`mdx_q` / `mdx_extra_q`，体积与耗时更小、质量略降）、缩小 `--segment`、或有 CUDA 时用 `-d cuda`。

### Apple Silicon 加速

Demucs 4.1+ 在 Apple Silicon 自动走 MPS。公开基准（M4 Max 40 核 GPU、128GB、120 秒 44.1kHz、`htdemucs`，2026-10）：

| 后端 | 耗时 | 实时倍率 |
| --- | --- | --- |
| PyTorch CPU | 19.4 秒 | 6× |
| PyTorch MPS | 2.82 秒 | 42× |
| MLX（`demucs-mlx`） | 1.05 秒 | 114× |

**M5 16GB 实测**（demucs 4.1.0 + torch 2.15，`htdemucs`，5:02 曲目，自动 MPS）：推理 33 秒（≈10.5× 实时，进度条约 10 seconds/s），含模型加载共 1:13；128k MP3 与无损 FLAC 源耗时基本一致。按 M4 公开基准折算的 15–25 秒偏乐观，实测按 10× 实时估更稳。下面是从 M4 基准折算的预期值，仅作参考：同一 `htdemucs` 30 秒片段，原 CPU 约 15.5 秒；MPS 预计 4–5 秒，MLX 预计 3–4 秒。

- **`demucs-mlx`**：`pip install demucs-mlx`，然后 `demucs-mlx song.mp3`。输出 4 轨到 `separated/`，没有 `--two-stems`；只要 2 轨时用 `mlx-audio-separator`，或把 drums/bass/other 相加得到伴奏。
- **`mlx-audio-separator`**：`pip install mlx-audio-separator`，然后 `mlx-audio-separator song.mp3`。默认 BS-RoFormer 输出 vocals/instrumental；4 轨用 `-m htdemucs_ft.yaml`；`--output_format` 默认 FLAC，需要 mp3 时显式指定。M4 mini 上比 `audio-separator` 中位快 1.85×（htdemucs_ft 1.40×、BS-RoFormer 2.16×、Mel-Band 2.50×）。
- **`audio-separator`**：`pip install "audio-separator[cpu]"`；Apple Silicon 走 PyTorch MPS + ONNX CoreML，模型覆盖最广、成熟度最高，但比 MLX 慢。
- **M5**：MLX 要 macOS 26.2+ 才吃 GPU Neural Accelerators；`mlx-audio-separator` 的验证机是 M4 mini、README 只列 M1–M4，M5 先跑 30 秒片段做对照。
- **内存**：`demucs-mlx` 的 htdemucs 缓存在 128GB 机器上可到 16–31GB；16–24GB 机器要限制 cache 或长文件分块。`mlx-audio-separator` 与 `audio-separator` 都有 `--chunk_duration`。

#### M5 16GB 预设

M5 的 16GB 是统一内存，系统与浏览器会先占掉一部分；下面按“音频分离不换页”给保守参数：

- **默认（稳）**：Demucs 4.1+ 自动 MPS。出现换页或内存告警时加 `--segment 7`；这是降内存优先，不是提速。
- **4 轨 MLX**：`demucs-mlx --batch-size 1 --io-memory-mib 512 song.mp3`。不要同时开其他 GPU 应用。
- **2 轨/长文件 MLX**：`mlx-audio-separator song.mp3 --chunk_duration 300`；4 轨用 `-m htdemucs.yaml --chunk_duration 300`，先别用 `htdemucs_ft` 整包。
- **质量优先且要稳**：`AUDIO_SEPARATOR_MPS_BUFFER_BUDGET_GIB=6 audio-separator song.mp3 --chunk_duration 300`。PowerShell 用 `$env:AUDIO_SEPARATOR_MPS_BUFFER_BUDGET_GIB=6; audio-separator ...`。
- **5 分钟 MP3**：htdemucs/htdemucs_ft 可整轨；BS-RoFormer 先整轨，OOM/换页再加 `--chunk_duration 180`（分块边界可能有轻微 artifacts）。只听默认 320kbps MP3；要存档、进 DAW 或继续处理再出 16-bit FLAC（Demucs 用 `--flac`，24-bit/float32 只在还要混音时有意义）。MP3 源本身有损，FLAC/24-bit 不会恢复细节；不要上采样到 48/96kHz。分发副本从 FLAC 转一次 320kbps MP3，不要反复转码。
- **高风险组合**：批量跑 `htdemucs_ft`、长文件 BS-RoFormer、多个分离进程并行；单首 5 分钟可试 `htdemucs_ft --segment 7`，出现 swap、风扇持续满转或进度异常变慢再降级。

## 清理

```bash
rm -rf .venv-demucs ~/.cache/demucs-models   # 环境与模型一起清掉，不影响系统 Python
rm -rf ~/.cache/mlx-audio-separator ~/.cache/demucs-mlx   # 用过 MLX 路线时
```
