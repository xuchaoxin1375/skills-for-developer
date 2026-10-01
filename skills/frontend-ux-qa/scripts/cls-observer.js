// 监听并打印非用户触发的布局偏移及责任元素（粘贴到控制台，首屏前注入最佳）。
// 对应 catalog V-01~V-07；hadRecentInput 为 true 的偏移不计入 CLS。
new PerformanceObserver((list) => {
  for (const entry of list.getEntries()) {
    if (entry.hadRecentInput) continue; // 排除 500ms 内用户输入引起的合理偏移
    console.group(`CLS +${entry.value.toFixed(4)}`);
    for (const src of entry.sources ?? []) {
      console.log(src.node, {
        from: src.previousRect.toJSON(),
        to: src.currentRect.toJSON(),
      });
    }
    console.groupEnd();
  }
}).observe({ type: 'layout-shift', buffered: true }); // buffered:true 补首屏已发生条目
