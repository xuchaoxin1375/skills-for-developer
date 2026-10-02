#!/usr/bin/env python3
"""arena_compare.py —— 同目录多项目批量对比入口页。

用法:
    python scripts/arena_compare.py <目录> [--force] [--json]

行为:
    扫描目录下的 *.zip 与已解压项目（复用 arena_unpack 的指纹逻辑）；
    zip 解压到同目录的 <包名>/（已存在则复用，--force 才覆盖重解）；
    --no-extract 时不解压，未解压的包以“待解压”占位卡片出现在入口页（scan 按需解压后重建即转正）；
    按 5173 起顺延分配端口；生成 <目录>/index.html 入口页：
    卡片（名称、框架、明暗、规模、主题色条、组件数、运行命令、本地地址）
    + sticky 工具区（搜索、框架/来源/明暗/规模筛选、排序、计数、重置）。
    卡片链接可点的前提：各项目已按分配端口启动（见 web-run.md）。
    目录下已有非本工具生成的 index.html 时拒绝写入（--force 覆盖）。
    本工具生成的 index.html 首行带 <!-- arena-compare:generated --> 标记。
退出码: 0 正常；2 参数/目录错误/拒绝覆盖。
零依赖，只用标准库。
"""

from __future__ import annotations

import argparse
import html
import os
import re
import shutil
import sys
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from arena_unpack import fingerprint, suggest, unwrap  # noqa: E402

HEX_RE = re.compile(r"#(?:[0-9a-fA-F]{6}|[0-9a-fA-F]{3})\b")
MARKER = "<!-- arena-compare:generated -->"
CHROME_NAME = "_chrome.html"

# 页眉 chrome 内置默认（可移植回退）：同一应用把共用的 _chrome.html 放到对比目录或其上级，
# 重建即自动收敛；裸用（别处目录、无约定文件）则用此默认，保证零依赖可移植。
CHROME_DEFAULT = (
    "<style>.crumbs{font-size:13px;color:#555;padding-top:16px}"
    " .crumbs a{color:#5b4bff}</style>\n"
    '<nav class="crumbs" aria-label="面包屑"><a href="/">展览首页</a> / '
    '<span aria-current="page">项目对比</span></nav>'
)


def load_chrome(directory: str) -> str:
    """页眉 chrome 单一来源：<目录>/_chrome.html → 上级目录/_chrome.html → 内置默认。"""
    for cand in (os.path.join(directory, CHROME_NAME),
                 os.path.join(os.path.dirname(directory), CHROME_NAME)):
        try:
            with open(cand, encoding="utf-8") as f:
                frag = f.read().strip()
        except OSError:
            continue
        if frag:
            return frag
    return CHROME_DEFAULT


def theme_colors(root: str, fp: dict, limit: int = 6) -> list[str]:
    seen: list[str] = []
    for rel in fp.get("theme_files", []):
        p = os.path.join(root, rel)
        if not os.path.isfile(p):
            continue
        try:
            with open(p, encoding="utf-8", errors="ignore") as f:
                text = f.read(200_000)
        except OSError:
            continue
        for c in HEX_RE.findall(text):
            if len(c) == 4:  # #rgb 展开
                c = "#" + "".join(ch * 2 for ch in c[1:])
            c = c.lower()
            if c not in seen:
                seen.append(c)
            if len(seen) >= limit:
                return seen
    return seen


def tone_of(colors: list[str]) -> str:
    """按主题首色亮度判定明暗（无颜色信息时返回'未知'）。"""
    if not colors:
        return "未知"
    c = colors[0].lstrip("#")
    r, g, b = (int(c[i:i + 2], 16) / 255 for i in (0, 2, 4))
    return "深色" if 0.2126 * r + 0.7152 * g + 0.0722 * b < 0.4 else "浅色"


def dev_cmd(framework: str, port: int) -> list[str]:
    """点绿徽标要敲的命令：每个项目独立服务，监听 exactly 分配到的端口。"""
    if framework.startswith("Vite"):
        return ["npm install", f"npm run dev -- --port {port}"]
    if framework == "Next.js":
        return ["npm install", f"npm run dev -- -p {port}"]
    if framework == "VueCLI":
        return ["npm install", f"npm run serve -- --port {port}"]
    return []


def size_of(n: int) -> str:
    return "小型" if n < 10 else "中型" if n <= 20 else "大型"


def component_count(root: str) -> int:
    n = 0
    for dp, dns, fs in os.walk(root):
        dns[:] = [d for d in dns if d not in {"node_modules", "dist", "build", ".git"}]
        n += sum(1 for f in fs if f.endswith((".tsx", ".vue", ".jsx")))
    return n


def _dir_mtime(root: str) -> float:
    """源码最新 mtime（剪掉 node_modules/dist/build/.git，与 node newestMtimePruned 同口径）。"""
    latest = 0.0
    for dp, dns, fs in os.walk(root):
        dns[:] = [d for d in dns if d not in {"node_modules", "dist", "build", ".git"}]
        for f in fs:
            try:
                latest = max(latest, os.path.getmtime(os.path.join(dp, f)))
            except OSError:
                pass
    return latest


def built_info(directory: str, proj_root: str, name: str) -> tuple[str, bool]:
    """静态基线用的产物地址+是否过期：向上找 arena-apps/<名>/index.html，源码新于产物即过期。"""
    d = os.path.abspath(directory)
    for _ in range(4):
        cand = os.path.join(d, "arena-apps", name, "index.html")
        if os.path.isfile(cand):
            try:
                stale = _dir_mtime(proj_root) > os.path.getmtime(cand) + 1
            except OSError:
                stale = False
            return "/arena-apps/" + name + "/", stale
        nd = os.path.dirname(d)
        if nd == d:
            break
        d = nd
    return "", False


