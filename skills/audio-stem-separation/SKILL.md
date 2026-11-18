---
name: audio-stem-separation
description: 从歌曲或音频里分离人声与伴奏（提取 BGM、去人声、卡拉OK、采样），并对分离后的人声轨做精剪：剪空白段、主唱缺席时只剩伴唱/人声衬腔（vocalise/vocable）的段落。覆盖 Demucs 安装与离线模型准备、Apple Silicon MPS/MLX 与 CPU/CUDA 耗时取舍、ffmpeg 静音裁剪与三平台差异，以及分离前的源品质核验（码率虚标、假无损、有效带宽）。用户要求提取伴奏、去人声、人声分离、做卡拉OK版、判断下载的音频是不是真 320k/真无损，或说分离后有大段空白、伴唱/衬腔段需要剪掉时使用；与分离无关的纯转码、剪辑拼接、变速变调、降噪修复不适用。
---

# 音频人声/伴奏分离与精剪（空白段 / 伴唱衬腔）

## 适用范围

- 从一首歌提取伴奏（BGM）或人声轨：翻唱、卡拉OK、采样、配音替换。
- 分离出来的音轨有大段空白（纯伴奏段落、间奏、尾奏），需要剪成连续片段。
- 分离后的人声精剪：剪空白段，以及主唱缺席、只剩伴唱或人声衬腔（vocalise/vocable）的段落；判断依赖分离轨的声像与主唱/伴唱层次。
- 不适用：与分离无关的纯转码、剪辑拼接、变速变调、降噪/修复、多轨混音母带，这些用 ffmpeg 或 DAW 直接完成即可。

不熟悉采样率、码率、频谱截止、LUFS、SDR 这些参数时，先读 [音频概念速查](references/audio-basics.md)：它面向不常处理音频的读者，解释每个数字在说什么、哪些结论不能从标签得出。

## 先对齐：三个问题定套餐

分离不是越重越好，也不是越短越好：源、机器、用途不同，最合适的档位就不同。动手前先回答三个问题，再选套餐。

- **源带宽**：跑 `python scripts/check_audio_quality.py song.mp3` 看 `ceiling` 与 `verdict`，约十秒（需要 numpy，缺了脚本会提示安装）。这一步同时是预检的一部分。
- **机器**：按 [本机资源体检](../resource-inventory/SKILL.md) 的 `hardware` 组跑一次，看 OS 版本、Apple Silicon/CUDA、内存与磁盘；不要凭印象。
- **用途**：只是试听、自用，还是要交付成品或批量处理。

| 套餐 | 适用 | 做法 | 耗时 | 产物 |
| --- | --- | --- | --- | --- |
| **A 试听** | 先确认值不值得处理 | ffmpeg 中置相消 | 秒级 | 临时文件，不交付 |
| **B 标准** | 自用；源 ≤17.5 kHz；或只有 CPU | `htdemucs` 两轨 | CPU 约 2.6× 实时（5 分钟歌 2–3 分钟）；MPS 约 10× 实时 | 320k MP3 |
| **C 高质量** | 源 ≥18 kHz，且要交付/批量或 B 的伴奏残留不能接受 | BS-RoFormer（Apple Silicon）或 audio-separator | 5 分钟曲目 1–2 分钟（M5 16GB） | FLAC 母版 |

18–19.5 kHz 是边界带：自用留 B，要交付进 C。灰区（19.5–21 kHz）按 320k 源处理，同样按用途选，但别把它当真无损。源窄带就留在 B：12–17.5 kHz 的源上 C 也补不回高频，只会更慢。

三个横切选项与套餐独立：**输出格式**（只听 320k MP3 / 存档 FLAC）、**stem 数**（2 轨 / 4 轨 / 6 轨）、**裁剪模式**（`cut` 改时间轴 / `mute` 保对轨）。

选型不是一次性的：模型换代快（同一数据集上 vocals SDR 一年能涨 1 dB 以上），距上次确认超过半年、或要批量交付时，按 [模型选型核对](references/model-selection.md) 查一次当前权重。

## 精剪前对齐：文件、时间轴与剪什么

精剪不等于只剪静音。动手前先确认：

- **文件与时间轴**：处理源 stem、已精剪版，还是旧版？用户报的时间点基于哪个文件？
- **操作**：剪空白段、剪非静音段（伴唱/衬腔），还是保留主唱只去伴唱层？
- **范围**：只处理用户点名的段落，还是全轨扫同类段落？
- **输出**：新文件还是覆盖，命名与版本。

