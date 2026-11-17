---
name: audio-stem-separation
description: 从歌曲或音频里分离人声与伴奏（提取 BGM、去人声、卡拉OK、采样），并清理分离后音轨中的空白段。覆盖 Demucs 安装与离线模型准备、CPU 耗时取舍、ffmpeg 静音裁剪与三平台差异。用户要求提取伴奏、去人声、人声分离、做卡拉OK版，或说分离后有大段空白需要剪掉时使用；纯转码、剪辑拼接、变速变调、降噪修复不适用。
---

# 音频人声/伴奏分离与空段清理

## 适用范围

- 从一首歌提取伴奏（BGM）或人声轨：翻唱、卡拉OK、采样、配音替换。
- 分离出来的音轨有大段空白（纯伴奏段落、间奏、尾奏），需要剪成连续片段。
- 不适用：纯转码、剪辑拼接、变速变调、降噪/修复、多轨混音母带，这些用 ffmpeg 直接完成即可。

## 最短路径

前置：ffmpeg（编解码与裁剪）、Python 3.10–3.13、demucs（带 torch）。三平台安装与网络细节见 [环境与依赖](references/environment.md)。

1. **预检**：`ffmpeg -version` 有输出且带 `libmp3lame`；`python3 -V` 在 3.10–3.13 之间。3.14 装不上 torch，换成 3.11/3.12 的解释器或 conda 环境。

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

4. **分离**（默认只分人声/伴奏两轨，320kbps mp3）：

   ```bash
   demucs --repo ~/.cache/demucs-models -n htdemucs --two-stems=vocals \
          --mp3 --mp3-bitrate 320 -d cpu -o out/ song.mp3
   ```

   产物在 `out/htdemucs/song/{vocals,no_vocals}.mp3`：`no_vocals` 是伴奏，`vocals` 是人声。

5. **需要连续人声时裁剪空白段**（先 `--dry-run` 看段表，确认再执行）：

   ```bash
   python scripts/trim_silence.py out/htdemucs/song/vocals.mp3 --dry-run
   python scripts/trim_silence.py out/htdemucs/song/vocals.mp3 \
          --output vocals-trim.mp3 --mode cut
   ```

   `--mode mute` 保留原时间轴只把空段音量归零，用于还要和伴奏对轨的场景；`cut` 会移除空段，时间轴随之改变。

6. **验收**：输出文件存在；`ffprobe` 时长与源一致（分离）或等于剩余段总长（裁剪）；`trim_silence.py` 报告的段表与实际听到的空白对得上；试听确认人声段无金属音、无伴奏残留，拼接处无爆音。

## 关键判断

| 情况 | 选择 | 代价 |
| --- | --- | --- |
| 只要伴奏/人声两轨 | `--two-stems=vocals -n htdemucs` | 默认档，质量与耗时平衡 |
| 值得等，要更干净 | `-n htdemucs_ft` | 约 4 倍耗时 |
| 要鼓、贝斯、钢琴等 | `-n htdemucs_6s` | 六轨模型，乐器分离弱于专用模型 |
| 只需快速试听、能接受残留 | ffmpeg 中置相消 `-af "pan=stereo\|c0=c0-c1\|c1=c1-c0"` | 几十秒出结果，人声残留明显，低频与混响受损 |

耗时取决于设备：本机实测（Apple M5、torch 2.15 CPU）5:39 的歌用 `htdemucs` 约 37 分钟（≈6.5× 实时）；有 CUDA 的机器通常 1–2 分钟。没有 GPU 时先判断用户能否等，不能等就走上面的中置相消或先做一小段试听。

## 环境与依赖

- ffmpeg ≥ 5 且含 `libmp3lame`。ffmpeg 9 已移除 `-filter_complex_script`，脚本改用内联 `-filter_complex` 字符串。
- Python 3.10–3.13；demucs 4.1 带 torch 2.x，占磁盘约 1.5GB（含 wheel 缓存前）。
- `numpy` 要单独确认：部分安装组合不会自动带上，缺了在启动时报 `ModuleNotFoundError: No module named 'numpy'`。
- 设备只支持 `cpu` / `cuda`；Apple Silicon 没有 MPS 后端，不要传 `-d mps`。
- 模型每个约 84MB，缓存在 `scripts/fetch_model.py --dir` 指定的目录，删目录即卸载。

平台差异、镜像与代理、内存和磁盘估算见 [环境与依赖](references/environment.md)；症状到处理的对照表见 [排障](references/troubleshooting.md)。

## 自检

- [ ] 分离命令真实跑完，退出码为 0，两个产物文件都存在
- [ ] 裁剪前跑过 `--dry-run`，段表与预期空白段一致（前奏/间奏/尾奏是否都命中）
- [ ] 裁剪结果时长等于剩余段总长，误差在 0.1s 内
- [ ] 拼接处有淡变，无明显爆音；阈值剪过头时回退 `--threshold-db` / `--pad`
- [ ] 未试听的结论不写成"听感已验证"
