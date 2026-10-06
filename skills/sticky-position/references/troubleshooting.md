# 失效排查详解

sticky 失效**不会抛任何错误**——元素只是像从未声明过一样滚走了。按下面的顺序排查，
绝大多数问题在前两步就能定位。

## 一、六类根因与修复

| # | 根因 | 机理 | 修复方式 |
|---|---|---|---|
| 1 | 缺少阈值（头号原因） | 目标轴 inset 全为 `auto`，声明合法但永不生效，表现如 relative | 补 `top: 0` 等；确认没被层叠中更低处的规则覆盖 |
| 2 | 祖先设了 overflow（第二大原因） | 祖先成为新滚动容器，劫持参照系，sticky 只在它内部粘滞，而它往往到不了那个位置 | 移除；或给祖先**设高度**使其真正滚动；或改用 `overflow: clip` |
| 3 | 父元素不够高 | 包含块与 sticky 等高，没有可移动空间 | 给父元素更多高度，或把 sticky 上移一层 DOM |
| 4 | Flex/Grid 拉伸 | 子项被 stretch 拉满父容器，等效于原因 3 | `align-self: flex-start`（Grid 用 `start`） |
| 5 | 父级高度陷阱 | `height: 100%`、`-webkit-fill-available` 等组合破坏粘性 | 改用 `min-height` 或明确高度来源 |
| 6 | 样式被覆盖 | 其他规则覆盖了粘性声明 | DevTools Computed 找实际覆盖规则，提高特异性 |

## 二、原因 2 展开：overflow 祖先最阴险

**典型翻车现场**：一切正常，直到你为某个需要横向滚动的兄弟元素（横滑卡片区）给 sticky 的
祖先加了 `overflow-x: hidden`——sticky 立刻失灵。更常见的是全局写法：
为消灭横向滚动条而写 `body { overflow-x: hidden }`，整页所有 sticky 一起失效
（这也是响应式项目里的高频反模式：掩盖了真正的溢出 bug，还顺手杀了 sticky；
正确做法是找出溢出元素并修复，确需裁切时用 `overflow-x: clip`）。

**机理**：overflow 创建了新的滚动容器/格式化上下文，sticky 改以它为粘滞参照。而且按规范，
**当一个轴的 overflow 是 hidden/auto/scroll 时，另一轴上的 `visible` 会被计算为 `auto`**，
所以 `overflow-x: hidden` 的实际计算值是 `hidden auto`，是一个货真价实的滚动容器。

**两条修复路线**：

- **方案 A（W3C CSSWG 讨论结论）**：给该祖先设置非默认 overflow 的同时**再给它设置高度**。
  祖先有了确定高度并真正成为滚动区域后，sticky 就名正言顺地"粘在它里面"。
- **方案 B（现代推荐）**：只想裁剪溢出、不想造出滚动容器时用 `overflow: clip`。
  裁剪效果与 `hidden` 相同，但完全禁用任何形式的滚动，因此不创建滚动容器，不劫持参照系。

**注意**：`hidden` 与 `clip` 不是一回事；"overflow 非 visible 的祖先一定劫持 sticky"并不精确，
**clip 是重要例外**。排查脚本会把 clip 也列出来，需人工甄别。

**别漏掉 contain**：`contain: paint`、`contain: layout` 等 CSS 容器性属性同样会劫持 sticky 的
包含块/上下文，复杂布局里要把它们一起纳入怀疑范围。

## 三、控制台脚本：六步自动诊断（直接粘贴运行）

下面脚本按六类根因逐项读取**真实计算样式**并给出结论，`clip` 会被正确识别为安全：

