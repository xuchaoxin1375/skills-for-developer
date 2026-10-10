# 可运行交互示例

以下三个示例各自复制到 HTML 文件即可运行，脚本放在对应标记之后。数值是演示默认值；集成时换成项目令牌。布局、焦点和业务语义独立于动画。

## 原生弹窗：双向过渡、遮罩与焦点

选型：原生 dialog 负责模态与键盘，支持离散过渡时渐进增强。`close()` 立即提交关闭语义；退出期间保留显示不等于保留布局，退出配置与所需布局必须常驻。

`[open]` 仅承载可见状态（需要时包含 `display:flex/grid`）；排列、尺寸、内边距、溢出与内容不能随它移除。下面将布局放基础选择器；也可放稳定内层。不要在基础 dialog 上无条件写 `display:flex`，以免覆盖原生关闭隐藏规则。

```html
<button id="dialog-open" type="button">打开详情</button>
<dialog id="motion-dialog" class="motion-dialog" aria-labelledby="dialog-title">
  <h2 id="dialog-title">详情</h2>
  <p>关闭和 Esc 都可返回入口。</p>
  <div class="dialog-body">
    <section><h3>服务状态</h3><p>页面已就绪。窗口退出期间仍保留这段正文的宽度与换行。</p></section>
    <section><h3>操作说明</h3><p>标题、正文与操作区保持原有排列，关闭不等待动画结束。</p></section>
  </div>
  <div class="dialog-actions">
    <button id="dialog-close" type="button" autofocus>关闭详情</button>
  </div>
</dialog>
```

```css
.motion-dialog {
  box-sizing: border-box; width: min(32rem, calc(100vw - 64px));
  max-height: calc(100dvh - 48px); padding: 20px; overflow: hidden;
  flex-direction: column; gap: 12px; /* close 后仍保留，不放在 [open] */
  opacity: 0; translate: 0 8px;
}
.motion-dialog[open] { display: flex; opacity: 1; translate: 0 0; }
.motion-dialog h2, .motion-dialog h3, .motion-dialog p { margin: 0; }
.dialog-body { display: grid; gap: 12px; min-height: 0; overflow: auto; }
.dialog-actions { display: flex; justify-content: flex-end; flex: 0 0 auto; }
.motion-dialog::backdrop { background: rgb(0 0 0 / .35); opacity: 0; }
.motion-dialog[open]::backdrop { opacity: 1; }
/* 不支持或 reduce 时无过渡，dialog 仍按原生方式开关。 */
@media (prefers-reduced-motion: no-preference) {
  @supports (transition-behavior: allow-discrete) and (overlay: auto) {
    .motion-dialog, .motion-dialog::backdrop {
      transition: opacity var(--motion-exit, 150ms) ease-in,
        translate var(--motion-exit, 150ms) ease-in,
        display var(--motion-exit, 150ms) allow-discrete,
        overlay var(--motion-exit, 150ms) allow-discrete;
    }
    .motion-dialog[open], .motion-dialog[open]::backdrop {
      transition-duration: var(--motion-enter, 200ms);
      transition-timing-function: ease-out;
    }
    @starting-style {
      .motion-dialog[open] { opacity: 0; translate: 0 8px; }
      .motion-dialog[open]::backdrop { opacity: 0; }
    }
  }
}
```

```js
const dlg = document.querySelector('#motion-dialog');
const openButton = document.querySelector('#dialog-open');
const closeButton = document.querySelector('#dialog-close');
const dialogEvents = new AbortController();
let invoker = null;
openButton.addEventListener('click', () => {
  if (dlg.open) return;
  invoker = document.activeElement; // 在 showModal 前记录，而非关闭时
  dlg.showModal();
}, { signal: dialogEvents.signal });
closeButton.addEventListener('click', () => dlg.close(), { signal: dialogEvents.signal });
dlg.addEventListener('close', () => {
  if (dlg.open) return; // 忽略快速重新打开前排队的旧 close 事件
  const target = invoker?.isConnected && !invoker.disabled ? invoker : openButton;
  if (target.isConnected && !target.disabled) target.focus({ preventScroll: true });
}, { signal: dialogEvents.signal });
// 原生 Esc 走相同 close 事件；入口全被移除时，调用方提供页面级后备焦点。
function disposeDialog() {
  if (dlg.open) dlg.close();
  dialogEvents.abort();
  dlg.getAnimations({ subtree: true }).forEach(animation => animation.cancel());
}
```

## 按钮忙态：即时防重入、延迟指示与错误恢复

选型：业务忙态同步生效；指示延迟出现避免短任务闪烁。示例 job 用计时演示，并非服务端进度；集成时替换为真实请求并保留错误处理。

```html
<button id="busy-button" type="button">
  <span class="busy-spinner" hidden aria-hidden="true"></span>
  <span data-label>保存设置</span>
</button>
<label><input id="fail-job" type="checkbox">模拟失败</label>
<p id="job-status" role="status"></p>
```

```css
.busy-spinner { display: inline-block; width: 1em; height: 1em;
  border: 2px solid currentColor; border-top-color: transparent; border-radius: 50%; }
.busy-spinner[hidden] { display: none; }
@media (prefers-reduced-motion: no-preference) {
  .busy-spinner { animation: busy-turn .8s linear infinite; }
}
@keyframes busy-turn { to { transform: rotate(360deg); } }
```

