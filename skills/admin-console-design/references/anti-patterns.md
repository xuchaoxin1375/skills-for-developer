# 控制台反例（Legacy 对照）

来源：sonnet `src/dashboard/Legacy.tsx`（刻意反例，注释即缺陷清单）+ sonnet `docs/03` 传统 vs 改进 +
fable/gpt 各"避免"条目。评审控制台先跑本表，命中"传统"列任一条即阻断。

## 传统四缺陷（Legacy.tsx 顶部注释逐条对应）

| # | 传统反例（Legacy 实现） | 后果 | 改进（本 skill 规范落点） |
|---|---|---|---|
| 1 | 侧栏固定 220px，无折叠/无抽屉（`w-[220px] flex-none`） | 窄屏内容被挤压 | `shell-sidebar.md` 状态机：rail 56 + peek 覆盖 + <768 抽屉 |
| 2 | 表格强制 `w-[900px]` min-width | 页面级横向滚动 | `tables.md`：表卡内 `overflow-x:auto` + <640 切卡，页面永无横滚 |
| 3 | 表单：无 label（placeholder 当标签）、单行硬排、`disabled={!valid}` 置灰提交代替校验、错误只在顶部笼统一条（`Error: invalid input`）、不聚焦首错、无粘性操作栏、无未保存提醒 | 用户不知道缺什么、错在哪个字段；输入易丢 | `forms.md`：可见 label + 两级校验 + 汇总 + 首错聚焦 + ActionBar + dirty 守卫 |
| 4 | 保存成功只有顶部 `Saved.`，无通知、无回行高亮 | 成功无感，用户会重复提交 | Toast live + 回列表高亮行 |

## 传统 vs 改进速查（sonnet `docs/03`）

| 传统 | 改进 |
|---|---|
| 置灰提交代校验 | 可点提交 → 汇总 Alert → 首错聚焦 → 保留输入 |
| placeholder 当标签 | 可见 label + hint/error `aria-describedby` 关联 |
| 顶部一条笼统错误 | 一字段一可行动消息（哪里错+为什么+如何改） |
| 顶部一次性提示 | 字段行内错 + 汇总 + Toast（成功5s/错误8s） |
| 无离开保护 | dirty JSON 比对 + 站内守卫 + beforeunload |
| 危险按钮与主操作同排 | 底部独立危险区 + 二次确认 + 高风险输名 |
| 固定宽侧栏/固定宽表格 | rail/peek/drawer 状态机 + 表自滚 + 切卡 |
| 仅 hover 入口 | 键盘/触屏等价路径 + 常驻按钮 |

## 用法

- 新建：写完先对照本表自查一遍，四缺陷一个都不许出现。
- 改版：拿本表当"保留举证"清单——旧设计每条命中都要给出不改的代价理由，答不上来就按改进列重做。
