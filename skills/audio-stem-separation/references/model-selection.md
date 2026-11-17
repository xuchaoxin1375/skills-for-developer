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

以下数字来自公开页面（MVSEP 的算法页与榜单、MUSDB18-HQ 榜单、ZFTurbo 模型表），**不同行的数据集不同，只作档位参考，不可直接相减**；过期后按上面的入口重查。

| 模型 / 权重 | vocals SDR | instrumental SDR | 说明 |
| --- | --- | --- | --- |
| `htdemucs`（800 首额外训练，MUSDB） | 8.93 | — | 默认档基线，速度快 |
| `htdemucs_ft`（MUSDB） | 9.20 | — | 4 个专家网络，约 4 倍耗时 |
| SCNet XL IHF（MUSDB / Multisong） | 11.42 / 9.68 | 8.19 / 6.48 均值为全轨 | 4 轨单权重，需 SCNet 后端 |
| MelBand RoFormer（Kim / kim_ft_unwa） | 11.21–12.6 / 12.4 | 17.0 级 | 2 轨，生态最成熟 |
| BS-Roformer viperx（MDX23 榜） | 11.75–11.92 | 16.3–17.0 | `model_bs_roformer_ep_317_sdr_12.9755.ckpt` 等 |
| BS Roformer（Multisong 2025.07） | 11.89 | 18.20 | MVSep 微调 |
| BS Roformer 124 bands（Multisong 2026.07） | 12.33 | 18.64 | 比基础版慢数倍，部分渠道付费 |
| BS PolarFormer（Synth 2026.05） | 14.03（Synth 口径） | 13.73 | 新架构，换 fullness 分档 |

结论：源带宽够时，2 轨 RoFormer 的收益（约 +3 dB vocals SDR）远大于从 `htdemucs` 换 `htdemucs_ft`（约 +0.3 dB）。

## 怎么落地

- 通用：`pip install "audio-separator[cpu]"`，先 `--list_models` 看当前权重名，再 `-m <model> --output_format FLAC`。Apple Silicon 走 MPS，模型覆盖最广。
- MLX：`mlx-audio-separator -m <model>`（2 轨），或 `demucs-mlx`（4 轨）；权重从 HuggingFace 拉，国内先设 `HF_ENDPOINT`。
- 上机前算两笔账：内存峰值（16GB 机器上整包 RoFormer 容易换页，用 `--chunk_duration`）与单曲耗时；先 30 秒片段对照 `htdemucs` 的同一段。
- 结论里写清：模型名与权重版本、评测数据集、检索日期、哪些是本机实测、哪些只是公开数据。
