// 找出所有造成横向溢出的元素并红框标记（粘贴到控制台）。
// 对应 catalog L 类排障；注意找出的多为受害者，真凶常为其父（不换行 flex 行），用决策树上溯。
(function findOverflow() {
  const docWidth = document.documentElement.clientWidth; // clientWidth 不含滚动条，对应 L-11
  const offenders = [];
  document.querySelectorAll('*').forEach((el) => {
    const rect = el.getBoundingClientRect();
    if (rect.width === 0) return; // 跳过隐藏元素
    if (rect.right > docWidth + 1 || rect.left < -1) { // 1px 容差防亚像素误报；同时捕左溢出
      offenders.push({ el, right: Math.round(rect.right), left: Math.round(rect.left) });
      el.style.outline = '2px solid red';
      el.style.outlineOffset = '-2px'; // 内描边，避免高亮引新溢出
    }
  });
  console.table(offenders.map((o) => ({
    tag: o.el.tagName.toLowerCase(),
    cls: o.el.className?.toString().slice(0, 40),
    left: o.left, right: o.right, viewport: docWidth,
  })));
  console.log(`视口宽度 ${docWidth}px，发现 ${offenders.length} 个溢出元素`);
})();
