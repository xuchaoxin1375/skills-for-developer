#!/usr/bin/env python3

"""为发散式创意探索生成外部随机字符串 + 可复现的方向解读。

移植自 opus5.5 seed.mjs 解读规则，与 references/direction-catalog.md 一致。
种子只是内部脚手架，不得放入用户可见的设计中。
"""

from __future__ import annotations

import argparse
import json
import secrets
import string
import sys


ALPHABET = string.ascii_uppercase + string.ascii_lowercase + string.digits
# qwen 版 curated 快查表（中文语境 Edison：配色/版式/字体/意象均可直接落简报）
BRIEF_PALETTES = [
    ("铁锈与骨", ["#B0432A", "#EDE3CE", "#2B2620", "#C89A5B"]),
    ("松烟青", ["#2F5D4C", "#F1EAD8", "#191712", "#A3B18A"]),
    ("熔金", ["#B98A2E", "#1E1A12", "#F5EDDC", "#7A5A1F"]),
    ("蓝墨", ["#33425F", "#EDE9DD", "#101318", "#C05B3C"]),
    ("珊瑚纸", ["#E56B4F", "#FBF3E7", "#241F19", "#8FB3A8"]),
    ("灰阶实验", ["#161614", "#F2F0EA", "#8A8880", "#C4C2BA"]),
    ("苔原", ["#4C5B3A", "#EFEAD9", "#232019", "#C7A66A"]),
    ("电紫(低概率)", ["#5B3FD6", "#F4F1FF", "#14121F", "#E14FC1"]),
]
BRIEF_LAYOUTS = [
    "放射式构图：一个中心，其余全部让位",
    "对角线撕裂：版式沿 45° 轴展开",
    "瑞士网格：12 列，只允许打破其中一列",
    "巨型字主导：首屏只有一行字，大到溢出",
    "编辑分栏：像杂志内页一样排版",
    "不对称留白：留白多到令人不安，但仍成立",
    "Z 字流转：视线被强制走一条折线",
]
BRIEF_TYPEFACES = [
    "宋体衬线 × 等宽字：标题庄严，数据冷静",
    "超粗黑体 × 细线：字重反差拉到最大",
    "窄长压缩字：所有标题向中间挤压",
    "手写体 × 严格网格：混乱只许出现在一处",
    "衬线斜体主导：像一句低声的宣言",
    "等宽字全篇：终端美学，无衬线不配出现",
]
BRIEF_MOTIFS = [
    "晶体与折射：页面里有一块会转的玻璃",
    "工业控制面板：按钮有触感，点击有回音",
    "上世纪中叶海报：色块硬切，字大得像口号",
    "纸艺拼贴：每张图片都有纸边和投影",
    "像素游戏截图：每个 section 都是一帧画面",
    "粗野主义混凝土：灰、重、网格外露",
    "复古实验手册：编号、图注、页脚一应俱全",
    "天文台星图：细线、圆环、一个会呼吸的星点",
    "日文活版：竖排、印章、极细的线",
    "实验室标本：透明容器 + 标签 + 放大细节",
]


def _hash31(s: str) -> int:
    h = 7
    for ch in s:
        h = (h * 31 + ord(ch)) % 1000003
    return h