```js
// 用法：diagnoseSticky() 或 diagnoseSticky('.site-nav')
function diagnoseSticky(sel) {
  const el = document.querySelector(sel || '.sticky');
  if (!el) return console.warn('No sticky element. Try diagnoseSticky(".your-selector")');
  const tag = (n) => n.tagName.toLowerCase()
    + (n.id ? '#' + n.id : '') + ([...n.classList].slice(0, 2).map((c) => '.' + c).join(''));
  const ok = (pass, msg) => console.log((pass ? '✓ ' : '✗ ') + msg);
  const cs = getComputedStyle(el);

  // [1] 阈值
  const insets = ['top', 'right', 'bottom', 'left'].filter((k) => cs[k] !== 'auto');
  ok(!(cs.position === 'sticky' && !insets.length),
    '[1] 阈值: ' + (insets.map((k) => k + ' = ' + cs[k]).join(', ') || '全 auto → 永不粘住'));

  // [2] overflow 祖先：向上走到 html，区分 clip / 预期滚动口 / 真滚动容器 / 劫持
  let p = el.parentElement, settled = false;
  while (p && p !== document.documentElement) {
    const o = getComputedStyle(p);
    if (o.overflow !== 'visible') {
      const clipOnly = ['clip', 'visible'].includes(o.overflowX)
        && ['clip', 'visible'].includes(o.overflowY);
      if (clipOnly) { console.log('  [2] ' + tag(p) + ': overflow ' + o.overflow + ' → clip 只裁剪，安全'); }
      else {
        settled = true;
        const scrolls = p.scrollHeight > p.clientHeight + 1 || p.scrollWidth > p.clientWidth + 1;
        ok(scrolls, '  [2] ' + tag(p) + ': 新滚动容器，'
          + (scrolls ? '确实可滚（方案 A 成立）' : '根本不滚动 → 劫持！改 clip 或给高度'));
        break;
      }
    }
    p = p.parentElement;
  }
  if (!settled) console.log('  [2] 无非预期滚动容器 → 以视口为滚动口');

  // [3] 父级活动空间（内容盒高度 − sticky 高度）
  const par = el.parentElement, ps = getComputedStyle(par);
  const room = Math.round(par.clientHeight - parseFloat(ps.paddingTop)
    - parseFloat(ps.paddingBottom) - el.offsetHeight);
  ok(room > 1, '[3] 活动空间: ' + room + 'px' + (room <= 1 ? ' → 无空间可粘' : ''));

  // [4] Flex/Grid 拉伸（含 align-items 继承来的 stretch）
  if (/flex|grid/.test(ps.display)) {
    const as = cs.alignSelf;
    const stretched = as === 'stretch'
      || ((as === 'auto' || as === 'normal') && ['normal', 'stretch'].includes(ps.alignItems));
    ok(!stretched, '[4] 拉伸: align-self = ' + as + (stretched ? ' → 被拉满父容器' : ''));
  } else console.log('○ [4] 父非 Flex/Grid，跳过');

  // [5] 高度陷阱：父高被锁死但内容溢出 → 包含块提前结束
  const trapped = ps.height !== 'auto' && par.scrollHeight > par.clientHeight + 1;
  ok(!trapped, '[5] 高度陷阱: ' + (trapped
    ? '父高锁为 ' + ps.height + ' 但内容溢出 → 提前被推走' : '包含块完整包住内容'));

  // [6] 最终计算样式
  ok(cs.position === 'sticky', '[6] 计算样式: position = ' + cs.position
    + (cs.position === 'sticky' ? '' : ' → 被更高特异性规则覆盖'));
}
diagnoseSticky();
```

只想快速列出嫌疑祖先时，用第一节表格逐项人肉检查同样有效（John Kavanagh 五步法见第四节）。

## 四、John Kavanagh 五步检查法

肉眼翻查逻辑时按这五问走，比"逐条试修复"更快：

1. 先查 inset 值（目标轴上是否有非 `auto` 的 inset）。
2. 哪个祖先提供了滚动口（scrollport）？
3. 哪个盒子提供了包含块？
4. 到达包含块边界之前，sticky 元素是否还有移动空间？
5. 祖先上的 overflow、滚动与 contain 规则是否创建了与预期不同的上下文？

## 五、故障基线复现法

排查复杂布局时，先造一个**正常基线**再逐项注入故障，比在真实页面上盲猜高效：

1. 建一个最小复现：元素有 `top` 阈值、父级有活动空间、没有额外 overflow 祖先——它应当正常粘住。
2. 依次注入单一故障：`去掉 top` → `加祖先 overflow: hidden` → `父容器与元素同高` → `Flex 默认拉伸`。
3. 每次只改一个变量，确认哪一项能复现你看到的现象，再套用第一节对应的修复。
4. 修复后回到基线验证，避免"多个修复叠加掩盖了真因"。

## 六、排查时的常见误判

- **"我写了 sticky 但它滚走了"**：先看 Computed 里 `position` 是不是真的算成了 `sticky`，
  再看目标 inset。多数是原因 1 或 6。
- **"粘住了但被内容盖住 / 透出下面文字"**：不是失效，是缺背景或 z-index（第四节强制项 2）。
- **"能粘但永远不被推走"**：包含块被设得过大（父级包住了整页），检查 DOM 层级。
- **"只在某个容器里不粘"**：那个容器就是新滚动容器，回到原因 2。
