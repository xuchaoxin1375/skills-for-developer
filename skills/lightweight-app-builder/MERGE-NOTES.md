# 融合说明（取舍决策记录）

来源：`designing-software-development-skills-glm5.3f.zip`（下称 GLM）与
`designing-software-development-skills-qwen3.8m.zip`（下称 Qwen）的竞技场项目包。
只保留 skill 本体，演示用 Vite 壳（`src/`、`index.html`、`package*.json` 等）已剔除。
出处细节只记在此文件，不进 `SKILL.md` frontmatter（运行时零价值，不占触发上下文）。

## 目录结构（agentskills.io 一层深，v2.1.0 共 12 篇 references）

```text
lightweight-app-builder/          # skill 根（本目录，含 SKILL.md）
├── SKILL.md                      # 主流程（融合版，~230 行，≤500 行规范）
├── MERGE-NOTES.md                # 本文件：取舍与优化记录
├── references/                   # 按需一次读一篇
│   ├── decision-matrix.md        # ★GLM：形态判定优先级表 + 决策树 + 判定红线
│   ├── requirement-intake.md     # ★Qwen：6 轴问题库 + 术语翻译表 + 追问技巧
│   ├── scripts-automation.md     # ★GLM：PEP723 + 定时三平台 + 可靠性四件套
│   ├── cli-and-tui.md            # 融合：GLM 骨架 + Qwen 严格模式/配置位置/交叉编译/TUI要点
│   ├── web-app.md                # 融合：GLM 骨架 + Qwen Go embed/token/合规（PWA 压表）
│   ├── desktop-hybrid.md         # 融合：GLM 骨架 + Qwen 成本告知/四框架表/系统集成清单
│   ├── hybrid-core-shell.md      # ★Qwen：内核三纪律 + 四语言布局 + 错误映射（sidecar 标进阶）
│   ├── packaging-distribution.md # 融合：Qwen 签名链/install.sh/CI 为骨 + GLM 光谱规则/命令表/九勾
│   ├── engineering-standards.md  # ★GLM：目录骨架 + 配置日志错误 + 质链 + CI 最小集
│   ├── quality-gates.md          # ★Qwen：G1-G5 闸门 + 工具链表 + 发布前 14 项
│   ├── prompt-recipes.md         # ★GLM：七段骨架 + 提问模板 + 好坏对照（已删拆分元讨论）
│   └── case-walkthroughs.md      # ★GLM 独有：三完整案例（Qwen 无）
├── assets/                       # 可复制模板（Qwen 独有，GLM 无）
│   ├── decision-record.md        # 方案确认单 / ADR 模板（Step 4 直接复制）
│   └── prompt-templates.md       # 用户侧 5 模板 A–E（从零 / 定形态 / 加功能 / 打包 / 迁移）
└── scripts/                      # 可执行脚本（两者各一，互补保留）
    ├── recommend.py              # ★GLM：7 问形态推荐器（零依赖，交互/--batch）
    └── preflight.sh              # ★Qwen：工具链体检（--form/--lang/--mirror/--json，exit 0/1/2）
```

## 取舍决策（融合时）

| 冲突点 | 采用 | 理由 |
| --- | --- | --- |
| skill 名 builder vs blueprint | builder | 动词性更强，触发描述更完整，生态兼容好 |
| 目录 `skills/` 复数 vs `skill/` 单数 | skill 根直放（本目录即 skill） | 合 agentskills.io 规范；整目录拷贝即安装 |
| 流程骨架 6 步 vs 5 阶段 | 6 步为骨，5 阶段语义并入 | GLM 有两人工确认点更可执行；Qwen 分诊/代决策/求确认/落地/交付映射到各 Step |
| 形态判定：优先级命中 vs 打分 | 优先级命中为主 + 红线否决 | 优先级表可执行性更强；Qwen 4 条红线是 GLM 缺的硬约束 |
| 技术栈表版本精度 | GLM 版（含数据锚点）+ Qwen 次选列 | GLM 可直接执行，Qwen 补分支 |
| 工程规范 vs 质量闸门 | 两者并存 | 红线管日常，闸门管发布，职责正交 |
| prompt-recipes vs prompt-templates | 并存 | 前者给 agent，后者给用户复制，对象不同 |

## 优化记录（v2.1.0，融合后审计整改）

1. **description 645→约330字符**：删"现代化"、8词触发堆砌、`compatibility` 非标准字段、`merged-from` 出处（移至此文件）。只留"做什么 + 何时用 + 一句 Not for"。
2. **四对重叠文档压成四篇**（16→12 篇）：`form-cli`→并入 `cli-and-tui`；`form-web`→并入 `web-app`；`form-desktop-gui`→并入 `desktop-hybrid`；`packaging-signing-delivery` 与 `packaging-distribution` 对调骨架后合并，原文件删除。路由表取消"主 + 补充"双读模式。
3. **删竞技场残留**：`prompt-recipes` 整节"一 skill 还是多 skill"（skill 设计元讨论）；`ssh -L` 长例换成一句话原则。
4. **压广度噪音**：七框架表→四行 + 一行"其他"；PWA 整节→3 行表；商店渠道→"进阶"小节；sidecar 标"进阶可跳过"。
5. **防腐烂**：`gh-proxy.com` 硬编码泛化为"当前可用的镜像代理（引用前实测）"，仅 install.sh 骨架注释保留一处示例。
6. **修自相矛盾**：Step 4"需移动端 → Tauri 2 / Flutter"改为超出范围声明；`desktop-hybrid` 内移动端宣传口径同步清除。
7. **轻量可判定化**：`SKILL.md` 适用边界新增一句话定义（运维复杂度低）+ 六维轻量/非轻量对照表；命中右侧触发"只给建议 + 优先拆轻量原型"。对照表放主文件不另开参考文档（范围判定发生在分诊前，且避免 12 篇再膨胀）。
8. 未改动其他 references/assets/scripts 正文，知识无损。
