---
name: audio-stem-separation
description: 从歌曲或音频里分离人声与伴奏（提取 BGM、去人声、卡拉OK、采样），并清理分离后音轨中的空白段。覆盖 Demucs 安装与离线模型准备、Apple Silicon MPS/MLX 与 CPU/CUDA 耗时取舍、ffmpeg 静音裁剪与三平台差异，以及分离前的源品质核验（码率虚标、假无损、有效带宽）。用户要求提取伴奏、去人声、人声分离、做卡拉OK版、判断下载的音频是不是真 320k/真无损，或说分离后有大段空白需要剪掉时使用；纯转码、剪辑拼接、变速变调、降噪修复不适用。
---

# 音频人声/伴奏分离与空段清理

## 适用范围

- 从一首歌提取伴奏（BGM）或人声轨：翻唱、卡拉OK、采样、配音替换。
- 分离出来的音轨有大段空白（纯伴奏段落、间奏、尾奏），需要剪成连续片段。
- 不适用：纯转码、剪辑拼接、变速变调、降噪/修复、多轨混音母带，这些用 ffmpeg 直接完成即可。

不熟悉采样率、码率、频谱截止、LUFS、SDR 这些参数时，先读 [音频概念速查](references/audio-basics.md)：它面向不常处理音频的读者，解释每个数字在说什么、哪些结论不能从标签得出。

## 最短路径

前置：ffmpeg（编解码与裁剪）、Python 3.10–3.13、demucs（带 torch）。三平台安装与网络细节见 [环境与依赖](references/environment.md)。

1. **预检**：`ffmpeg -version` 有输出且带 `libmp3lame`；`python3 -V` 在 3.10–3.13 之间。3.14 装不上 torch，换成 3.11/3.12 的解释器或 conda 环境。

   源文件先量有效带宽（用装 demucs 的解释器）：

   ```bash
   python scripts/check_audio_quality.py song.mp3
   ```

   声明码率不等于内容：13–16 kHz 就截止的低码率源，上 `htdemucs_ft`/RoFormer 也补不回高频，仍用默认 `htdemucs`。判决表、假无损与灰区处理见 [源品质核验](references/quality-check.md)。

2. **建隔离环境**（不要装进系统 Python）：

   ```bash
   python3 -m venv .venv-demucs
   . .venv-demucs/bin/activate          # Windows: .venv-demucs\Scripts\Activate.ps1
   python -m pip install -U demucs numpy
   ```

3. **准备本地模型仓库**。demucs 4.x 默认先访问 HuggingFace 取 bag 配置，在无法直连 HF 的网络里会长时间无输出地卡住；用本地仓库可完全离线：

   ```bash
   python scripts/fetch_model.py --model htdemucs --dir ~/.cache/demucs-models
   ```

   先从 `python scripts/fetch_model.py --list` 看有哪些可选模型。

   仓库目录一旦选定就固定复用：`fetch_model.py --dir` 与 `demucs --repo` 必须指向同一路径，换名字等于把每个模型（约 84MB）重下一遍。已有仓库先 `ls ~/.cache/demucs*` 再决定要不要新建。

4. **分离**（默认只分人声/伴奏两轨，320kbps mp3）：

   ```bash
   demucs --repo ~/.cache/demucs-models -n htdemucs --two-stems=vocals \
          --mp3 --mp3-bitrate 320 -o out/ song.mp3
   ```

   Demucs 4.1+ 在 Apple Silicon 上自动走 MPS；只有 MPS 报错或旧版 Demucs 才加 `-d cpu`。Linux/Windows 无 CUDA 时加 `-d cpu`，有 CUDA 时用 `-d cuda`。想比 MPS 更快，见下方“Apple Silicon 加速”。

   只听就保持 `--mp3 --mp3-bitrate 320`；要存档、进 DAW 或继续处理，再换成 `--flac`。需要分发时从 FLAC 转一次 320kbps MP3，避免反复有损编码。

   产物在 `out/htdemucs/song/{vocals,no_vocals}.mp3`：`no_vocals` 是伴奏，`vocals` 是人声。