def collect(directory: str, force: bool, extract: bool = True) -> list[dict]:
    items: list[dict] = []
    skip = {"_compare", "_arena", "node_modules", "dist", "build", ".git"}
    seen: set[str] = set()
    for name in sorted(os.listdir(directory)):
        if name in skip:
            continue
        path = os.path.join(directory, name)
        if name.endswith(".zip") and os.path.isfile(path):
            base = os.path.splitext(name)[0]
            if base in seen:
                continue  # 同名已解压目录已收录，不重复计数
            dest = os.path.join(directory, base)
            if os.path.isdir(dest) and os.listdir(dest) and not force:
                print(f"复用已解压目录: {dest}")
            elif not extract and not (os.path.isdir(dest) and os.listdir(dest)):
                items.append({
                    "name": base,
                    "origin": "zip",
                    "origin_raw": "zip:" + name + "（未解压）",
                    "dir": dest,
                    "framework": "待解压",
                    "scripts": [],
                    "colors": [],
                    "tone": "未知",
                    "components": 0,
                    "size": "待解压",
                    "suggest": ["点本页工具条“检测新包”勾选，或运行 arena_manage.py 选择解压"],
                    "pending": True,
                })
                seen.add(base)
                continue
            else:
                if force and os.path.isdir(dest):
                    shutil.rmtree(dest)
                os.makedirs(dest, exist_ok=True)
                with zipfile.ZipFile(path) as z:
                    z.extractall(dest)
            root, origin = unwrap(dest), "zip:" + name
        elif os.path.isdir(path) and (
            os.path.exists(os.path.join(path, "package.json"))
            or os.path.exists(os.path.join(path, "index.html"))
        ):
            root, origin = unwrap(path), "dir:" + name
        else:
            continue
        fp = fingerprint(root)
        colors = theme_colors(root, fp)
        n = component_count(root)
        entry = {
            "name": os.path.basename(root),
            "origin": "zip" if origin.startswith("zip:") else "dir",
            "origin_raw": origin,
            "dir": root,
            "framework": fp["framework"],
            "scripts": fp["scripts"],
            "colors": colors,
            "tone": tone_of(colors),
            "components": n,
            "size": size_of(n),
            "suggest": suggest(fp),
        }
        items.append(entry)
        seen.add(entry["name"])
    return items


CARD = """
<section class="card" data-name="{name}" data-fw="{framework}" data-origin="{origin}"
  data-tone="{tone}" data-size="{size}" data-components="{components}" data-port="{port}" data-built="{built}" data-stale="{stale}">
<div class="cardhead">{selhtml}<h2>{name}</h2></div>
<div class="fw">{framework} · {tone} · {size}({components}组件)</div>
<div class="swatches">{swatches}</div>
<div class="cmd">{cmd}</div>
<div class="links"><span class="st" title="服务状态">●</span><span class="code">未知</span>{linkhtml}<span class="src">{origin_raw}</span></div>
{buildhtml}
{previewhtml}
</section>
"""

