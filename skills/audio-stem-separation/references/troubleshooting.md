# 排障

## 症状对照

| 症状 | 原因 | 处理 |
| --- | --- | --- |
| 启动后长时间没有任何进度，日志里反复 `HEAD https://huggingface.co/...` → `Retrying` | demucs 4.x 先向 HF 取 bag 配置，HF 不通 | 用 `fetch_model.py` 建本地仓库并传 `--repo <目录>`；或设 `HF_ENDPOINT` 走镜像 |
| `ModuleNotFoundError: No module named 'numpy'` | demucs 的依赖没把 numpy 带全（安装裁剪或 user site 混装） | `python -m pip install numpy`，用同一解释器再验 `python -c "import numpy, torch; print(numpy.__version__, torch.__version__)"` |
| `Unrecognized option 'filter_complex_script'` | ffmpeg 9 移除了该选项 | 改用 `-/filter_complex <文件>`，或把滤镜串直接内联给 `-filter_complex`（本 skill 的脚本已内联） |
| `demucs: command not found` | venv 没激活，或装到了别的解释器 | 用 `python -m demucs ...` 调用，避免依赖 PATH |
| `Torch not compiled with CUDA enabled` | 装的是 CPU 版 torch，却传了 `-d cuda` | 换 CUDA 版 wheel 或改 `-d cpu` |
| `-d mps` 报未知设备 | 旧版 Demucs 没有 MPS 后端，或设备名不被接受 | Demucs 4.1+ 去掉 `-d` 让它自动选 MPS；旧版或 MPS 报错时用 `-d cpu` |
| Apple Silicon 上分离很慢 | 命令固定了 `-d cpu`，没用上自动 MPS | 去掉 `-d cpu` 重跑；仍慢再按 [环境与依赖](environment.md#apple-silicon-加速) 上 MLX |
| 分离过程像是卡住，进度条几分钟不动 | CPU 推理本身慢，或机器休眠/降频、CPU 配额被限 | 看 `ps` 里 python 的 CPU 占用：占用高就是算得慢，给它时间；占用低或时间跳变则查休眠与降频（macOS 合盖会暂停进程） |
| 实测耗时比 0.4× 音频时长慢好几倍 | 期间机器休眠、降频，或拿了被打断任务的总时长当基准 | 以进度条 `x seconds/s` 判断真实速度；重新用 30 秒片段测，必要时 `caffeinate -i` 后复测 |
| 用 `conda run -n ...` 跑 demucs 看不到任何输出 | `conda run` 默认缓冲子进程输出 | 加 `--live-stream`，或直接调用环境里的 `python -m demucs` |
| 输出时长比源短或长几秒 | mp3 容器时长含编码帧填充，与解码后样本数不同 | 用解码时长对比（`ffmpeg -i x.mp3 -f null -` 的 time），差 <0.2s 可忽略 |
| 裁剪后时长对不上 | 段表用了不同采样率的时间基准，或 `atrim` 边界重叠 | 以 `--dry-run` 段表累计值为准，检查是否有重叠段 |

## 分离质量

- **伴奏里仍有人声**：`htdemucs` 对和声、叠加人声分离有限，换 `htdemucs_ft`（慢约 4 倍）或 `mdx_extra` 对比。
- **伴奏发闷、几乎没有高频**：源本身只有 13–16 kHz 带宽（低码率转存），不是分离算法的问题。先按 [源品质核验](quality-check.md) 量一次，再换带宽更高的源。
- **人声里有金属音/水声**：模型对混响重、音域低的段落容易出伪影，先把 `--shifts` 调大（默认 1，调到 5 质量略升、耗时倍增），或改用伴奏轨中置相消的混合结果。
- **结果左右声道异常**：源本身是单声道或相位异常时分离会失真，先 `ffprobe` 确认 `channels`。

## 静音裁剪调参

阈值按这首歌的电平定，换歌要重新看段表。

| 参数 | 默认 | 调大的效果 | 调小的效果 |
| --- | --- | --- | --- |
| `--threshold-db` | -50 | 更多段落算作空白（-40 更激进） | 只剪真正的数字静音，-60 更保守 |
| `--min-silence` | 1.0 | 只剪长间奏，乐句停顿保留 | 短停顿也剪，节奏更紧但可能剪碎语感 |
| `--pad` | 0.2 | 空白两侧留更多余量，衔接更自然、剪得少 | 剪得更干净，但容易切到气口和尾音 |
| `--min-keep` | 1.0 | 中间零散小块并入剪切，段数更少 | 保留更多短促片段，可能出现孤立残句 |

- **剪完还有长空白**：先 `--dry-run` 看该段是否被判为保留，多半是底噪高于阈值，调高 `--threshold-db`。
- **人声轨前奏多出十几秒很轻的段落**：多半是高频乐器串进人声的泄漏（电平比正式段落低 15 dB 以上）。默认阈值下它会整段保留；不要为去掉它把 `--threshold-db` 调到 -30，那会把正常乐句的换气也剪成空白，段数反而翻倍。
- **气口被切、乐句断裂**：调大 `--pad` 到 0.3–0.5，或调大 `--min-silence` 只处理长间奏。
- **拼接处有爆音**：脚本默认在每个内部边界加 15ms 淡入淡出；仍有可听到的跳变时增大淡变时长，或检查是否有重叠段导致波形不连续。

## 对轨与混音

`--mode cut` 会改变时间轴，剪过的音轨不能再和原伴奏逐帧对齐。要做卡拉OK对轨或重新混音时：保留 `--mode mute` 版本（时间轴不变，空段音量归零），或用未裁剪的 `vocals` 原始输出。
