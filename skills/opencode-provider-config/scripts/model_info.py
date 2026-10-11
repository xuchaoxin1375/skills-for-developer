#!/usr/bin/env python3
"""model_info.py — 多源查询模型元数据（上下文窗口/输出上限/模态/工具调用），供 opencode provider 配置用。

用法:
  python3 model_info.py <模型名正则> [--source auto|openrouter|litellm|modelsdev|all]
                        [--json] [--limit N] [--timeout 秒]

数据源按速度排序: openrouter（直连最快、字段最全）-> litellm（jsdelivr 镜像 -> raw 回退）
-> modelsdev（最慢）。--source auto 在第一个有命中的源停止；all 跨源合并。

仅用标准库，零依赖；下载带 UA（脚本 HTTP 库无 UA 常被 403），JSON 解析失败即视为截断并提示重取。
退出码: 0=有命中, 1=无命中, 2=所有源都失败。
"""
import argparse
import json
import re
import sys
import urllib.error
import urllib.request

UA = {"User-Agent": "Mozilla/5.0 (model_info.py)", "Accept": "application/json"}

LITELLM_URLS = [
    "https://cdn.jsdelivr.net/gh/BerriAI/litellm@main/model_prices_and_context_window.json",
    "https://raw.githubusercontent.com/BerriAI/litellm/main/model_prices_and_context_window.json",
]

SOURCES = {
    "openrouter": "https://openrouter.ai/api/v1/models",
    "modelsdev": "https://models.dev/api.json",
}
AUTO_ORDER = ["openrouter", "litellm", "modelsdev"]


def fetch_json(url, timeout):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
    # 截断/损坏的文件会在这里抛 JSONDecodeError，交由上层提示重取
    return json.loads(raw)


def fetch_with_fallback(urls, timeout):
    last = None
    for url in urls:
        try:
            return fetch_json(url, timeout)
        except Exception as exc:  # noqa: BLE001 - 逐个回退，报告原因
            last = exc
            print(f"  ! {url} -> {type(exc).__name__}: {exc}", file=sys.stderr)
    raise last


def row(model, source, ctx=None, max_out=None, modal_in=None, modal_out=None,
        tools=None, reasoning=None, mode=None, name=""):
    return {
        "model": model, "source": source, "ctx": ctx, "max_out": max_out,
        "modal_in": modal_in, "modal_out": modal_out,
        "tools": tools, "reasoning": reasoning, "mode": mode, "name": name,
    }


def q_openrouter(pat, timeout):
    data = fetch_json(SOURCES["openrouter"], timeout)
    rows = []
    for m in data.get("data", []):
        arch = m.get("architecture") or {}
        tp = m.get("top_provider") or {}
        sp = m.get("supported_parameters") or []
        rows.append(row(
            m.get("id", ""), "openrouter",
            ctx=m.get("context_length"), max_out=tp.get("max_completion_tokens"),
            modal_in="+".join(arch.get("input_modalities") or []),
            modal_out="+".join(arch.get("output_modalities") or []),
            tools=("tools" in sp) or None, reasoning=("reasoning" in sp) or None,
            name=m.get("name", ""),
        ))
    return rows


def q_litellm(pat, timeout):
    data = fetch_with_fallback(LITELLM_URLS, timeout)
    rows = []
    for key, m in data.items():
        if not isinstance(m, dict):
            continue
        rows.append(row(
            key, "litellm",
            ctx=m.get("max_input_tokens"), max_out=m.get("max_output_tokens"),
            tools=m.get("supports_function_calling"),
            reasoning=m.get("supports_reasoning"),
            mode=m.get("mode"), name=key,
        ))
    return rows


def q_modelsdev(pat, timeout):
    data = fetch_json(SOURCES["modelsdev"], timeout)
    rows = []
    for pid, prov in data.items():
        for mid, m in (prov.get("models") or {}).items():
            lim = m.get("limit") or {}
            mod = m.get("modalities") or {}
            rows.append(row(
                f"{pid}/{mid}", "modelsdev",
                ctx=lim.get("context"), max_out=lim.get("output"),
                modal_in="+".join(mod.get("input") or []),
                modal_out="+".join(mod.get("output") or []),
                tools=m.get("tool_call"), reasoning=m.get("reasoning"),
                name=m.get("name", ""),
            ))
    return rows


QUERY = {"openrouter": q_openrouter, "litellm": q_litellm, "modelsdev": q_modelsdev}


def match(rows, pat):
    try:
        rx = re.compile(pat, re.IGNORECASE)
        hit = lambda r: rx.search(f"{r['model']} {r.get('name', '')}")
    except re.error:
        needle = pat.lower()
        hit = lambda r: needle in f"{r['model']} {r.get('name', '')}".lower()
    return [r for r in rows if hit(r)]


def cell(v, width):
    if v is None:
        s = "-"
    elif isinstance(v, bool):
        s = "y" if v else "n"
    else:
        s = str(v)
    return s[:width]


def print_table(rows, limit):
    heads = ["model", "source", "ctx", "out", "in", "out_mod", "tools", "rsn", "mode"]
    widths = [44, 10, 8, 8, 16, 16, 5, 3, 10]
    keys = ["model", "source", "ctx", "max_out", "modal_in", "modal_out", "tools", "reasoning", "mode"]
    order = {"openrouter": 0, "litellm": 1, "modelsdev": 2}
    rows = sorted(rows, key=lambda r: (order.get(r["source"], 9), r["model"]))[:limit]
    print("  ".join(h.ljust(w) for h, w in zip(heads, widths)))
    for r in rows:
        print("  ".join(cell(r[k], w).ljust(w) for k, w in zip(keys, widths)))


def main():
    if hasattr(sys.stdout, "reconfigure"):  # Windows GBK 控制台防乱码
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            pass

    ap = argparse.ArgumentParser(description="多源查询模型元数据（上下文/输出/模态/工具调用）")
    ap.add_argument("pattern", help="模型名匹配（大小写不敏感正则，如 glm-5.3、kimi|k3）")
    ap.add_argument("--source", default="auto",
                    choices=["auto", "openrouter", "litellm", "modelsdev", "all"],
                    help="auto=按速度序取首个有命中的源（默认）；all=跨源合并")
    ap.add_argument("--json", action="store_true", help="输出 JSON 数组而非表格")
    ap.add_argument("--limit", type=int, default=20, help="最多显示条数（默认 20）")
    ap.add_argument("--timeout", type=int, default=30, help="单源超时秒数（默认 30，modelsdev 较慢）")
    args = ap.parse_args()

    order = list(AUTO_ORDER) if args.source in ("auto", "all") else [args.source]
    matched, failures = [], 0
    for src in order:
        try:
            print(f"# querying {src} ...", file=sys.stderr)
            hits = match(QUERY[src](args.pattern, args.timeout), args.pattern)
        except Exception as exc:  # noqa: BLE001 - 单源失败不拖垮整体
            failures += 1
            print(f"  ! {src} 失败: {type(exc).__name__}: {exc}", file=sys.stderr)
            continue
        print(f"# {src}: {len(hits)} hit(s)", file=sys.stderr)
        matched.extend(hits)
        if args.source == "auto" and hits:
            break

    if not matched:
        sys.exit(1 if failures < len(order) else 2)

    if args.json:
        print(json.dumps(matched[:args.limit], ensure_ascii=False, indent=2))
    else:
        print_table(matched, args.limit)


if __name__ == "__main__":
    main()