PAGE = MARKER + """
<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Arena 项目对比入口</title>
<style>
body{{font-family:system-ui,-apple-system,"PingFang SC","Microsoft YaHei","Noto Sans CJK SC",sans-serif;background:#f4f4f5;margin:0;padding:0 24px 24px;line-height:1.6}}
h1{{font-size:20px;padding-top:12px;margin:0 0 8px}}p.tip{{color:#555}}
.skip{{position:absolute;left:-9999px;top:0;background:#fff;padding:8px 12px;border-radius:8px}}
.skip:focus{{left:8px;top:8px;z-index:99;border:2px solid #5b4bff}}
a:focus-visible,button:focus-visible,input:focus-visible,select:focus-visible{{outline:2px solid #5b4bff;outline-offset:2px}}
.toolbar{{position:sticky;top:0;z-index:10;display:flex;gap:8px;flex-wrap:wrap;align-items:center;
  background:rgba(244,244,245,.94);backdrop-filter:blur(8px);padding:12px 0;margin:0 -24px;padding-left:24px;padding-right:24px}}
.toolbar input[type=search]{{flex:1;min-width:160px;padding:8px 10px;border:1px solid #ddd;border-radius:8px}}
.toolbar select,.toolbar button{{padding:8px 10px;border:1px solid #ddd;border-radius:8px;background:#fff}}
.toolbar button{{cursor:pointer}}
#count{{color:#555;font-size:13px;margin-left:auto}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(min(100%,300px),1fr));gap:16px;margin-top:16px}}
.card{{background:#fff;border-radius:8px;padding:16px;box-shadow:0 1px 3px rgba(0,0,0,.1);min-width:0}}
.cardhead{{display:flex;gap:8px;align-items:flex-start}}
.cardhead h2{{flex:1;min-width:0;font-size:15px;margin:0 0 8px;word-break:break-all}}
.cardhead .sel{{width:24px;height:24px;margin:0;flex:none;accent-color:#5b4bff}}
.stale-hint{{display:block;color:#92400e;font-size:13px;margin-top:6px}}
.fw{{color:#555;font-size:13px;margin-bottom:8px}}
.swatches{{display:flex;gap:4px;margin-bottom:8px;min-height:20px}}
.sw{{width:36px;height:20px;border-radius:4px;border:1px solid #ddd}}
.cmd{{font:12px ui-monospace,Consolas,monospace;background:#f4f4f5;padding:8px;border-radius:4px;white-space:pre-wrap;margin-bottom:8px}}
.links a{{color:#5b4bff}} .src{{color:#666;font-size:12px;margin-left:8px;overflow-wrap:anywhere}}
.st{{color:#6b7280;font-size:13px;margin-right:2px}} .st.on{{color:#15803d}} .st.off{{color:#dc2626}}
.devlink-off{{color:#4b5563;font-size:13px;text-decoration:none}}
.card .preview-btn{{width:100%;margin-top:6px}}
button:disabled{{opacity:.55;cursor:not-allowed}}
.preview-frame{{width:100%;height:360px;border:1px solid #ddd;border-radius:8px;margin-top:8px;background:#fff}}
.pv-hint{{color:#555;font-size:13px;background:#f4f4f5;border-radius:4px;padding:8px;margin-top:8px}}
.toolbar #batchmsg{{color:#555;font-size:13px}}
.pending-hint{{color:#92400e;font-size:13px}}
.buildlog{{display:none;font:12px ui-monospace,Consolas,monospace;color:#555;white-space:pre-wrap;
  max-height:96px;overflow:auto;background:#f4f4f5;border-radius:4px;padding:6px 8px;margin-top:6px}}
.code{{font:12px ui-monospace,Consolas,monospace;color:#555;margin-right:6px}}
.empty{{display:none;color:#555;padding:32px 0;text-align:center}}
.scanpanel{{margin-top:12px;background:#fff;border:1px solid #ddd;border-radius:8px;padding:12px 14px}}
.scanrow{{display:flex;gap:8px;align-items:center;padding:6px 0;border-bottom:1px solid #f0f0f0;font-size:13px}}
.st-NEW{{color:#1d4ed8;font-weight:600}} .st-STALE{{color:#92400e;font-weight:600}}
.st-OK{{color:#16a34a}} .st-ORPHAN{{color:#555}} .st-WARN{{color:#dc2626;font-weight:600}}
.scanbtns{{display:flex;gap:8px;margin-top:10px;flex-wrap:wrap;align-items:center;font-size:13px}}
#scanmsg{{color:#555}}
dialog{{border:1px solid #ddd;border-radius:8px;padding:16px;max-width:min(420px,90vw)}}
dialog::backdrop{{background:rgba(0,0,0,.35)}}
#cfm-msg{{margin:0 0 12px;font-size:14px;line-height:1.6}}
.cfm-btns{{display:flex;gap:8px;justify-content:flex-end}}
.cfm-btns button{{padding:8px 16px;border:1px solid #ddd;border-radius:8px;background:#fff;cursor:pointer;min-height:36px}}
#cfm-ok{{background:#5b4bff;border-color:#5b4bff;color:#fff}}
@media (max-height:30rem){{.toolbar{{position:static}}}}
</style></head><body>
<a class="skip" href="#grid">跳到项目列表</a>
{chrome}
<h1>Arena 项目对比入口（{n} 个）</h1>
<p class="tip">● 为各端口实时状态（每 5 秒刷新，需 node 预览服务同源 /api）。在线显示品牌色“本地打开”（可点，新窗口）；离线显示灰色“未启动”（先敲卡片命令起 dev）；无 /api（file 直开/python 后端）显示“未知”，链接保持原样。列表动态渲染，上传/解压后自动刷新（file 直开显示静态基线）。Vite 系可点“构建并预览”，产物落单服务 /arena-apps/ 直接看。“预览可见项”只展开当前筛选结果，逐卡懒加载；“构建可见项”按序逐个构建。卡片勾选（复选框）即批量范围：勾了按勾选来（筛选藏起来的也算），没勾才按可见项；“全选可见”一键勾上当前结果。有产物构建过显示“重新构建”，源码新于产物显示“产物过期”；重建覆盖旧产物，弹窗会点名。</p>
<div class="toolbar" role="search">
<input id="q" type="search" placeholder="搜索名称/框架…" aria-label="搜索">
<select id="f-fw" aria-label="框架筛选">{fw_opts}</select>
<select id="f-origin" aria-label="来源筛选">
<option value="">全部来源</option><option value="zip">来自压缩包</option><option value="dir">已解压目录</option>
</select>
<select id="f-tone" aria-label="明暗筛选">
<option value="">明暗不限</option><option>深色</option><option>浅色</option><option>未知</option>
</select>
<select id="f-size" aria-label="规模筛选">
<option value="">规模不限</option><option>小型</option><option>中型</option><option>大型</option>
</select>
<select id="f-sort" aria-label="排序">
<option value="port">按端口排序</option><option value="name">按名称排序</option><option value="components">按组件数↓</option>
</select>
<button id="f-reset" type="button">重置</button>
<button id="f-scan" type="button" title="检测本目录新增/更新的包">检测新包</button>
<button id="f-rebuild" type="button" title="调 compare --no-extract 重建本页">重建入口页</button>
<button id="f-preview" type="button" title="只展开当前筛选可见的卡片内联预览">预览可见项</button>
<button id="f-buildall" type="button" title="按可见顺序逐个构建（服务端一次一个）">构建可见项</button>
<button id="f-ckall" type="button" title="勾选当前筛选可见的卡片">全选可见</button>
<button id="f-cknone" type="button" title="清空全部勾选">清空选择</button>
<span id="selcount" role="status"></span>
<span id="batchmsg" role="status"></span>
<span id="count" aria-live="polite"></span>
</div>
<dialog id="cfm" aria-labelledby="cfm-msg"><p id="cfm-msg"></p>
<div class="cfm-btns"><button id="cfm-no" type="button">取消</button><button id="cfm-ok" type="button">确认</button></div>
</dialog>
<div class="scanpanel" id="scanpanel" hidden>
<div id="scanrows">尚未检测。</div>
<div class="scanbtns">
<button id="f-extract" type="button">解压选中</button>
<button id="f-selall" type="button" title="全选检测到的新增/可更新包">全选</button>
<button id="f-selnone" type="button" title="清空勾选">全不选</button>
<input type="file" id="f-upload" accept=".zip" aria-label="上传 zip 包">
<button id="f-uploadbtn" type="button" title="上传 zip 包到本目录">上传包</button>
<span id="scanmsg"></span>
</div>
</div>
<div class="grid" id="grid" tabindex="-1">{cards}</div>
<div class="empty" id="empty">没有匹配的项目，换条件试试。</div>
<script>
(function(){{
var grid=document.getElementById('grid'),empty=document.getElementById('empty'),
q=document.getElementById('q'),count=document.getElementById('count'),
fw=document.getElementById('f-fw'),origin=document.getElementById('f-origin'),
tone=document.getElementById('f-tone'),size=document.getElementById('f-size'),
sort=document.getElementById('f-sort');
var savedFw=null;
function saveFilter(){{
  try{{localStorage.setItem('arena-compare-filter',JSON.stringify(
    {{q:q.value,fw:fw.value,origin:origin.value,tone:tone.value,size:size.value,sort:sort.value}}));}}catch(e){{}}
}}
(function loadFilter(){{
  try{{
    var m=JSON.parse(localStorage.getItem('arena-compare-filter')||'null');
    if(!m)return;
    if(typeof m.q==='string')q.value=m.q;
    if(typeof m.origin==='string')origin.value=m.origin;
    if(typeof m.tone==='string')tone.value=m.tone;
    if(typeof m.size==='string')size.value=m.size;
    if(typeof m.sort==='string')sort.value=m.sort;
    if(typeof m.fw==='string'&&m.fw)savedFw=m.fw;
  }}catch(e){{}}
}})();
function apply(){{
  var kw=q.value.trim().toLowerCase(),n=0,
  cards=Array.prototype.slice.call(grid.querySelectorAll('.card'));
  cards.forEach(function(c){{
    var ok=(!fw.value||c.dataset.fw===fw.value)
      &&(!origin.value||c.dataset.origin===origin.value)
      &&(!tone.value||c.dataset.tone===tone.value)
      &&(!size.value||c.dataset.size===size.value)
      &&(!kw||(c.dataset.name+' '+c.dataset.fw).toLowerCase().indexOf(kw)>-1);
    c.style.display=ok?'':'none'; if(ok)n++;
  }});
  var vis=cards.filter(function(c){{return c.style.display!=='none';}});
  var key=sort.value;
  vis.sort(function(a,b){{
    if(key==='name')return a.dataset.name.localeCompare(b.dataset.name,'zh');
    if(key==='components')return (+b.dataset.components)-(+a.dataset.components);
    return (+a.dataset.port)-(+b.dataset.port);
  }});
  vis.forEach(function(c){{grid.appendChild(c);}});
  count.textContent='显示 '+n+' / '+cards.length;
  empty.style.display=n?'none':'block';
  saveFilter();
}}
[q,fw,origin,tone,size,sort].forEach(function(el){{el.addEventListener('input',apply);el.addEventListener('change',apply);}});
document.getElementById('f-reset').addEventListener('click',function(){{
  q.value='';fw.value='';origin.value='';tone.value='';size.value='';sort.value='port';apply();
}});
apply();
/* 包管理台2.0：列表动态渲染（/api/scan 全字段），解压/上传后重扫即刷新，不改页代码 */
var scanBtn=document.getElementById('f-scan'),rebuildBtn=document.getElementById('f-rebuild'),
panel=document.getElementById('scanpanel'),rowsBox=document.getElementById('scanrows'),
extractBtn=document.getElementById('f-extract'),
upFile=document.getElementById('f-upload'),upBtn=document.getElementById('f-uploadbtn'),
scanMsg=document.getElementById('scanmsg');
var PAGEDIR=location.pathname.replace(/\\/index\\.html$/,'').replace(/^\\//,'').replace(/\\/$/,'')||'.';
var CAPS={{}};
var OPEN={{}},HAVE_API=false;
var batchMsg=document.getElementById('batchmsg'),previewBtn=document.getElementById('f-preview'),
buildAllBtn=document.getElementById('f-buildall');
function sayBatch(s){{if(batchMsg)batchMsg.textContent=s;}}
var selCount=document.getElementById('selcount');
function updateSel(){{
  var n=grid.querySelectorAll('.sel:checked').length;
  if(selCount)selCount.textContent=n?('已选 '+n):'';
}}
function checkedCards(){{
  return Array.prototype.filter.call(grid.querySelectorAll('.card'),function(c){{
    var s=c.querySelector('.sel');return s&&s.checked;
  }});
}}
function scopeCards(){{
  /* 批量范围：勾了按勾选来（含被筛选藏起来的），没勾才按可见项 */
  var sel=checkedCards();
  if(sel.length)return {{cards:sel,mode:'已选'}};
  return {{cards:visCards(),mode:'可见'}};
}}
/* 确认/提示统一走原生 <dialog>（可 Esc、焦点自动返回触发元；一次只开一个） */
var cfmDlg=document.getElementById('cfm'),cfmMsg=document.getElementById('cfm-msg'),
cfmOk=document.getElementById('cfm-ok'),cfmNo=document.getElementById('cfm-no'),
cfmResolve=null,cfmLast=null;
function dialogMsg(msg,okLabel,alertOnly){{
  return new Promise(function(resolve){{
    if(cfmDlg.open){{resolve(false);return;}}
    cfmLast=document.activeElement;
    cfmMsg.textContent=msg;
    cfmOk.textContent=okLabel||'确认';
    cfmNo.style.display=alertOnly?'none':'';
    cfmResolve=resolve;
    try{{cfmDlg.showModal();}}catch(e){{cfmResolve=null;resolve(false);return;}}
    (alertOnly?cfmOk:cfmNo).focus();
  }});
}}
function dialogConfirm(msg,okLabel){{return dialogMsg(msg,okLabel||'确认',false);}}
function dialogAlert(msg){{return dialogMsg(msg,'知道了',true);}}
cfmOk.addEventListener('click',function(){{cfmDlg.close('ok');}});
cfmNo.addEventListener('click',function(){{cfmDlg.close('cancel');}});
cfmDlg.addEventListener('close',function(){{
  var v=cfmDlg.returnValue==='ok';
  cfmDlg.returnValue='';
  if(cfmResolve){{var r=cfmResolve;cfmResolve=null;r(v);}}
  if(cfmLast&&document.contains(cfmLast))cfmLast.focus();
}});
function disableBuildBtns(){{
  if(CAPS.build===false){{
    Array.prototype.forEach.call(grid.querySelectorAll('.build-one'),function(b){{
      b.disabled=true;b.title='本机缺包管理器，用 CLI 构建';    }});
    if(buildAllBtn){{buildAllBtn.disabled=true;buildAllBtn.title='本机缺包管理器，用 CLI 构建';}}
  }}
}}
var PORT0=5173;
(function(){{
  var ps=Array.prototype.map.call(grid.querySelectorAll('.card'),
    function(c){{return +c.dataset.port||0;}}).filter(Boolean);
  if(ps.length)PORT0=Math.min.apply(null,ps);
}})();
var LAST=[];
function esc(s){{return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}}
function buildable(fw){{return fw.indexOf('Vite')===0||fw==='Next.js'||fw==='VueCLI';}}
function renderCards(items){{
  LAST=items;
  grid.innerHTML='';
  items.forEach(function(it){{
    var sec=document.createElement('section');sec.className='card';
    sec.dataset.name=it.name;sec.dataset.fw=it.framework;sec.dataset.origin=it.origin;
    sec.dataset.tone=it.tone;sec.dataset.size=it.size;
    sec.dataset.components=it.components;sec.dataset.port=it.port;
    sec.dataset.built=it.builtUrl||'';
    sec.dataset.stale=it.builtStale?'1':'';
    var sw=it.colors.map(function(c){{
      return '<span class="sw" style="background:'+c+'" title="'+c+'"></span>';
    }}).join('')||"<span style='color:#666;font-size:12px'>未提取到主题色</span>";
    var cmd=esc((it.cmd||[]).join('；')||'—');
    var tail=it.pending
      ? '<button type="button" class="preview-btn extract-one" data-name="'+esc(it.name)+'">解压此包</button>'
        +'<span class="src">'+esc(it.origin_raw)+'</span>'
      : '<a class="devlink" href="http://localhost:'+it.port+'" target="_blank" rel="noopener noreferrer">本地打开 :'+it.port+'</a>'
        +'<span class="src">'+esc(it.origin_raw)+'</span>'
        +(it.builtUrl?'<a class="built-link" href="'+it.builtUrl+'" target="_blank" rel="noopener noreferrer" style="margin-left:6px">静态预览↗</a>':'');
    var pvBtn=(!it.pending)
      ? '<button type="button" class="preview-btn pv-toggle" aria-expanded="false">预览本项</button>'
        +'<div class="pv"></div>' : '';
    var buildBtn=((!it.pending&&buildable(it.framework))
      ? (function(){{
          var label=it.builtUrl?'重新构建':'构建并预览';
          var title=it.builtUrl
            ? '已有产物（可直接点静态预览）；重建将覆盖旧产物'
            : '构建后落到单服务 /arena-apps/ 下直接看，不起新端口';
          return '<button type="button" class="preview-btn build-one" data-name="'+esc(it.name)+'"'
            +' title="'+title+'">'+label+'</button>'
            +(it.builtStale?'<span class="stale-hint">产物过期（源码更新过），建议重建</span>':'')
            +'<div class="buildlog"></div>';
        }})()
      : '');
    var selBox=(!it.pending)
      ? '<input type="checkbox" class="sel" aria-label="选择'+esc(it.name)+'">' : '';
    sec.innerHTML='<div class="cardhead">'+selBox+'<h2>'+esc(it.name)+'</h2></div>'
      +'<div class="fw">'+esc(it.framework)+' · '+esc(it.tone)+' · '+esc(it.size)
      +'('+it.components+'组件)</div>'
      +'<div class="swatches">'+sw+'</div>'
      +'<div class="cmd">'+cmd+'</div>'
      +'<div class="links"><span class="st" title="服务状态">●</span>'
      +'<span class="code">未知</span>'+tail+'</div>'
      +buildBtn
      +pvBtn;
    grid.appendChild(sec);
  }});
  updateSel();
  var curFw=fw.value;
  var fws=[];items.forEach(function(i){{if(fws.indexOf(i.framework)<0)fws.push(i.framework);}});
  fws.sort();
  fw.innerHTML='<option value="">全部框架</option>'+fws.map(function(f){{
    return '<option>'+esc(f)+'</option>';}}).join('');
  if(fws.indexOf(curFw)>=0)fw.value=curFw;
  if(savedFw&&fws.indexOf(savedFw)>=0){{fw.value=savedFw;savedFw=null;}}
  var h1=document.querySelector('h1');
  if(h1)h1.textContent='Arena 项目对比入口（'+items.length+' 个）';
  disableBuildBtns();
  apply();
  poll();
}}
function rescan(){{
  return fetch('/api/scan?dir='+encodeURIComponent(PAGEDIR)+'&port0='+PORT0).then(function(r){{
    if(!r.ok)throw new Error('HTTP '+r.status);return r.json();
  }}).then(function(m){{HAVE_API=true;renderCards(m.rows);return m.rows;}},function(e){{HAVE_API=false;throw e;}});
}}
fetch('/api/health').then(function(r){{return r.json();}}).then(function(h){{
  CAPS=h.caps||{{}};
  if(!h.caps||!h.caps.extract){{scanBtn.disabled=true;scanBtn.title='需 node 预览服务（/api/scan）';}}
  if(!h.caps||!h.caps.rebuild){{rebuildBtn.disabled=true;rebuildBtn.title='缺 python 或 skill 路径，用 CLI 重建';}}
  disableBuildBtns();
}}).catch(function(){{
  scanBtn.disabled=true;rebuildBtn.disabled=true;
  scanBtn.title='需 node 预览服务';rebuildBtn.title='需 node 预览服务';
}});
function buildChecks(){{
  var actionable=LAST.filter(function(x){{return x.status==='NEW'||x.status==='STALE';}});
  if(!actionable.length){{rowsBox.textContent='无新增/可更新的包。';return;}}
  rowsBox.innerHTML='';
  actionable.forEach(function(x){{
    var lab=document.createElement('label');lab.className='scanrow';
    var cb=document.createElement('input');cb.type='checkbox';
    cb.checked=x.status==='NEW';cb.value=x.name;
    var st=document.createElement('span');st.className='st-'+x.status;st.textContent=x.status;
    lab.appendChild(cb);lab.appendChild(st);
    lab.appendChild(document.createTextNode(x.name+' — '+x.detail));
    rowsBox.appendChild(lab);
  }});
}}
scanBtn.addEventListener('click',function(){{
  panel.hidden=false;rowsBox.textContent='检测中…';scanMsg.textContent='';
  rescan().then(buildChecks).catch(function(e){{
    rowsBox.textContent='检测失败：'+e.message+'（需 node 预览服务）';
  }});
}});
extractBtn.addEventListener('click',async function(){{
  var names=Array.prototype.map.call(
    rowsBox.querySelectorAll('input:checked'),function(c){{return c.value;}});
  if(!names.length){{scanMsg.textContent='先勾选要解压的包。';return;}}
  if(!(await dialogConfirm('解压 '+names.length+' 个包到本目录？（STALE 会清目录重解）','解压')))return;
  scanMsg.textContent='解压中…';extractBtn.disabled=true;
  fetch('/api/extract',{{method:'POST',headers:{{'Content-Type':'application/json'}},
    body:JSON.stringify({{dir:PAGEDIR,names:names}})}})
    .then(function(r){{return r.json().then(function(m){{return {{http:r.status,body:m}};}});}})
    .then(function(x){{
      extractBtn.disabled=false;
      var bad=(x.body.results||[]).filter(function(r){{return !r.ok;}});
      if(bad.length){{scanMsg.textContent='部分失败：'+
        bad.map(function(r){{return r.name+'（'+r.error+'）';}}).join('；');return;}}
      scanMsg.textContent='解压成功 '+names.length+' 个，列表已刷新。';
      rescan().then(buildChecks);
    }}).catch(function(e){{extractBtn.disabled=false;scanMsg.textContent='请求失败：'+e.message;}});
}});
grid.addEventListener('click',async function(e){{
  var b=e.target&&e.target.closest?e.target.closest('.extract-one'):null;
  if(!b)return;
  var nm=b.getAttribute('data-name');
  if(!(await dialogConfirm('解压 '+nm+' 到本目录？','解压')))return;
  b.disabled=true;b.textContent='解压中…';
  fetch('/api/extract',{{method:'POST',headers:{{'Content-Type':'application/json'}},
    body:JSON.stringify({{dir:PAGEDIR,names:[nm]}})}})
    .then(function(r){{return r.json();}}).then(function(m){{
      var r0=(m.results||[])[0]||{{ok:false,error:'无返回'}};
      if(r0.ok)rescan();
      else{{b.disabled=false;b.textContent='解压此包';dialogAlert('解压失败：'+r0.error);}}
    }}).catch(function(e2){{b.disabled=false;b.textContent='解压此包';dialogAlert('请求失败：'+e2.message);}});
}});
function buildLog(card){{
  var l=card.querySelector('.buildlog');
  if(l)l.style.display='block';
  return l;
}}
grid.addEventListener('click',async function(e){{
  var b=e.target&&e.target.closest?e.target.closest('.build-one'):null;
  if(!b)return;
  var card=b.closest('.card'),nm=b.getAttribute('data-name');
  var hasBuilt=!!card.dataset.built,isStale=!!card.dataset.stale;
  var tip=hasBuilt
    ? ('重新构建 '+nm+'？已有产物将被覆盖'+(isStale?'（源码更新过，重建合理）。':'（源码没变的话，直接点“静态预览”更快）。'))
    : ('构建 '+nm+'？产物落到单服务 /arena-apps/ 下直接看，不起新端口。首次 install 会比较久。');
  if(!(await dialogConfirm(tip,hasBuilt?'重新构建':'构建')))return;
  b.disabled=true;var label=b.textContent;b.textContent='构建排队…';
  fetch('/api/build',{{method:'POST',headers:{{'Content-Type':'application/json'}},
    body:JSON.stringify({{dir:PAGEDIR,name:nm}})}})
    .then(function(r){{return r.json().then(function(m){{return {{http:r.status,body:m}};}});}})
    .then(function(x){{
      if(x.http===409){{b.disabled=false;b.textContent=label;
        dialogAlert('已有构建在跑，一次一个，稍后再试。');return;}}
      if(!x.body.ok){{b.disabled=false;b.textContent=label;
        dialogAlert('构建启动失败：'+(x.body.error||x.http));return;}}
      b.textContent='构建中…';
      var log=buildLog(card);
      var timer=setInterval(function(){{
        fetch('/api/build?id='+x.body.id).then(function(r){{return r.json();}}).then(function(j){{
          if(log)log.textContent=(j.logTail||[]).join('\\n');
          if(j.status==='done'){{
            clearInterval(timer);b.disabled=false;b.textContent=label;
            if(log)log.textContent=(j.logTail||[]).join('\\n');
            if(j.result&&j.result.url)card.dataset.built=j.result.url;
            var links=card.querySelector('.links');
            if(links&&!links.querySelector('.built-link')){{
              var a=document.createElement('a');a.className='built-link';
              a.href=j.result.url;a.target='_blank';a.rel='noopener noreferrer';
              a.textContent='静态预览↗';a.style.marginLeft='6px';
              links.appendChild(a);
            }}
          }} else if(j.status==='error'){{
            clearInterval(timer);b.disabled=false;b.textContent=label;
            if(log)log.textContent='构建失败：'+j.error+'\\n'+(j.logTail||[]).join('\\n');
          }}
        }}).catch(function(){{/* 下轮重试 */}});
      }},2000);
    }}).catch(function(e2){{b.disabled=false;b.textContent=label;dialogAlert('请求失败：'+e2.message);}});
}});
/* 卡片内预览：builtUrl（同源，最稳）> 在线 dev 端口 > 无 api 时乐观试 dev > 占位指引；收起即清 src */
function visCards(){{
  return Array.prototype.filter.call(grid.querySelectorAll('.card'),function(c){{
    return c.style.display!=='none'&&c.dataset.fw!=='待解压';
  }});
}}
function cardSrc(c){{
  if(c.dataset.built)return {{kind:'built',url:c.dataset.built}};
  if(OPEN[c.dataset.port])return {{kind:'dev',url:'http://localhost:'+c.dataset.port}};
  if(!HAVE_API&&c.dataset.port)return {{kind:'dev',url:'http://localhost:'+c.dataset.port}};
  return null;
}}
function setPreview(c,open){{
  var box=c.querySelector('.pv');if(!box)return false;
  var btn=c.querySelector('.pv-toggle');
  if(!open){{box.innerHTML='';if(btn)btn.setAttribute('aria-expanded','false');return true;}}
  var src=cardSrc(c);
  if(!src){{
    box.innerHTML='<div class="pv-hint">无可预览源：先点“构建并预览”（产物落单服务），或按卡片命令起 dev 再预览。</div>';
    if(btn)btn.setAttribute('aria-expanded','true');return 'hint';
  }}
  box.innerHTML='<iframe class="preview-frame" loading="lazy" title="'+esc(c.dataset.name)+' 预览" src="'+src.url+'"></iframe>';
  if(btn)btn.setAttribute('aria-expanded','true');return true;
}}
grid.addEventListener('click',function(e){{
  var b=e.target&&e.target.closest?e.target.closest('.pv-toggle'):null;
  if(!b)return;
  var card=b.closest('.card'),box=card.querySelector('.pv');
  setPreview(card,!(box&&box.firstChild));
}});
previewBtn.addEventListener('click',async function(){{
  var sc=scopeCards();
  var pool=sc.cards.filter(function(c){{return c.dataset.fw!=='待解压';}});
  if(!pool.length){{sayBatch(sc.mode==='已选'?'已选项中没有可预览项。':'没有可预览的可见项（待解压不参与）。');return;}}
  var opened=pool.filter(function(c){{var b=c.querySelector('.pv');return b&&b.firstChild;}});
  if(opened.length===pool.length){{pool.forEach(function(c){{setPreview(c,false);}});sayBatch('已收起 '+pool.length+' 项预览（'+sc.mode+'）。');return;}}
  var todo=pool.filter(function(c){{var b=c.querySelector('.pv');return !(b&&b.firstChild);}});
  if(todo.length>6&&!(await dialogConfirm('一次展开 '+todo.length+' 个预览会同时加载 '+todo.length+' 个页面，可能很卡。继续？','展开预览')))return;
  var hid=pool.filter(function(c){{return c.style.display==='none';}}).length;
  todo.forEach(function(c){{setPreview(c,true);}});
  sayBatch('已展开 '+todo.length+' 项预览（'+sc.mode+(hid?'，含隐藏 '+hid+' 项':'')+'）。');
}});
/* 批量构建：按可见顺序逐个串行（服务端一次一个），可中途取消（当前 job 跑完即停） */
var batchRunning=false,batchCancel=false;
function pollBuild(id,card,cancel){{
  return new Promise(function(resolve){{
    var log=card?card.querySelector('.buildlog'):null;
    if(log)log.style.display='block';
    var timer=setInterval(function(){{
      if(cancel&&cancel()){{clearInterval(timer);resolve({{cancelled:true}});return;}}
      fetch('/api/build?id='+id).then(function(r){{return r.json();}}).then(function(j){{
        if(log)log.textContent=(j.logTail||[]).join('\\n');
        if(j.status==='done'||j.status==='error'){{clearInterval(timer);resolve(j);}}
      }}).catch(function(){{/* 下轮重试 */}});
    }},2000);
  }});
}}
function setBuildBtns(dis){{
  Array.prototype.forEach.call(grid.querySelectorAll('.build-one'),function(b){{b.disabled=dis;}});
}}
buildAllBtn.addEventListener('click',async function(){{
  if(batchRunning){{batchCancel=true;sayBatch('正在取消：当前构建跑完即停…');return;}}
  if(CAPS.build===false){{sayBatch('本机缺包管理器，用 CLI 构建。');return;}}
  var sc=scopeCards();
  var targets=sc.cards.filter(function(c){{return buildable(c.dataset.fw);}});
  if(!targets.length){{sayBatch(sc.mode==='已选'?'已选项中没有可构建的项目（Vite/Next/VueCLI）。':'可见项中没有可构建的项目（Vite/Next/VueCLI）。');return;}}
  var coverN=targets.filter(function(c){{return !!c.dataset.built;}}).length;
  var staleN=targets.filter(function(c){{return !!c.dataset.stale;}}).length;
  var cmsg='逐个构建'+sc.mode+' '+targets.length+' 个项目？服务端一次一个，总耗时约 N×单次，期间可切走。'
    +(coverN?('其中 '+coverN+' 个已有产物'+(staleN?'（'+staleN+' 个已过期）':'（均未过期）')+'，将覆盖重建。'):'无历史产物，全新构建。');
  if(!(await dialogConfirm(cmsg,'开始构建')))return;
  batchRunning=true;batchCancel=false;setBuildBtns(true);
  buildAllBtn.textContent='取消构建队列';
  var i=0,okN=0,failN=0;
  (function next(){{
    if(batchCancel||i>=targets.length){{
      batchRunning=false;setBuildBtns(false);
      buildAllBtn.textContent='构建可见项';
      sayBatch(batchCancel
        ? '已取消队列：成功 '+okN+'，失败 '+failN+'，剩余 '+(targets.length-i)+' 未跑。'
        : '构建队列完成：成功 '+okN+'，失败 '+failN+'。');
      rescan().catch(function(){{}});
      return;
    }}
    var card=targets[i],nm=card.dataset.name;i++;
    sayBatch('构建中 '+i+'/'+targets.length+'：'+nm+'…（队列可点按钮取消）');
    fetch('/api/build',{{method:'POST',headers:{{'Content-Type':'application/json'}},
      body:JSON.stringify({{dir:PAGEDIR,name:nm}})}})
      .then(function(r){{return r.json().then(function(m){{return {{http:r.status,body:m}};}});}})
      .then(function(x){{
        if(x.http===409){{sayBatch('服务端正忙（可能有单卡构建在跑），本队列停止，稍后重试。');batchCancel=true;
          batchRunning=false;setBuildBtns(false);buildAllBtn.textContent='构建可见项';return;}}
        if(!x.body.ok){{failN++;
          var log=card.querySelector('.buildlog');
          if(log){{log.style.display='block';log.textContent='启动失败：'+(x.body.error||x.http);}}
          next();return;}}
        pollBuild(x.body.id,card,function(){{return batchCancel;}}).then(function(j){{
          if(j&&j.cancelled){{next();return;}}
          if(j.status==='done'){{okN++;
            card.dataset.built=(j.result&&j.result.url)||card.dataset.built;
            var links=card.querySelector('.links');
            if(links&&j.result&&j.result.url&&!links.querySelector('.built-link')){{
              var a=document.createElement('a');a.className='built-link';
              a.href=j.result.url;a.target='_blank';a.rel='noopener noreferrer';
              a.textContent='静态预览↗';a.style.marginLeft='6px';
              links.appendChild(a);
            }}
          }} else failN++;
          setTimeout(next,500);
        }});
      }}).catch(function(){{failN++;setTimeout(next,500);}});
  }})();
}});
grid.addEventListener('change',function(e){{
  if(e.target&&e.target.classList&&e.target.classList.contains('sel'))updateSel();
}});
document.getElementById('f-ckall').addEventListener('click',function(){{
  visCards().forEach(function(c){{var s=c.querySelector('.sel');if(s)s.checked=true;}});
  updateSel();
}});
document.getElementById('f-cknone').addEventListener('click',function(){{
  Array.prototype.forEach.call(grid.querySelectorAll('.sel'),function(s){{s.checked=false;}});
  updateSel();
}});
document.getElementById('f-selall').addEventListener('click',function(){{
  Array.prototype.forEach.call(rowsBox.querySelectorAll('input[type=checkbox]'),function(c){{c.checked=true;}});
}});
document.getElementById('f-selnone').addEventListener('click',function(){{
  Array.prototype.forEach.call(rowsBox.querySelectorAll('input[type=checkbox]'),function(c){{c.checked=false;}});
}});
upBtn.addEventListener('click',async function(){{
  var f=upFile.files[0];
  if(!f){{scanMsg.textContent='先选择一个 .zip 包。';return;}}
  if(!/\\.zip$/i.test(f.name)){{scanMsg.textContent='只收 .zip 包。';return;}}
  if(!(await dialogConfirm('上传 '+f.name+' 到本目录？（同名包将被覆盖）','上传')))return;
  scanMsg.textContent='上传中…';upBtn.disabled=true;
  var fd=new FormData();fd.append('dir',PAGEDIR);fd.append('file',f);
  fetch('/api/upload',{{method:'POST',body:fd}})
    .then(function(r){{return r.json().then(function(m){{return {{http:r.status,body:m}};}});}})
    .then(function(x){{
      upBtn.disabled=false;
      if(x.body.ok){{upFile.value='';
        scanMsg.textContent='已上传'+(x.body.overwritten?'（覆盖旧包）':'')+'，列表已刷新。';
        rescan().then(buildChecks);
      }}
      else scanMsg.textContent='上传失败：'+(x.body.error||x.http);
    }}).catch(function(e){{upBtn.disabled=false;scanMsg.textContent='请求失败：'+e.message;}});
}});
function doRebuild(){{
  dialogConfirm('重建入口页静态基线（compare --no-extract，没选的不动）？日常改动已实时刷新，不必每次重建。','重建').then(function(go){{
  if(!go)return;
  scanMsg.textContent='重建中…';rebuildBtn.disabled=true;
  fetch('/api/rebuild',{{method:'POST',headers:{{'Content-Type':'application/json'}},
    body:JSON.stringify({{dir:PAGEDIR}})}})
    .then(function(r){{return r.json().then(function(m){{return {{http:r.status,body:m}};}});}})
    .then(function(x){{
      rebuildBtn.disabled=false;
      if(x.body.ok){{scanMsg.textContent='重建成功，刷新页面…';
        setTimeout(function(){{location.reload();}},800);}}
      else{{scanMsg.textContent='重建失败：'+(x.body.output||x.body.error||x.http);}}
    }}).catch(function(e){{rebuildBtn.disabled=false;scanMsg.textContent='请求失败：'+e.message;}});
  }});
}}
rebuildBtn.addEventListener('click',doRebuild);
function paint(map){{
  OPEN={{}};
  Array.prototype.forEach.call(grid.querySelectorAll('.card'),function(c){{
    var st=c.querySelector('.st'),code=c.querySelector('.code'),link=c.querySelector('.devlink');
    if(c.dataset.fw==='待解压'){{st.className='st';st.title='尚未解压，不探活';code.textContent='待解压';return;}}
    if(!map){{st.className='st';code.textContent='未知';st.title='未知（需 node 预览服务的 /api）';return;}}
    var r=map[c.dataset.port];
    if(r&&r.open){{OPEN[c.dataset.port]=true;
      st.className='st on';st.title='在线 '+r.ms+'ms';code.textContent='HTTP '+r.code;
      if(link){{link.className='devlink';link.textContent='本地打开 :'+c.dataset.port;
        link.setAttribute('href','http://localhost:'+c.dataset.port);
        link.removeAttribute('aria-disabled');link.title='dev 在线，新窗口打开';}}
      return;}}
    st.className='st off';code.textContent='离线';st.title='离线：先敲卡片命令起 dev 再点';
    if(link){{link.className='devlink devlink-off';link.textContent='未启动 :'+c.dataset.port;
      link.setAttribute('href','http://localhost:'+c.dataset.port);
      link.setAttribute('aria-disabled','true');link.title='dev 未启动，先敲上方命令起服务再点';}}
  }});
}}
function poll(){{
  var pts=Array.prototype.map.call(grid.querySelectorAll('.card'),
    function(c){{return c.dataset.port;}});
  if(!pts.length)return;
  fetch('/api/status?'+pts.map(function(p){{return 'port='+p;}}).join('&'))
    .then(function(r){{return r.json();}}).then(paint).catch(function(){{paint(null);}});
}}
/* 启动即动态渲染（有 /api 才换掉静态基线；file 直开/python 后端保留静态卡片） */
rescan().catch(function(){{/* 静态基线保留 */}});
poll();setInterval(poll,5000);
}})();
</script>
</body></html>
"""


