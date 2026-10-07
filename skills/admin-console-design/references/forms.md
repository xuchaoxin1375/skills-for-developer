# 表单 / 设置 / 向导

为什么不禁用提交：三工程一致“保存可点→提交校验→汇总→首错聚焦→保留输入”，
置灰等于把缺什么藏起来，校验文案必须是一字段一可行动消息。

## 四形态

内联（行内新增/编辑，高亮卡片单例）/ 长表单（Create）/ 向导（AddSite 三步）/ 设置（一卡一决策）。

## Field 结构

`label(*/Optional)+control36px+hint/error(role=alert)+计数器`，`aria-invalid + aria-describedby(hint+error)`，
`noValidate + 纯函数 validateRecord`，文案公式：哪里错 + 为什么 + 如何改（给示例值如 192.0.2.1，CNAME 冲突指明已有 A 记录）。

- 标签可见，禁 placeholder 代标签；必填 `* aria-hidden + 顶部说明 + aria-required`，选填标 Optional；
  正确 type/inputMode/autoComplete，主机名 `autocapitalize=none spellCheck=false`；允许粘贴+规范化；窄屏输入 16px 但禁禁缩放。
- 布局：<640 单列按钮 `flex-col-reverse` primary 在上；640-1023 用 6 栅；≥1024 用 12 栅
  （例 Type2/Name4/Content6/Proxy4/TTL2/Comment12）；≥7 项分组，≥3 组加 ≥1024 右侧粘性大纲（scroll-margin+IO 高亮）。
- 控件：Switch(`role=switch`)即时+toast；2-4 互斥用 RadioCards（`:has(:focus-visible)` 整卡环）；多互斥用原生 Select；
  长文本 Textarea 字数；Tags Enter/逗号。

## 两级校验

首次不责备 → blur 单字段 → 已 touched 修改同步 → 提交全量 + 汇总 Alert + 首错 focus+scrollIntoView（scroll-padding 防遮）+ 保留已填。
`requestAnimationFrame` 聚首错；550ms 模拟异步 + saving 防重 + `aria-busy`；重复（type|name|content）与上限（如 200）抛错；
服务端冲突（CNAME 独占）映射回字段，否则进汇总。

## 联动与草稿

- Type 切 label/placeholder；互斥强制（如 MX/TXT 关 proxied）并说明原因；条件字段出现才校验，切换清不适用值；TXT 用 textarea。
- 新增每次 update 持久草稿（`edgelab.draft`），取消/关抽屉 Toast“草稿已保留”，成功清空；编辑仅实例内。
- 脏保护：JSON 比对 + 站内守卫单例 + beforeunload，保存即解；删除时清脏防幽灵拦截；Cancel 再 Edit 关窗弹 Discard（默认 Keep editing）。

## 设置页

一卡一决策，Footer 左状态右 Save（dirty 才启用）；Toggle 即时生效+toast；危险区底部独立红描边远离首屏，
二次确认，高风险输名确认但按钮可点（以校验说话）；离开 dirty 站内确认（默认焦“继续编辑”）+ beforeunload。

## 向导

线性进度可回退，Stepper `ol+aria-current=step`，窄屏 `Step 2 of 3:Plan`+进度；换步焦点到标题 `tabIndex=-1`；
Continue 步校验，最后 Review 汇总回改（dl+Change 链）；输入不丢 + 离开保护。

## 浮层与反馈

- Dialog：danger 动词主按钮 + 移动底部抽屉 + 焦点陷阱 + 高风险输名；Popover 非模态 + 视口夹取（<640 变底板）；
  Toast 右下 live polite（成功 5s/错误 8s/撤销 8s，可关）；表单内 success-banner + server-error(`role=alert`+focus) + draft-status。
- Modal 用原生 `dialog.showModal()+body overflow lock计数+backdrop点+portal`；Esc 关浮层并回焦点。