主观听感（“这段听着不好”）先出候选段表：源时间、当前成品时间、类型、建议；确认后再编码。术语也要先对齐：用户说“和声”时，确认是“伴唱/人声衬腔层”还是“和声音程/叠唱”，中文口语常混用；不要按字面直接剪。

识别方法、候选表与 cut map 见 [人声精剪](references/vocal-edit.md)。

## 最短路径（B 标准档）

适用：自用伴奏/人声，源带宽 ≤17.5 kHz，或机器只有 CPU。选了 B 档，下面六步就是完整流程；要更轻或更重，见后面的 A / C 档。

前置：ffmpeg（编解码与裁剪）、Python 3.10–3.13、demucs（带 torch）。三平台安装与网络细节见 [环境与依赖](references/environment.md)。

1. **预检**：`ffmpeg -version` 有输出且带 `libmp3lame`；`python3 -V` 在 3.10–3.13 之间。3.14 装不上 torch，换成 3.11/3.12 的解释器或 conda 环境。

   源带宽若还没按「先对齐」量过，现在补上：

   ```bash
   python scripts/check_audio_quality.py song.mp3
   ```

   判决为窄带就留在 B：13–16 kHz 就截止的源，上 `htdemucs_ft`/RoFormer 也补不回高频。满带宽且要交付，转 C 档。判决表、假无损与灰区处理见 [源品质核验](references/quality-check.md)。

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

4. **分离**（本套餐档位：`htdemucs` 两轨，320kbps mp3；换档见 C 档）：

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

   如果目标不是空白段，而是伴唱/人声衬腔段，不要用静音阈值去猜：先按 [人声精剪](references/vocal-edit.md) 扫描立体声相关度，确认主唱是否缺席，再决定剪掉、保留或分层。`trim_silence.py` 只处理低于阈值的空白，不会识别非静音的伴唱段。

6. **验收**：输出文件存在；`ffprobe` 时长与源一致（分离）或等于剩余段总长（裁剪）；`trim_silence.py` 报告的段表与实际听到的空白对得上；试听确认人声段无金属音、无伴奏残留，拼接处无爆音。

## A 试听档（更轻）

只想先听听分离效果，或判断这首歌值不值得处理时，用 ffmpeg 中置相消，几十秒出结果：

```bash
ffmpeg -i song.mp3 -af "pan=stereo|c0=c0-c1|c1=c1-c0" preview.wav
```

人声残留明显，低频与混响受损，只适合试听，不要当成品。要判断 C 档值不值得跑，拿同一段 30 秒与 B 档对照。

## C 高质量档（更重）

适用：源有效带宽 ≥18 kHz（无损、320k），且满足其一：产物要交付、要批量，或 B 档的伴奏残留不能接受。

