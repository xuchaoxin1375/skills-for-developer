# 源品质核验

分离质量的上限由源文件决定。下载来的“320k”“无损”经常是低码率转存：码率是真的，内容却停在 13–16 kHz，上更重的模型（`htdemucs_ft`、BS-RoFormer）也补不回被砍掉的高频。分离前先花十秒量一下带宽。

## 一条命令

```bash
python scripts/check_audio_quality.py song.flac                # 声明值 + 带宽 + 响度 + 判决
python scripts/check_audio_quality.py a.flac --compare b.mp3   # 两份文件是不是同一母带
python scripts/check_audio_quality.py a.flac b.mp3 --json      # 批量或交给别的脚本
```

输出四行要点：`declared`（容器声明的编码与码率）、`ceiling`（内容实际停在哪里、掉多陡、墙以上还剩多少）、`loudness`（EBU R128 与真峰值）、`verdict`（按下表给的判决）。脚本只依赖 ffmpeg/ffprobe 与 numpy，用装 demucs 的解释器跑即可。

```text
Mona Lisa.flac
  declared   flac 44100 Hz 2 ch 960 kbps 5:00.1
  ceiling    none up to 21 kHz (steepest 500 Hz drop 24.3 dB at 21.0 kHz)
  loudness   -9.8 LUFS, true peak -0.0 dBFS
  verdict    no wall — no codec cliff; a gentle roll-off near 21 kHz is the master
```

## 怎么读判决

判据是“悬崖”（wall）：在 500 Hz 内电平塌掉多少 dB。真正的编码器低通是断崖，母带的低通是斜坡。

| 500 Hz 内塌陷 | 含义 | 典型来源 |
| --- | --- | --- |
| ≥ 40 dB，墙以上接近 -70 dB 以下 | 编码器硬低通（数字静音） | MP3/AAC/Opus |
| 25–40 dB | 灰区：可能是母带 20 kHz 低通，也可能是温和的编码器 | 320k 或老母带，需交叉验证 |
| < 25 dB | 没有编码器悬崖 | 真无损，或高码率无损式编码 |

墙的位置对码率：< 15 kHz 是低码率（96–128k，国内音乐 App “标准音质”常在 13–14 kHz，比标准 LAME 128k 的 16.5 kHz 还狠）；15–17.5 kHz 对应 128–160k；17.5–19.5 kHz 对应 192k；19.5–21 kHz 对应 320k/AAC。真 CD 抓轨到 22.05 kHz 才到 Nyquist。

结论只写实测值，不写“听着像无损”：频谱证明的是内容上限，不是听感。

## 三种会误判的情形

- **母带自己在 20 kHz 做了低通**：频谱和 320k 几乎一样（灰区）。判据是墙的陡度（≤ 30 dB/500 Hz 更像母带）和墙以上是否有数字静音；再拿同曲另一份文件做 `--compare`，或换一个来源交叉验证。
- **有损母带**：正规 CD 抓轨，但母带制作时就从有损源或加了低通的素材来。这种文件是真无损、频谱却像有损，任何阈值都会把它当假的，别急着否定文件。
- **噪声整形抖动填充**：转码后重新加抖动，会把墙以上的“数字静音”填成底噪，`floor` 不再低于 -70 dB，硬判决会失效。此时只能看陡度与对比另一份。

## 交叉验证与专用工具

- **同一母带的另一份文件**：`--compare` 对齐 100 ms 能量包络并给互相关系数。`r ≥ 0.95` 且偏移固定，说明是同一演奏同一母带的不同编码，选带宽最高的那份；`r` 低或偏移漂移，说明是不同版本或母带，不能互相替代。
- **flaccheck**（Rust 单文件，macOS/Linux/Windows 都有 5 MB 左右的构建，无运行时依赖）：除频谱外还查 MDCT 量化残差、预回声、joint stereo，给 `GENUINE`/`SUSPICIOUS`/`TRANSCODED`/`INCONCLUSIVE`。适合批量扫库。
- **FLAC Detective**（`pip install flac-detective`，带 numpy/scipy 依赖）：四档评分，输出更适合写报告。
- **Spek**（`brew install spek` / `apt install spek`）：只看图，判断靠人眼。看速度最快，批量不划算。

`flac -t` 只验数据完整性，验不出转码。

## 拿到结果之后

| 结论 | 动作 |
| --- | --- |
| 满带宽（到 21–22 kHz） | 自用留 B（`htdemucs`）；要交付或要更干净进 C（RoFormer） |
| 12–16 kHz 窄带宽 | 留在 B 档（`htdemucs`），不值得上重模型；分离结果的高频会同步发闷，别把它当成分离算法的问题 |
| 灰区（19.5–21 kHz） | 先找同曲更高带宽的版本；没有就按 320k 源处理，可进 C，但别当真无损 |
| 与另一份是同一母带 | 用带宽最高的那份做源，输出码率不必高于源的带宽 |