5. **需要连续人声时裁剪空白段**（先 `--dry-run` 看段表，确认再执行）：

   ```bash
   python scripts/trim_silence.py out/htdemucs/song/vocals.mp3 --dry-run
   python scripts/trim_silence.py out/htdemucs/song/vocals.mp3 \
          --output vocals-trim.mp3 --mode cut
   ```

   `--mode mute` 保留原时间轴只把空段音量归零，用于还要和伴奏对轨的场景；`cut` 会移除空段，时间轴随之改变。

   dry-run 段表里，1–3 秒、电平低于 -45 dB 的碎段多半是分离泄漏或气口，可加 `--min-keep 2` 去掉。但别为了去碎段整体调高 `--threshold-db`：-30 上下会把正常乐句间的换气一起判成空白，5 段会涨到 9 段，整句被切碎。源换过（例如从 128k 换成无损）要重看段表：前奏可能多出十几秒电平很低的泄漏段，那是高频乐器串进人声轨，不是人声。

6. **验收**：输出文件存在；`ffprobe` 时长与源一致（分离）或等于剩余段总长（裁剪）；`trim_silence.py` 报告的段表与实际听到的空白对得上；试听确认人声段无金属音、无伴奏残留，拼接处无爆音。

## 关键判断

表里的档位是 2026-11 的常用组合。分离模型换代快（同一数据集上 vocals SDR 一年能涨 1 dB 以上），源带宽 ≥ 18 kHz、要批量跑或产物要交付时，先按 [模型选型核对](references/model-selection.md) 查一次当前权重；14–16 kHz 的窄带宽源按默认档跑即可。

| 情况 | 选择 | 代价 |
| --- | --- | --- |
| 只要伴奏/人声两轨 | `--two-stems=vocals -n htdemucs` | 默认档，质量与耗时平衡 |
| 源只有 12–16 kHz 带宽（低码率转存） | 仍用 `htdemucs`，别上 `htdemucs_ft`/RoFormer | 高频已被砍掉，重模型补不回来；先按 [源品质核验](references/quality-check.md) 确认 |
| 值得等，要更干净 | `-n htdemucs_ft` | 约 4 倍耗时 |
| 5 分钟 MP3，高品质 | 2 轨 BS-RoFormer（MLX/audio-separator）；4 轨 `htdemucs_ft` | 单曲几十秒到分钟级；只听 320kbps MP3 即可 |
| RoFormer 人声发薄、发尖 | 换 Mel-Band RoFormer 或其 fullness 调优权重 | 音色更平滑，SDR 略低；对照与数字口径见 [模型选型核对](references/model-selection.md) |
| 5 分钟 MP3，超高品质 | 2 轨 `BS-Roformer-SW.ckpt`（MLX/audio-separator）；4 轨 `htdemucs_ft` + shifts=2 | 相对 `htdemucs_ft` 再翻倍；只听 320kbps MP3 即可，MP3 源有损 |
| 存档 / 进 DAW / 继续处理 | `--flac`（16-bit 足够） | 体积约为 MP3 的 3–4 倍；不恢复源损失 |
| 只听后分发 | `--mp3 --mp3-bitrate 320` | 从 FLAC 母版转一次，别反复转 |
| 要鼓、贝斯、钢琴等 | `-n htdemucs_6s` | 六轨模型，乐器分离弱于专用模型 |
| Apple Silicon，想最快 | `demucs-mlx`（4 轨）或 `mlx-audio-separator`（2 轨/RoFormer） | 需 macOS 26.2+ 才吃 M5 矩阵单元；包较新，先小样本对照 |
| 只需快速试听、能接受残留 | ffmpeg 中置相消 `-af "pan=stereo\|c0=c0-c1\|c1=c1-c0"` | 几十秒出结果，人声残留明显，低频与混响受损 |