```js
async function runBusy(button, busyLabel, job, delay = 300) {
  if (button.disabled || button.getAttribute('aria-busy') === 'true') return;
  const label = button.querySelector('[data-label]');
  const spinner = button.querySelector('.busy-spinner');
  const oldLabel = label.textContent;
  const oldBusy = button.getAttribute('aria-busy');
  button.disabled = true;
  button.setAttribute('aria-busy', 'true');
  const timer = setTimeout(() => {
    if (!button.isConnected) return;
    label.textContent = busyLabel; // 不拼 innerHTML，保留子节点与监听
    spinner.hidden = false;
  }, delay);
  try { return await job(); }
  finally {
    clearTimeout(timer);
    label.textContent = oldLabel;
    if (!spinner.hidden) spinner.hidden = true;
    button.disabled = false;
    if (oldBusy === null) button.removeAttribute('aria-busy');
    else button.setAttribute('aria-busy', oldBusy);
  }
}

const busyButton = document.querySelector('#busy-button');
const jobStatus = document.querySelector('#job-status');
const busyEvents = new AbortController();
busyButton.addEventListener('click', async () => {
  if (busyButton.disabled) return;
  const fail = document.querySelector('#fail-job').checked;
  jobStatus.textContent = '正在保存设置';
  try {
    await runBusy(busyButton, '正在保存设置', () => new Promise((resolve, reject) => {
      setTimeout(() => fail ? reject(new Error('示例保存失败，请重试')) : resolve(), 700);
    }));
    if (jobStatus.isConnected) jobStatus.textContent = '设置已保存';
  } catch (error) {
    if (jobStatus.isConnected) jobStatus.textContent = error.message;
  }
}, { signal: busyEvents.signal });
// 卸载：busyEvents.abort() 移除入口监听；在途 job 的 finally 仍恢复状态。
// 真实请求是否可取消由业务决定；组件销毁时按能力中止请求，避免写入失效视图。
```

## 下拉 disclosure：可打断退出与无动画收尾

选型：WAAPI 便于取消、反向和精确收尾；只补透明度，不动画高度。这里是展开链接区，使用 `aria-expanded/controls`；真正 ARIA menu 另需方向键和菜单焦点模型。

```html
<button id="disclosure-toggle" type="button" aria-expanded="false"
  aria-controls="disclosure-panel">更多入口</button>
<div id="disclosure-panel" hidden inert aria-hidden="true">
  <a href="#settings">设置</a>
  <a href="#history">历史记录</a>
</div>
```

```js
function createDisclosure(trigger, panel, { enter = 150, exit = 120 } = {}) {
  const events = new AbortController();
  const reduced = matchMedia('(prefers-reduced-motion: reduce)');
  let open = !panel.hidden;
  let generation = 0;
  let active = null;
  let disposed = false;

  async function setOpen(next) {
    if (disposed) return;
    const mine = ++generation;
    const from = panel.hidden ? 0 : Number.parseFloat(getComputedStyle(panel).opacity);
    active?.cancel();
    active = null;
    open = next;
    // 焦点先移出，再隔离关闭区域，避免聚焦在 aria-hidden 内容中。
    if (!open && panel.contains(document.activeElement)) trigger.focus({ preventScroll: true });
    trigger.setAttribute('aria-expanded', String(open));
    panel.inert = !open;
    panel.setAttribute('aria-hidden', String(!open));
    panel.style.opacity = open ? '1' : '0'; // 基础终态先落，动画仅视觉补偿
    const duration = open ? enter : exit;
    if (reduced.matches || typeof panel.animate !== 'function' || duration <= 0) {
      panel.hidden = !open;
      return;
    }
    panel.hidden = false; // 退出仍可见，但已不可交互
    const animation = panel.animate([{ opacity: from }, { opacity: open ? 1 : 0 }], {
      duration, easing: open ? 'ease-out' : 'ease-in'
    });
    active = animation;
    try { await animation.finished; }
    catch (error) { if (error.name !== 'AbortError') throw error; }
    finally {
      if (mine === generation && !disposed) {
        panel.hidden = !open;
        active = null;
      }
      animation.cancel();
    }
  }

  trigger.setAttribute('aria-expanded', String(open));
  panel.inert = !open;
  panel.setAttribute('aria-hidden', String(!open));
  trigger.addEventListener('click', () => void setOpen(!open), { signal: events.signal });
  panel.addEventListener('keydown', event => {
    if (event.key === 'Escape' && open) {
      event.preventDefault();
      void setOpen(false);
    }
  }, { signal: events.signal });
  const onPreferenceChange = () => void setOpen(open);
  reduced.addEventListener('change', onPreferenceChange);
  return {
    setOpen,
    dispose() {
      disposed = true;
      generation++;
      events.abort();
      reduced.removeEventListener('change', onPreferenceChange);
      active?.cancel();
      if (panel.contains(document.activeElement)) trigger.focus({ preventScroll: true });
      panel.hidden = true;
      panel.inert = true;
      panel.setAttribute('aria-hidden', 'true');
      panel.style.removeProperty('opacity');
      trigger.setAttribute('aria-expanded', 'false');
    }
  };
}

const disclosure = createDisclosure(
  document.querySelector('#disclosure-toggle'), document.querySelector('#disclosure-panel')
);
// 卸载时 disclosure.dispose()；不支持 WAAPI/reduce/零时长均直接落终态。
```

验证统一见 `performance-a11y.md`“进出场与忙态验证矩阵”：从按钮入口执行关闭、Esc、连点、失败、取消与减弱切换；确认状态与焦点，不只检查动画是否存在。
