# Web 运行配方与故障表

> 何时读：Step 2。根据 `arena_unpack.py` 的框架指纹选一节。**默认走静态链，只看效果不改代码就不起 dev。**

## 后端选择：node 首选，python 仅备选

- 有 node 就用 node（标准库手写静态服务即可，零依赖）：响应快约 7 倍、可自带 `/api` 状态接口、可发 `no-store` 杜绝旧页缓存、默认独占绑定不会同端口重复起。
- `python3 -m http.server` 只在没 node 的机器上备选：无状态接口、无 `no-store`（浏览器可能缓存旧页）、自带 `SO_REUSEADDR`（同端口重复起不报错，探针也识别不出）。
- 提醒用户装 Node.js 18+（`node --version` 确认），这是一次性投入、长期收益。

## 静态预览链（默认）

```sh
cd <项目目录>
npm install
npm run build
npx serve dist          # 默认 http://localhost:3000；或 python3 -m http.server 8000
# vite 项目也可用：npm run preview （默认 http://localhost:4173）
```

验证：`curl -s -o /dev/null -w "%{http_code}" http://localhost:PORT` 期望 200。

服务进程必须与当前会话解耦（独立进程 / `nohup` / 系统服务），随会话结束一起死的后台任务不算"保留运行"——用户下次打不开地址时先查这个。

## 改代码才 dev（Vite/Next/Vue）

```sh
npm run dev             # 后台启动；Vite 默认 5173，Next 默认 3000
```

- 指定端口：`npm run dev -- --port 5174`（被占时用）。
- Next 首次启动慢（编译），等 `Ready` 再验 200。

## 单文件导出（发给别人看）

```sh
npm i -D vite-plugin-singlefile
```

`vite.config.ts` 加 `plugins: [viteSingleFile()]` 后 `npm run build`，`dist/index.html` 即单文件，双击即开。限制：`public/` 大图不内联（外链，离线裂图）；路由只能 hash 模式。

## 静态页（无 package.json，有 index.html）

```sh
python3 -m http.server 8000
# 或：npx serve .
```

纯展示页可直接浏览器打开 `index.html`，但有模块导入/fetch 时必须走 http 服务。

## 多项目端口分配（批量对比用）

按目录扫描顺序从 5173 起顺延（5173/5174/5175…），`arena_compare.py` 自动分配并写进入口页。先探活再写地址，不要臆测端口。

长期展出不要 N 个服务：给各项目构建配 `base: './'` 后，把 dist 搬到同一服务根的子目录，一台静态服务覆盖全站（入口页改相对链接，端口与探活逻辑全部删除）。临时看才用多端口。

## 故障表

| 现象 | 先查 |
| --- | --- |
| `EADDRINUSE` 端口被占 | 换 `--port`，不要杀未知进程 |
| `npm install` 失败 | `node -v`（Vite 5+ 要 Node ≥18）；`npm config get registry` 看源；删 `node_modules` + lock 重装只限一次 |
| 白屏但 200 | 看浏览器控制台报错；多为 base 路径或 API 地址问题，记入报告不深修 |
| `vite: command not found` | 依赖没装好，回上一步 |

## 截图验证（条件允许）

跑起来后可用 `frontend-design` 的 `scripts/screenshot.mjs` 截三断点（跨 skill 调用，路径按本机实际安装位），截图存预览报告旁。
