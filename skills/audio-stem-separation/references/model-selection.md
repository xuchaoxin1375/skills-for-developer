# 模型选型核对

音频分离模型一年换一代：同一份 MUSDB18-HQ 上，`htdemucs` 的 vocals SDR 约 8.9 dB，2026 年的 BS-RoFormer 系权重能到 11.9–12.4 dB，在听感上是“伴奏里还有残响”和“干净”的差别。SKILL.md 里的模型表只是起点，动手前花几分钟核对现状，尤其是源本身就是无损或 320k 的时候。

## 什么时候值得查

- 源有效带宽 ≥ 18 kHz（无损、320k），模型的差距能听出来。
- 要批量处理，或产物是要交付的成品。
- 距上次确认超过半年。
- 源只有 12–16 kHz 带宽、只是自己试听一版：按默认 `htdemucs` 跑，不必追新。

## 查哪里

| 入口 | 能拿到什么 | 注意 |
| --- | --- | --- |
| `audio-separator --list_models --list_format json` | 本机即时可用的模型清单，含 stem 与 SDR | 装了就查；清单随包更新 |
| `mlx-audio-separator --list_models` | MLX 已转换的权重 | 部分新权重滞后于上游 |
| MVSEP 的 algorithms 页与 news | 同曲目（Multisong/Synth）SDR、fullness/bleedless | 模型更新最快，也最多 |
| ZFTurbo `Music-Source-Separation-Training` 的 `docs/pretrained_models.md` | 社区权重与 MUSDB 分数 | 权重来源，不是榜单 |
| Demucs / SCNet / mlx-audio-separator 的 release 与模型卡 | 官方新版本、许可与训练数据 | 训练数据常不公开 |
| 公开榜单（MUSDB18-HQ 等） | 横向对比 | 只能同数据集比 |

## 判据

- 看 **vocals / instrumental 分项 SDR**，不看总平均；总平均由鼓和贝斯主导，跟人声提取关系不大。
- 只在同一数据集内比较：MUSDB18-HQ test 与 MULTISONG 的数差 1–2 dB，不能相减。
- 2026 年起公开评测补了 fullness / bleedless（伴奏漏多少人声、人声被削掉多少），比 SDR 更贴近听感；有这两项时优先看。
- 最后一步永远是本机 30 秒 A/B：M 系列上 2 轨 RoFormer 跑 5 分钟曲目约 1–3 分钟，成本比读表格高不了多少。

## 2026-11 快照

数字来自公开页面（MVSEP 的算法页与榜单、MUSDB18-HQ 榜单、ZFTurbo 模型表），检索日期 2026-11-17。**数据集写在同一列里，只可同列相比**；“公开可下”指本地能拿到权重，拿不到的不必为它折腾。

| 模型 / 权重 | 数据集 | vocals | instr. | 公开可下 |
| --- | --- | --- | --- | --- |
| `htdemucs`（800 首额外数据） | MUSDB | 8.93 | — | 是（MIT） |
| `htdemucs_ft` | MUSDB | 9.20 | — | 是（MIT） |
| SCNet XL IHF | MUSDB | 11.42 | — | 权重无许可声明 |
| MelBand（Kimberley Jensen） | Multisong | 11.01 | 17.32 | 是 |
| MelBand（Bas Curtiz / 2024.08） | Multisong | 11.18 | 17.49 | 是 |
| MelBand（Becruily deux） | Multisong | 11.35 | 17.51 | 是 |
| MelBand（unwa big beta v5e / becruily vocals） | Multisong | 10.55–10.59 | 16.86–16.90 | 是，人声 fullness 调优版 |
| BS-Roformer（viperx 系） | MDX23 榜 | 11.75–11.92 | 16.3–17.0 | 是 |
| **BS-Roformer-SW**（6 轨，折 2 轨） | Multisong | 11.30 | 17.50 级 | 是，666MB，许可未知 |
| BS Roformer（2025.07） | Multisong | 11.89 | 18.20 | 否（MVSep 侧） |
| BS Roformer 124 bands（2026.07） | Multisong | 12.33 | 18.64 | 否（付费，数倍耗时） |
| Ensemble（2025.06） | Multisong | 11.93 | 18.23 | 否 |