- **Apple Silicon**：`mlx-audio-separator` + BS-Roformer-SW（6 轨折 2 轨），5 分钟曲目约 1–2 分钟（M5 16GB）；首次要把 `.ckpt` 转成 safetensors。完整命令与权重来源见 [模型选型核对](references/model-selection.md#mlx-实操路径2-轨实测)。
- **非 Apple Silicon**：`audio-separator` + 公开 ckpt，走 PyTorch MPS 或 CPU；模型覆盖最广，但比 MLX 慢，落地命令见 [模型选型核对](references/model-selection.md#怎么落地)。
- **不想换工具链**：把 B 路径的 `-n htdemucs` 换成 `-n htdemucs_ft`，只多约 0.3 dB 却要 4 倍耗时，只在赶时间且不愿装第二套环境时选。
- **人声发薄、发尖**：换 Mel-Band RoFormer 或其 fullness 调优权重，音色更平滑、SDR 略低，对照见 [模型选型核对](references/model-selection.md#mel-band-与-bs-roformer-怎么选)。

16GB 内存上整包 RoFormer 容易换页，长文件加 `--chunk_duration 300`；先拿 30 秒片段与 B 档同一段对照，再决定是否批量。产物默认 FLAC，分发时再转一次 320k MP3。

## 关键判断

套餐定下来后，剩下的判断多是横切选项与边界情形；档位选择见前面的套餐表。

| 情况 | 选择 | 代价 |
| --- | --- | --- |
| 源只有 12–16 kHz 带宽（低码率转存） | 留在 B，别上 C | 高频已被砍掉，重模型补不回来；先按 [源品质核验](references/quality-check.md) 确认 |
| 存档 / 进 DAW / 继续处理 | Demucs 用 `--flac`；MLX/audio-separator 用 `--output_format FLAC`（16-bit 足够） | 体积约为 MP3 的 3–4 倍；不恢复源损失 |
| 只听后分发 | Demucs 用 `--mp3 --mp3-bitrate 320`；C 档从 FLAC 母版转一次 | 别反复转码 |
| 要鼓、贝斯、钢琴等 | `-n htdemucs_6s`，或 `demucs-mlx` 4 轨 | 六轨模型，乐器分离弱于专用模型 |

耗时取决于设备。这里的 `x 实时` 指处理速度是播放速度的 x 倍（1× = 边播边算，5:02 用 33 秒即 10.5×），换算与 RTF 见 [环境与依赖](references/environment.md#性能与资源)。CPU 基准（Apple M5 16GB、torch 2.15、`htdemucs`）：30 秒片段推理 13 秒，加约 2.5 秒模型加载共 15.5 秒，约 2.6× 实时（≈0.4× 音频时长）；5 分钟的歌约 2–3 分钟。同一台机器切到自动 MPS（demucs 4.1.0）：5:02 的曲目推理 33 秒（≈10.5× 实时，进度条约 10 seconds/s），含模型加载共 1:13，FLAC 与 MP3 源基本同量级；换 MLX `BS-Roformer-SW`（6 轨）跑 5 分钟级曲目 1–2 分钟（首跑 2:00，热跑 0:59）。上述耗时均在启用低电量模式时测得，未与正常模式对照，正常供电下应更快。对比数据与 M5 注意事项见 [环境与依赖](references/environment.md#apple-silicon-加速)。

估时用 30 秒片段先跑一遍，别拿长任务的总时长当基准：机器休眠、合盖、降频都会让 wall-clock 失真，进度条里的 `x seconds/s` 才是推理速度的可靠指标。实测比上述量级慢几倍时，先查是否休眠或线程被限，再考虑换更省的模型。

## Apple Silicon 加速（可选）

Demucs 4.1+ 的 MPS 已比 CPU 快一个数量级。MLX 路线不只是更快，也是质量升级的入口：2 轨 BS-RoFormer 的 vocals SDR 比 `htdemucs` 高约 2.5–3 dB（两个数字来自不同数据集，只作量级参考），代价是多了模型权重下载与首次转换。

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
- `scripts/scan_vocal_layers.py` 只依赖 ffmpeg 与 Python 标准库，不需要 numpy；它输出宽声场候选段，不判定“一定是伴唱”。

平台差异、镜像与代理、内存和磁盘估算见 [环境与依赖](references/environment.md)；症状到处理的对照表见 [排障](references/troubleshooting.md)。

## 自检

- [ ] 已按「先对齐」的三问定下套餐（A/B/C），机器条件来自 `hardware` 组实测，而不是凭印象
- [ ] 分离命令真实跑完，退出码为 0，产物文件存在
- [ ] 分离前量过源的有效带宽（`check_audio_quality.py` 有 `ceiling` 与 `verdict` 两行），套餐与带宽匹配
- [ ] 选 C 档时按 [模型选型核对](references/model-selection.md) 看过当前权重；结论里写明模型版本、评测数据集、检索日期，以及哪些是本机实测
- [ ] Apple Silicon 上未固定 `-d cpu`；追求速度时按“Apple Silicon 加速”选 MPS 或 MLX，并记录实际后端
- [ ] 裁剪前跑过 `--dry-run`，段表与预期空白段一致（前奏/间奏/尾奏是否都命中）
- [ ] 裁剪结果时长等于剩余段总长，误差在 0.1s 内
- [ ] 拼接处有淡变，无明显爆音；阈值剪过头时回退 `--threshold-db` / `--pad`
- [ ] 精剪前确认了文件与时间轴（源 / 已精剪版），用户报的时间点能对应到具体文件
- [ ] 非静音段（伴唱/衬腔）先出候选段表；主唱缺席的衬腔段按用户偏好剪掉或确认保留，未用静音阈值代替判断
- [ ] 交付附源时间↔成品时间 cut map；未试听的判断（如“没有居中主唱”）标明来自测量而非试听
- [ ] 未试听的结论不写成"听感已验证"