def build_brief(seed: str, product: str = "一个产品") -> str:
    """qwen 版一句话简报：同一种子→同一方向，可直接贴进编码 agent。"""
    h = _hash31(seed)
    pname, colors = BRIEF_PALETTES[h % len(BRIEF_PALETTES)]
    layout = BRIEF_LAYOUTS[(h // 7) % len(BRIEF_LAYOUTS)]
    face = BRIEF_TYPEFACES[(h // 13) % len(BRIEF_TYPEFACES)]
    motif = BRIEF_MOTIFS[(h // 29) % len(BRIEF_MOTIFS)]
    digits = [c for c in seed if c.isdigit()]
    zeros = seed.count("0")
    last = seed[-1]
    if zeros >= 3:
        rule = f"字符串里出现了 {zeros} 个「0」→ 页面必须留出一块纯空区域，不放任何内容"
    elif last in "2357":
        rule = f"字符串以素数「{last}」收尾 → 全页只允许 {3 + int(last)} 种字号，且布局必须有一处故意违反对称"
    elif not digits:
        rule = "字符串里一个数字都没有 → 页面禁用数字排版，所有信息用图形表达"
    else:
        freq: dict[str, int] = {}
        for c in seed:
            freq[c] = freq.get(c, 0) + 1
        top, n = max(freq.items(), key=lambda kv: kv[1])
        rule = f"「{top}」出现了 {n} 次 → 选一个视觉元素（色块/图标/字），让它精确重复 {n} 次"
    return (
        f"以随机字符串 {seed} 为灵感（它本身不出现在设计里，仅供你解读）。\n"
        f"创意方向：配色「{pname}」({' / '.join(colors)})；版式：{layout}；"
        f"字体气质：{face}；核心意象：{motif}；规则：{rule}。\n"
        f"请基于以上方向，构建{product}的落地页初稿：大胆执行，不要回落到渐变 + 三列卡片，让它真正好看。"
    )
HARMONY = ["单色", "互补", "类似色", "三分色", "分裂互补"]
HARMONY_OFFSET = [0, 180, 32, 120, 150]
ARCHETYPE = ["编辑大标题", "不对称网格", "中心海报", "目录索引", "便当网格", "终端打印", "横向色带"]
TYPEFACE = ["衬线展示", "怪诞无衬线", "等宽", "窄体", "圆体"]
RADIUS = ["直角 0", "微圆 4px", "圆润 12px", "胶囊"]
MOTIF = ["网格线", "点阵", "巨型数字", "斜纹", "正圆", "票据齿孔", "等高线", "套准十字"]
VOICE = ["冷静克制", "俏皮", "宣言式", "技术精确"]
DOSE = ["点缀", "适中", "大胆色块"]
VOWELS = set("aeiouAEIOU")


def generate_seed(length: int) -> str:
    return "".join(secrets.choice(ALPHABET) for _ in range(length))


def _fnv1a(s: str) -> int:
    h = 0x811C9DC5
    for ch in s:
        h ^= ord(ch)
        h = (h * 0x01000193) & 0xFFFFFFFF
    return h


def _is_prime(n: int) -> bool:
    if n < 2:
        return False
    i = 2
    while i * i <= n:
        if n % i == 0:
            return False
        i += 1
    return True


def _find_palindrome(s: str) -> str | None:
    for length in range(min(7, len(s)), 2, -1):
        for i in range(len(s) - length + 1):
            sub = s[i : i + length]
            if sub == sub[::-1]:
                return sub
    return None


def validate_seed(seed: str) -> bool:
    return 8 <= len(seed) <= 512 and all(c in ALPHABET for c in seed)


def derive_direction(seed: str) -> dict:
    chars = list(seed)
    total = sum(ord(c) for c in chars)
    hue = total % 360
    digits = [c for c in chars if c.isdigit()]
    upper = sum(1 for c in chars if c.isupper())
    lower = sum(1 for c in chars if c.islower())
    harmony_idx = len(digits) % 5
    first, last = chars[0], chars[-1]
    arch_idx = ALPHABET.index(first) % 7
    type_idx = ALPHABET.index(last) % 5
    vowels = sum(1 for c in chars if c in VOWELS)
    radius_idx = vowels % 4
    first_digit = next((i for i, c in enumerate(chars) if c.isdigit()), -1)
    if first_digit == -1 or first_digit >= 20:
        density = "疏朗"
    elif first_digit <= 7:
        density = "紧凑"
    else:
        density = "均衡"
    sub = seed[8:16]
    motif_idx = _fnv1a(sub) % 8
    flips = sum(1 for i in range(1, len(chars)) if (chars[i].isdigit(), chars[i].isupper(), chars[i].islower()) != (chars[i-1].isdigit(), chars[i-1].isupper(), chars[i-1].islower()))
    # 类别切换：大写/小写/数字三类
    def _cls(c: str) -> str:
        return "d" if c.isdigit() else ("u" if c.isupper() else "l")
    flips = sum(1 for i in range(1, len(chars)) if _cls(chars[i]) != _cls(chars[i - 1]))
    digit_sum = sum(int(d) for d in digits)
    pal = _find_palindrome(seed)
    twist = "镜像布局" if pal else ("竖排书脊" if _is_prime(digit_sum) else "无")

    judgments: list[str] = []
    body = TYPEFACE[type_idx]
    if arch_idx == 5:
        body = "等宽"
        judgments.append("终端打印版式下，正文统一为等宽字体")
        if radius_idx == 3:
            radius_idx = 0
            judgments.append("胶囊圆角与终端美学冲突，改为直角")

    dark = upper >= lower
    return {
        "seed": seed,
        "summary": f"{'暗调' if dark else '亮调'}{HARMONY[harmony_idx]} · {ARCHETYPE[arch_idx]} · {TYPEFACE[type_idx]}",
        "accentHue": (hue + HARMONY_OFFSET[harmony_idx]) % 360,
        "bodyTypeface": body,
        "readings": [
            {"维度": "主色相", "子模式": f"编码和 {total} → mod 360", "取值": f"{hue}°"},
            {"维度": "配色关系", "子模式": f"数字 {len(digits)} 个 → mod 5", "取值": HARMONY[harmony_idx]},
            {"维度": "明度基调", "子模式": f"大写 {upper} / 小写 {lower}", "取值": "暗调" if dark else "亮调"},
            {"维度": "版式原型", "子模式": f"首字符「{first}」→ mod 7", "取值": ARCHETYPE[arch_idx]},
            {"维度": "字体气质", "子模式": f"末字符「{last}」→ mod 5", "取值": TYPEFACE[type_idx]},
            {"维度": "圆角", "子模式": f"元音 {vowels} 个 → mod 4", "取值": RADIUS[radius_idx]},
            {"维度": "密度", "子模式": "无数字" if first_digit == -1 else f"首数字第 {first_digit + 1} 位", "取值": density},
            {"维度": "母题", "子模式": f"第9–16位「{sub}」哈希 mod 8", "取值": MOTIF[motif_idx]},
            {"维度": "文案语气", "子模式": f"类别切换 {flips} 次 → mod 4", "取值": VOICE[flips % 4]},
            {"维度": "强调剂量", "子模式": f"数字和 {digit_sum} → mod 3", "取值": DOSE[digit_sum % 3]},
            {"维度": "特殊模式", "子模式": f"回文「{pal}」" if pal else (f"数字和 {digit_sum} 是质数" if _is_prime(digit_sum) else "未发现"), "取值": twist},
        ],
        "judgments": judgments,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="生成外部随机种子并输出可复现解读。种子不得放入设计中。"
    )
    parser.add_argument("--count", type=int, default=1, help="种子数量 1–12")
    parser.add_argument("--length", type=int, default=64, help="种子长度 8–512")
    parser.add_argument("--seed", type=str, default=None, help="解读已有种子（复现）")
    parser.add_argument("--json", action="store_true", help="JSON 输出")
    parser.add_argument("--brief", action="store_true", help="输出可直接粘贴的创意简报（qwen 版 curated 表）")
    parser.add_argument("--product", type=str, default="一个产品", help="简报中的产品名（配合 --brief）")
    args = parser.parse_args()

    if not 1 <= args.count <= 12:
        parser.error("--count must be between 1 and 12")
    if not 8 <= args.length <= 512:
        parser.error("--length must be between 8 and 512")

    seeds = [args.seed] if args.seed else [generate_seed(args.length) for _ in range(args.count)]
    for s in seeds:
        if not validate_seed(s):
            parser.error("种子必须是 8–512 位字母或数字")
    results = [derive_direction(s) for s in seeds]

    if args.brief:
        for s in seeds:
            print(build_brief(s, args.product))
            print()
        return 0
    if args.json:
        print(json.dumps(results[0] if len(results) == 1 else results, ensure_ascii=False, indent=2))
    else:
        for d in results:
            print(f"\n种子  {d['seed']}\n方向  {d['summary']}\n{chr(9472) * 40}")
            for r in d["readings"]:
                print(f"{r['维度']:>5}  {r['取值']:<8}  ← {r['子模式']}")
            for j in d["judgments"]:
                print(f"判断修正：{j}")
            print("\n提示：种子只用于灵感，不要让它出现在设计中。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