结论：源带宽够时，2 轨 RoFormer 的收益（约 +3 dB vocals SDR）远大于从 `htdemucs` 换 `htdemucs_ft`（约 +0.3 dB）；但“第一”的权重多数拿不到，本地实际可选的是 BS-Roformer-SW 与 Mel-RoFormer InstV7n 这一档。

## Mel-Band 与 BS-RoFormer 怎么选

Mel-RoFormer 的“最强”是 2024 年那一代的结论，2026 年已被 BS 系超过（同表 11.0–11.35 对 11.89–12.33）。它仍值得试的理由在架构而不是总分：

- **同等训练数据下 vocals 更强**：论文（arXiv:2310.01809）在 MUSDB18-HQ 上测，Mel 比 BS 高 0.43 dB（L=6）与 0.58 dB（L=9），原因是 Mel 尺度对语音建模更友好。
- **音色更平滑**：论文原话是“更平滑的人声、更一致的响度”；BS 那篇自己承认输出偏“锐利、雾感少”。所以 0.6–0.9 dB 的总分差距可能被音色偏好抵消。
- **fullness 调优版换走向**：unwa big beta v5e、becruily vocals 这类把 fullness 拉到 20.7 左右、SDR 降到 10.5。觉得 BS 人声偏薄偏干时，先试这几个。

判断顺序：先跑 BS 系（SW），人声发薄或发尖再换 Mel 系或 Mel 的 fullness 版，不要只看排名。

## 数字口径陷阱

同一个 ckpt 会有一串互相不能比的分数。以 viperx 1296/1297 为例：

| 来源 | 1296 | 1297 |
| --- | --- | --- |
| 文件名标注 | 12.9628 | 12.9755 |
| audio-separator 独立评测（40 首，BSS Eval v4） | 12.10 | 11.77 |
| ZFTurbo 的 Multisong 口径 | 无 | 10.87 |

文件名里的数字只是训练者贴的标签，不是结果；两个来源的排序甚至相反。引用时写清数据集与评测方法，跨表相减一律不作数。MVSEP 也提示部分评测曲目可能进过训练集。

## 本地能跑什么

| 路线 | 权重 | 体积 | 备注 |
| --- | --- | --- | --- |
| `mlx-audio-separator` | BS-Roformer-SW | 666MB | 6 轨，折出 vocals/instrumental；MLX 原生 |
| `mlx-audio-separator` | Mel-RoFormer InstV7n | 870MB | 2 轨，音色平滑，作对照 |
| `audio-separator` | 上表任意公开 ckpt | 200MB–1GB | 走 PyTorch MPS，模型覆盖最广 |
| `mlx-audio-separator` | ZFTurbo Mel vocals v1 | 64MB | **别用它判断 RoFormer**：对应原始权重 SDR 仅 8.42 |

## 怎么落地

- 通用：`pip install "audio-separator[cpu]"`，先 `--list_models` 看当前权重名，再 `-m <model> --output_format FLAC`。Apple Silicon 走 MPS，模型覆盖最广。
- MLX：`mlx-audio-separator -m <model>`（2 轨），或 `demucs-mlx`（4 轨）；权重从 HuggingFace 拉，国内先设 `HF_ENDPOINT`。
- 上机前算两笔账：内存峰值（16GB 机器上整包 RoFormer 容易换页，用 `--chunk_duration`）与单曲耗时；先 30 秒片段对照 `htdemucs` 的同一段。
- 结论里写清：模型名与权重版本、评测数据集、检索日期、哪些是本机实测、哪些只是公开数据。