def main() -> int:
    ap = argparse.ArgumentParser(description="同目录多项目批量对比入口页")
    ap.add_argument("dir", help="含多个项目包/项目目录的目录（解压与入口页都落在这里）")
    ap.add_argument("--force", action="store_true", help="覆盖重解、覆盖已有的 index.html")
    ap.add_argument("--no-extract", action="store_true",
                    help="不解压：仅用已解压目录建页，未解压的包记为“待解压”占位（scan 按需流程用）")
    ap.add_argument("--port0", type=int, default=5173)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if not os.path.isdir(args.dir):
        print(f"错误：找不到目录 {args.dir}", file=sys.stderr)
        return 2
    directory = os.path.abspath(args.dir)
    items = collect(directory, args.force, extract=not args.no_extract)
    if not items:
        print("目录下未发现项目包（*.zip）或项目目录", file=sys.stderr)
        return 2

    idx = os.path.join(directory, "index.html")
    if os.path.exists(idx) and not args.force:
        with open(idx, encoding="utf-8", errors="ignore") as f:
            head = f.read(500)
        if MARKER not in head:
            print("拒绝写入：目录下已有非本工具生成的 index.html（--force 覆盖）",
                  file=sys.stderr)
            return 2

    import json as _json
    fw_opts = ['<option value="">全部框架</option>'] + [
        f'<option>{html.escape(fw)}</option>'
        for fw in sorted({it["framework"] for it in items})
    ]
    cards = []
    for i, it in enumerate(items):
        port = args.port0 + i
        it["port"] = port
        sw = "".join(
            f'<span class="sw" style="background:{c}" title="{c}"></span>' for c in it["colors"]
        ) or "<span style='color:#666;font-size:12px'>未提取到主题色</span>"
        if it.get("pending"):
            linkhtml = '<span class="pending-hint">待解压 — 点“解压此包”或工具条勾选</span>'
            buildhtml = ""
            previewhtml = ""
            selhtml = ""
            built, stale = "", False
        else:
            built, stale = built_info(directory, it["dir"], it["name"])
            linkhtml = (f'<a class="devlink" href="http://localhost:{port}" target="_blank" rel="noopener noreferrer">本地打开 :{port}</a>'
                        + (f'<a class="built-link" href="{built}" target="_blank" rel="noopener noreferrer" style="margin-left:6px">静态预览↗</a>' if built else ''))
            buildhtml = ""
            if it["framework"].startswith("Vite") or it["framework"] in ("Next.js", "VueCLI"):
                label = "重新构建" if built else "构建并预览"
                title = ("已有产物（可直接点静态预览）；重建将覆盖旧产物" if built
                         else "构建后落到单服务 /arena-apps/ 下直接看，不起新端口")
                buildhtml = (f'<button type="button" class="preview-btn build-one" '
                             f'data-name="{html.escape(it["name"])}" '
                             f'title="{title}">{label}</button>'
                             + ('<span class="stale-hint">产物过期（源码更新过），建议重建</span>' if stale else '')
                             + f'<div class="buildlog"></div>')
            previewhtml = ('<button type="button" class="preview-btn pv-toggle" aria-expanded="false">预览本项</button>'
                           '<div class="pv"></div>')
            selhtml = f'<input type="checkbox" class="sel" aria-label="选择{html.escape(it["name"])}">'
        cmds = dev_cmd(it["framework"], port) or ("；".join(it["suggest"][:2]) or "—")
        if isinstance(cmds, list):
            cmds = "；".join(cmds)
        cards.append(CARD.format(
            name=html.escape(it["name"]),
            framework=html.escape(it["framework"]),
            origin=it["origin"],
            tone=it["tone"],
            size=it["size"],
            components=it["components"],
            swatches=sw,
            cmd=html.escape(cmds),
            linkhtml=linkhtml,
            buildhtml=buildhtml,
            previewhtml=previewhtml,
            selhtml=selhtml,
            port=port,
            built=html.escape(built),
            stale="1" if stale else "",
            origin_raw=html.escape(it["origin_raw"]),
        ))
    # 先渲染成串再落盘：模板报错时不截断旧页
    rendered = PAGE.format(n=len(items), cards="".join(cards),
                           fw_opts="".join(fw_opts), chrome=load_chrome(directory))
    with open(idx, "w", encoding="utf-8") as f:
        f.write(rendered)

    if args.json:
        print(_json.dumps(
            [{k: it[k] for k in ("name", "origin", "framework", "tone", "size",
                                 "port", "components", "colors") if k in it}
             | ({"pending": True} if it.get("pending") else {}) for it in items],
            ensure_ascii=False, indent=2))
    else:
        print(f"入口页: {idx}（{len(items)} 个项目）")
        for it in items:
            print(f"  - {it['name']}: {it['framework']}, {it['tone']}/{it['size']}, "
                  f"端口 {it['port']}, {it['components']} 组件")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