耗时取决于设备。这里的 `x 实时` 指处理速度是播放速度的 x 倍（1× = 边播边算，5:02 用 33 秒即 10.5×），换算与 RTF 见 [环境与依赖](references/environment.md#性能与资源)。CPU 基准（Apple M5 16GB、torch 2.15、`htdemucs`）：30 秒片段推理 13 秒，加约 2.5 秒模型加载共 15.5 秒，约 2.6× 实时（≈0.4× 音频时长）；5 分钟的歌约 2–3 分钟。同一台机器切到自动 MPS（demucs 4.1.0）：5:02 的曲目推理 33 秒（≈10.5× 实时，进度条约 10 seconds/s），含模型加载共 1:13，FLAC 与 MP3 源基本同量级；换 MLX `BS-Roformer-SW`（6 轨）跑 5 分钟级曲目 1–2 分钟（首跑 2:00，热跑 0:59）。上述耗时均在启用低电量模式时测得，未与正常模式对照，正常供电下应更快。对比数据与 M5 注意事项见 [环境与依赖](references/environment.md#apple-silicon-加速)。

估时用 30 秒片段先跑一遍，别拿长任务的总时长当基准：机器休眠、合盖、降频都会让 wall-clock 失真，进度条里的 `x seconds/s` 才是推理速度的可靠指标。实测比上述量级慢几倍时，先查是否休眠或线程被限，再考虑换更省的模型。

## Apple Silicon 加速（可选）

Demucs 4.1+ 的 MPS 已比 CPU 快一个数量级。MLX 路线不只是更快，也是质量升级的入口：2 轨 BS-RoFormer 的 vocals SDR 比 `htdemucs` 高约 3 dB，代价是多了模型权重下载与首次转换。

- **4 轨，最快**：`pip install demucs-mlx`，然后 `demucs-mlx song.mp3`。输出 4 个 stem，没有 `--two-stems` 快捷方式。
- **2 轨或 RoFormer**：`pip install mlx-audio-separator`，然后 `mlx-audio-separator song.mp3`。默认 BS-RoFormer 输出 vocals/instrumental；4 轨用 `-m htdemucs_ft.yaml`。
- **成熟回退**：`pip install "audio-separator[cpu]"`，Apple Silicon 走 PyTorch MPS + ONNX CoreML，模型覆盖更广但比 MLX 慢。

MLX 要 macOS 26.2+ 才能用上 M5 的 GPU Neural Accelerators；旧系统仍能跑，只是不吃矩阵单元。两个 MLX 包比 Demucs 年轻，M5 上先拿 30 秒片段用 `mlx-audio-separator` 与 `demucs-mlx` 各跑一遍对照，再决定是否批量。

**M5 16GB + macOS 26.2+**：默认用 Demucs 4.1+ 的 MPS；要用 MLX，4 轨用 `demucs-mlx --batch-size 1`，2 轨或长文件用 `mlx-audio-separator --chunk_duration 300`。`htdemucs_ft` 整包和长文件 BS-RoFormer 在 16GB 上容易触发换页，先分块/降 batch；具体参数见 [环境与依赖](references/environment.md#m5-16gb-预设)。

## 环境与依赖

- ffmpeg ≥ 5 且含 `libmp3lame`。ffmpeg 9 已移除 `-filter_complex_script`，脚本改用内联 `-filter_complex` 字符串。
- Python 3.10–3.13；demucs 4.1 带 torch 2.x，占磁盘约 1.5GB（含 wheel 缓存前）。
- `numpy` 要单独确认：部分安装组合不会自动带上，缺了在启动时报 `ModuleNotFoundError: No module named 'numpy'`。
- 设备：`cpu` / `cuda`；Demucs 4.1+ 在 Apple Silicon 自动使用 MPS，不需要 `-d mps`，也不要固定 `-d cpu`。旧版 Demucs 或 MPS 报错时才回退 CPU。MLX 原生加速见 [环境与依赖](references/environment.md#apple-silicon-加速)。
- 模型每个约 84MB，缓存在 `scripts/fetch_model.py --dir` 指定的目录，删目录即卸载。
- `scripts/check_audio_quality.py` 需要 numpy（demucs 环境已带），解码与响度都走 ffmpeg，不需要 torch。

平台差异、镜像与代理、内存和磁盘估算见 [环境与依赖](references/environment.md)；症状到处理的对照表见 [排障](references/troubleshooting.md)。

## 自检

- [ ] 分离命令真实跑完，退出码为 0，两个产物文件都存在
- [ ] 分离前量过源的有效带宽（`check_audio_quality.py` 有 `ceiling` 与 `verdict` 两行），模型档位与带宽匹配
- [ ] 选型前按 [模型选型核对](references/model-selection.md) 看过当前权重；结论里写明模型版本、评测数据集与检索日期
- [ ] Apple Silicon 上未固定 `-d cpu`；追求速度时按“Apple Silicon 加速”选 MPS 或 MLX，并记录实际后端
- [ ] 裁剪前跑过 `--dry-run`，段表与预期空白段一致（前奏/间奏/尾奏是否都命中）
- [ ] 裁剪结果时长等于剩余段总长，误差在 0.1s 内
- [ ] 拼接处有淡变，无明显爆音；阈值剪过头时回退 `--threshold-db` / `--pad`
- [ ] 未试听的结论不写成"听感已验证"
