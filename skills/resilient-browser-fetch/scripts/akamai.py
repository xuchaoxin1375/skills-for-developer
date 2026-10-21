"""Akamai Bot Manager 挑战检测与本地求解(SEC-CPT / SBSD)。

为什么要有这个模块: Akamai 不是 Cloudflare, `solve_cloudflare` 对它完全无效。
Akamai 的页面分两类, 处置方式相反:

- **挑战页**(SEC-CPT interstitial / SBSD 脚本): 站点还没放行。挑战在页面加载早期
  采集环境, 跑完后自己重载正文。这类可以等, 也可以在页面自己没解题时, 本地把
  SHA-256 工作量证明算出来再从页面内提交。
- **边缘封禁**(edge block): 403 "Access Denied" + "Reference #18.…", 第一个请求就被拒,
  根本没有挑战窗口。换引擎、换指纹、换求解器都无效, 只能换出口。

本模块只处理第一类, 并且只做"本地可算"的部分:

- SEC-CPT 的 crypto/adaptive 挑战是 SHA-256 工作量证明, 本地算完从页面内提交;
- behavioral 挑战要采集行为数据, 本模块只负责等它自己跑完, 不伪造行为。

算法来源: SEC-CPT 挑战结构与 PoW 规则、`_abck` 客户端停止信号, 参考
Hyper Solutions 的 hyper-sdk-py(MIT, Copyright (c) 2024 Hyper Solutions)。
这里是按其公开算法重写的独立实现, 不含其 API 调用与商业代码。

已知边界(实测, 见 references/detection-layers.md):

- 挑战窗口内暴露自动化痕迹时, PoW 算对了照样被判负 —— 本模块不改变控制面;
- 边缘封禁与出口级封禁本模块无解, 只负责把它认出来, 好让调用方去换出口。
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import hashlib
import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from html import unescape
from typing import Any
from urllib.parse import urlsplit

__all__ = [
    "AkamaiSignal",
    "AkamaiSolveResult",
    "SecCptChallenge",
    "abck_invalidated",
    "abck_state",
    "abck_stop_signal",
    "detect_akamai",
    "parse_sec_cpt_html",
    "parse_sec_cpt_json",
    "solve_akamai_page",
    "solve_akamai_page_async",
    "solve_sec_cpt_answers",
    "verify_sec_cpt_answer",
]

LOGGER = logging.getLogger(__name__)

# SEC-CPT interstitial 的容器标记。挑战页很小(几 KB), 因此后面还有"正文很小"的联合判定。
SEC_CPT_MARKERS = (
    "sec-if-cpt-container",
    "sec-bc-tile-container",
    "sec-cpt-if",
    "/_sec/cp_challenge/",
    "sec-cp-challenge",
)
# SBSD(state based scraping detection)脚本: 路径是 /.well-known/sbsd, 或带 v=<uuid>[&t=<n>] 的查询串。
# 带 t= 的是"主动挑战"(脚本会自己提交并重载); 不带 t= 的只是被动传感器, 正常页面也会加载,
# 不能据此判定为挑战页。
WELL_KNOWN_SBSD = "/.well-known/sbsd"
_UUID = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
SBSD_SCRIPT_RE = re.compile(rf"(?i)<script[^>]+src=[\"'][^\"']*[?&](?:amp;)?v={_UUID}(?:&(?:amp;)?t=\d+)?")
ACTIVE_SBSD_SCRIPT_RE = re.compile(
    rf"(?i)<script[^>]+src=[\"'][^\"']*[?&](?:amp;)?v={_UUID}&(?:amp;)?t=\d+"
)
# 边缘封禁页: "Reference #18.a5f7d517.1792565137.49bd9361" + errors.edgesuite.net。
REFERENCE_RE = re.compile(r"(?i)reference\s*#\s*(\d{1,3}\.[0-9a-f]{4,16}\.\d{6,12}\.[0-9a-f]{4,16})")
AKAMAI_HINTS = (
    "akamai",
    "akamaighost",
    "akamaitechnologies",
    "akamaitechnologies.com",
    "edgesuite.net",
    "edgekey.net",
    "bmak",
    "bm_sz",
    "_abck",
)

# SEC-CPT 挑战参数: iframe 上的 challenge="<base64 json>"、data-duration=N、src="<挑战页路径>"。
_CHALLENGE_ATTR_RE = re.compile(r"challenge=[\"']([^\"']+)[\"']")
_DURATION_RE = re.compile(r"data-duration=[\"']?(\d+)")
_SRC_RE = re.compile(r"data-duration=[\"']?\d+[\"']?\s+src=[\"']([^\"']+)[\"']")
_PROVIDER_RE = re.compile(r"(?i)\bprovider=[\"']?([a-z]+)")
_TOKEN_RE = re.compile(r"[\"']token[\"']\s*:\s*[\"']([^\"']*)[\"']")
_TIMESTAMP_RE = re.compile(r"[\"']timestamp[\"']\s*:\s*(\d+)")
_NONCE_RE = re.compile(r"[\"']nonce[\"']\s*:\s*[\"']([^\"']*)[\"']")
_DIFFICULTY_RE = re.compile(r"[\"']difficulty[\"']\s*:\s*(\d+)")
_COUNT_RE = re.compile(r"[\"']count[\"']\s*:\s*(\d+)")

# 时间预算(秒)。挑战页自己会先解一次, 本地求解只是兜底, 所以宽限给得不大。
SEC_GRACE_POW = 8.0
SEC_GRACE_SENSOR = 12.0
# 边缘封禁时的同源首页预热: 让 bmak 把 _abck 发到有效为止, 再回目标页。
WARMUP_SENSOR_WAIT = 8.0
# 判定"挑战页"的正文上限: SEC-CPT interstitial 很小, 正常商品页远大于此。
CHALLENGE_PAGE_MAX_BYTES = 50_000


@dataclass(frozen=True)
class AkamaiSignal:
    """一次检测的结果。``kind`` 取值: none / sec_cpt / sbsd / edge_block / bot_manager。"""

    kind: str
    detail: str = ""
    provider: str = ""
    duration: int = 0
    reference: str = ""


@dataclass
class AkamaiSolveResult:
    """求解结果。``outcome``: no_challenge / solved / unsolved / edge_block。"""

    outcome: str
    kind: str = "none"
    detail: str = ""
    steps: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class SecCptChallenge:
    """SEC-CPT 挑战参数。``has_pow`` 为 False 表示是 behavioral 型, 没有可本地计算的量。"""

    provider: str = "crypto"
    duration: int = 0
    path: str = ""
    token: str = ""
    timestamp: int = 0
    nonce: str = ""
    difficulty: int = 0
    count: int = 1

    @property
    def has_pow(self) -> bool:
        """是否有可本地计算的工作量证明参数。"""

        return self.difficulty > 0 and bool(self.nonce)


def abck_state(cookie: str | None) -> str:
    """读 `_abck` 的有效性标记: valid(~0~) / invalid(~-1~) / unknown / missing。"""

    if not cookie:
        return "missing"
    if "~0~" in cookie:
        return "valid"
    if "~-1~" in cookie:
        return "invalid"
    return "unknown"


def abck_stop_signal(cookie: str | None) -> int | None:
    """`_abck` 的客户端停止信号(第二个 `~` 字段)。

    `-1` 表示还没被接受, 要继续发传感器; `0` 或正数表示发到该次数就停。
    字段缺失或不是整数时返回 None。
    """

    if not cookie:
        return None
    parts = cookie.split("~")
    if len(parts) < 2:
        return None
    try:
        return int(parts[1])
    except ValueError:
        return None


def abck_invalidated(cookie: str | None) -> bool:
    """`_abck` 是否被受保护接口作废(第四个 `~` 字段 >= 0), 再发一次传感器即可修复。"""

    if not cookie:
        return False
    parts = cookie.split("~")
    if len(parts) < 4:
        return False
    try:
        return int(parts[3]) > -1
    except ValueError:
        return False


def _page_sample(html: str) -> str:
    """取判定用的正文样本: 只看前 200 KB, 避免超大页面拖慢判定。"""

    return (html or "")[:200_000]


def detect_akamai(
    html: str,
    *,
    status: int | None = None,
    headers: dict[str, str] | None = None,
    cookies: dict[str, str] | None = None,
) -> AkamaiSignal:
    """识别 Akamai 的挑战页 / 边缘封禁 / 正常页。

    判定顺序: SEC-CPT 挑战容器 → **明确拒绝** → SBSD 脚本 → 只跑了传感器(正常)。

    "明确拒绝"要排在 SBSD 脚本之前: 边缘封禁页里也会带一个混淆的 SBSD 脚本标签
    (形如 ``/hnuG7-/…/v=<uuid>``), 按脚本分支先判会把硬拒绝误报成"可求解的挑战页",
    于是让人去加求解器——而边缘封禁根本没有挑战窗口, 只能换出口或换客户端。

    :param html: 页面 HTML(挑战页与封禁页都按正文判定, 状态码只作补充)。
    :param status: 响应状态码, 403 之类的边缘封禁才有意义。
    :param headers: 响应头, 用于看 Server 是否是 AkamaiGHost 一类。
    :param cookies: 浏览器 cookie 字典, 用来判断 `_abck`/`bm_sz` 是否已下发。
    """

    sample = _page_sample(html)
    lowered = sample.lower()
    header_map = {str(key).lower(): str(value) for key, value in (headers or {}).items()}
    cookie_map = {str(key): str(value) for key, value in (cookies or {}).items()}
    # 挑战页本身很小(几 KB)。这个上限用来把"加载了传感器脚本的正常页面"排除掉:
    # 正常页面也会带 /.well-known/sbsd, 但它不是挑战。
    near_empty = len(sample) <= CHALLENGE_PAGE_MAX_BYTES

    if any(marker in lowered for marker in SEC_CPT_MARKERS) or (
        "powered and protected by" in lowered and near_empty
    ):
        provider_match = _PROVIDER_RE.search(sample)
        duration_match = _DURATION_RE.search(sample)
        return AkamaiSignal(
            kind="sec_cpt",
            detail="sec_cpt_container",
            provider=(provider_match.group(1).lower() if provider_match else ""),
            duration=int(duration_match.group(1)) if duration_match else 0,
        )

    # 明确拒绝: 标题 Access Denied / "You don't have permission" / Reference #18。
    # 页面小的时候不需要 403 状态码或 Akamai 响应头佐证(晚接入引擎拿不到状态码)。
    reference_match = REFERENCE_RE.search(sample)
    denied = "access denied" in lowered or "you don't have permission" in lowered
    server = header_map.get("server", "").lower()
    akamai_server = any(hint in server for hint in ("akamai", "edgesuite", "edgekey"))
    if reference_match or (
        denied
        and (
            status == 403
            or akamai_server
            or near_empty
            or any(hint in lowered for hint in AKAMAI_HINTS)
        )
    ):
        return AkamaiSignal(
            kind="edge_block",
            detail="edge_block",
            reference=reference_match.group(1) if reference_match else "",
        )

    if near_empty and (
        WELL_KNOWN_SBSD in lowered
        or ACTIVE_SBSD_SCRIPT_RE.search(sample)
        or SBSD_SCRIPT_RE.search(sample)
    ):
        detail = "sbsd_active" if ACTIVE_SBSD_SCRIPT_RE.search(sample) else "sbsd_script"
        return AkamaiSignal(kind="sbsd", detail=detail)

    if status == 403 and akamai_server:
        # 站点自己的 403 错误页也可能由 Akamai 网关代发(如标题 "Page Reference Code"),
        # 这类同样是"边缘层已拒绝", 换出口才有意义。
        return AkamaiSignal(kind="edge_block", detail="edge_block")

    if any(name in cookie_map for name in ("_abck", "bm_sz", "ak_bmsc")):
        return AkamaiSignal(kind="bot_manager", detail="sensor_cookies")

    if SBSD_SCRIPT_RE.search(sample) or WELL_KNOWN_SBSD in lowered:
        # 正常页面也可能带 SBSD 传感器脚本(被动), 这不是挑战, 只是"传感器跑过了"。
        return AkamaiSignal(kind="bot_manager", detail="sbsd_sensor")

    return AkamaiSignal(kind="none")


def _challenge_from_mapping(data: dict[str, Any]) -> SecCptChallenge:
    """从已解析的 JSON 字典里取挑战参数。"""

    def _int(key: str, default: int = 0) -> int:
        value = data.get(key, default)
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    return SecCptChallenge(
        provider=str(data.get("provider") or "crypto").lower(),
        duration=_int("chlg_duration", _int("duration")),
        path=str(data.get("branding_url_content") or ""),
        token=str(data.get("token") or ""),
        timestamp=_int("timestamp"),
        nonce=str(data.get("nonce") or ""),
        difficulty=_int("difficulty"),
        count=max(1, _int("count", 1)),
    )


def parse_sec_cpt_html(html: str) -> SecCptChallenge | None:
    """解析 SEC-CPT interstitial 的 iframe 参数。

    页面里有一处 ``challenge="<base64 json>"``(挑战数据)、``data-duration=N``(服务端
    要求的最短等待秒数)与 ``src="<挑战页路径>"``。不是挑战页时返回 None。
    """

    sample = _page_sample(html)
    challenge_match = _CHALLENGE_ATTR_RE.search(sample)
    duration_match = _DURATION_RE.search(sample)
    if not challenge_match or not duration_match:
        return None
    raw = challenge_match.group(1)
    try:
        decoded = base64.b64decode(unescape(raw), validate=False)
        data = json.loads(decoded)
    except (binascii.Error, ValueError, UnicodeDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    src_match = _SRC_RE.search(sample)
    provider_match = _PROVIDER_RE.search(sample)
    challenge = _challenge_from_mapping(data)
    return SecCptChallenge(
        provider=(provider_match.group(1).lower() if provider_match else challenge.provider),
        duration=int(duration_match.group(1)),
        path=(unescape(src_match.group(1)) if src_match else challenge.path),
        token=challenge.token,
        timestamp=challenge.timestamp,
        nonce=challenge.nonce,
        difficulty=challenge.difficulty,
        count=challenge.count,
    )


def parse_sec_cpt_json(payload: str) -> SecCptChallenge | None:
    """解析 428 JSON 答案(``{"sec-cp-challenge": "true", ...}``)。不是挑战时返回 None。"""

    text = (payload or "").strip()
    if text.startswith("{"):
        try:
            data = json.loads(text)
        except ValueError:
            data = None
    else:
        # 浏览器把 JSON 文档渲染成 <pre>{"…"}</pre>, 去掉标签再取。
        stripped = re.sub(r"<[^>]+>", "", text).strip()
        try:
            data = json.loads(stripped)
        except ValueError:
            data = None
    if not isinstance(data, dict):
        return None
    if str(data.get("sec-cp-challenge", "")).lower() not in ("true", "1"):
        return None
    return _challenge_from_mapping(data)


def solve_sec_cpt_answers(
    sec: str,
    challenge: SecCptChallenge,
    *,
    deadline: float | None = None,
) -> list[str]:
    """本地解 SEC-CPT 的 SHA-256 工作量证明。

    规则: 找 ``count`` 个答案, 使 ``sha256(sec + timestamp + nonce + difficulty + answer)``
    的整数值能被 ``difficulty`` 整除; 每答对一个, 难度加一(与官方脚本同规则)。
    ``sec`` 取自 ``sec_cpt`` cookie 的第一个 ``~`` 字段。
    """

    if challenge.difficulty <= 0:
        raise ValueError("SEC-CPT 难度必须为正数。")
    answers: list[str] = []
    difficulty = challenge.difficulty
    prefix = f"{sec}{challenge.timestamp}{challenge.nonce}"
    tries = 0
    while len(answers) < max(1, challenge.count):
        answer = f"0.{os.urandom(8).hex()}"
        digest = hashlib.sha256(f"{prefix}{difficulty}{answer}".encode("ascii")).digest()
        if int.from_bytes(digest, "big") % difficulty == 0:
            answers.append(answer)
            difficulty += 1
            continue
        tries += 1
        if deadline is not None and tries % 4096 == 0 and time.monotonic() >= deadline:
            raise TimeoutError("SEC-CPT 工作量证明超出时间预算。")
    return answers


def verify_sec_cpt_answer(
    sec: str,
    challenge: SecCptChallenge,
    answer: str,
    difficulty: int | None = None,
) -> bool:
    """校验一个答案是否满足难度要求(自测与单元测试用)。"""

    level = challenge.difficulty if difficulty is None else difficulty
    digest = hashlib.sha256(
        f"{sec}{challenge.timestamp}{challenge.nonce}{level}{answer}".encode("ascii")
    ).digest()
    return int.from_bytes(digest, "big") % level == 0


class _AsyncPageProbe:
    """异步 Playwright/Patchright 页面的一层薄封装(与 :class:`_PageProbe` 同接口)。"""

    def __init__(self, page: Any) -> None:
        self.page = page
        self.sensor_posts = 0
        self.sbsd_posts = 0
        self.documents = 0

    def _on_request(self, request: Any) -> None:
        try:
            if request.method != "POST":
                return
            body = request.post_data or ""
        except Exception:
            return
        if body.startswith('{"sensor_data"'):
            self.sensor_posts += 1
        elif body.startswith('{"body"'):
            self.sbsd_posts += 1

    def _on_response(self, response: Any) -> None:
        try:
            request = response.request
            if request.resource_type != "document":
                return
            if request.frame is not None and request.frame != self.page.main_frame:
                return
        except Exception:
            return
        self.documents += 1

    def __enter__(self) -> _AsyncPageProbe:
        self.page.on("request", self._on_request)
        self.page.on("response", self._on_response)
        return self

    def __exit__(self, *_args: Any) -> None:
        for event, handler in (("request", self._on_request), ("response", self._on_response)):
            try:
                self.page.remove_listener(event, handler)
            except Exception:
                pass

    async def html(self) -> str:
        return str(await self.page.content())

    async def cookies(self) -> dict[str, str]:
        try:
            items = await self.page.context.cookies()
        except Exception:
            return {}
        return {str(item.get("name")): str(item.get("value")) for item in items}


async def _sec_cpt_cleared_async(probe: _AsyncPageProbe, documents: int) -> bool:
    """异步版的挑战放行判定。"""

    if "~3~" in (await probe.cookies()).get("sec_cpt", ""):
        return True
    if probe.documents <= documents:
        return False
    sample = (await probe.html())[:CHALLENGE_PAGE_MAX_BYTES].lower()
    return not any(marker in sample for marker in SEC_CPT_MARKERS)


async def _solve_sec_cpt_async(
    probe: _AsyncPageProbe,
    *,
    target_url: str,
    deadline: float,
    signal: AkamaiSignal,
    steps: list[str],
) -> AkamaiSolveResult:
    """异步版 SEC-CPT 求解(批量会话走 Scrapling 异步接口)。"""

    html = await probe.html()
    challenge = parse_sec_cpt_html(html) or parse_sec_cpt_json(html)
    provider = challenge.provider if challenge else (signal.provider or "crypto")
    duration = challenge.duration if challenge else signal.duration
    documents = probe.documents
    grace = SEC_GRACE_SENSOR if provider == "behavioral" else SEC_GRACE_POW

    phase_a_start = time.monotonic()
    phase_a_end = min(deadline, phase_a_start + float(duration) + grace)
    while time.monotonic() < phase_a_end:
        if await _sec_cpt_cleared_async(probe, documents):
            steps.append("sec_cpt_self_solved")
            return AkamaiSolveResult("solved", "sec_cpt", "页面自己解开了挑战", steps)
        await asyncio.sleep(0.5)
    steps.append("sec_cpt_self_solve_timeout")

    if challenge is None or not challenge.has_pow:
        steps.append("sec_cpt_no_local_pow")
        try:
            await probe.page.goto(target_url, wait_until="domcontentloaded", timeout=15_000)
        except Exception as exc:
            return AkamaiSolveResult("unsolved", "sec_cpt", f"刷新目标页失败: {exc}", steps)
        return AkamaiSolveResult("unsolved", "sec_cpt", "只有行为型挑战, 本模块不伪造行为数据", steps)

    cookie = (await probe.cookies()).get("sec_cpt", "")
    sec = cookie.split("~", 1)[0] if cookie else ""
    if not sec:
        steps.append("sec_cpt_missing_cookie")
        return AkamaiSolveResult("unsolved", "sec_cpt", "没有 sec_cpt cookie, 无法计算 PoW", steps)

    remaining_wait = float(duration) - (time.monotonic() - phase_a_start)
    if remaining_wait > 0:
        await asyncio.sleep(min(remaining_wait, max(0.0, deadline - time.monotonic())))

    try:
        answers = await asyncio.to_thread(
            solve_sec_cpt_answers, sec, challenge, deadline=deadline - 1.0
        )
    except (TimeoutError, ValueError) as exc:
        steps.append("sec_cpt_pow_failed")
        return AkamaiSolveResult("unsolved", "sec_cpt", f"本地 PoW 失败: {exc}", steps)
    steps.append(f"sec_cpt_pow_solved:{len(answers)}")

    payload = json.dumps({"token": challenge.token, "answers": answers})
    try:
        posted = await probe.page.evaluate(
            _POST_JSON_JS, {"url": f"/_sec/verify?provider={provider}", "body": payload}
        )
    except Exception as exc:
        steps.append("sec_cpt_post_failed")
        return AkamaiSolveResult("unsolved", "sec_cpt", f"提交 PoW 答案失败: {exc}", steps)
    steps.append(f"sec_cpt_post:{posted.get('status') if isinstance(posted, dict) else '?'}")

    try:
        await probe.page.evaluate(_GET_JSON_JS, {"url": "/_sec/cp_challenge/verify"})
    except Exception:
        pass

    cleared = "~3~" in (await probe.cookies()).get("sec_cpt", "")
    try:
        await probe.page.goto(target_url, wait_until="domcontentloaded", timeout=15_000)
    except Exception as exc:
        return AkamaiSolveResult("unsolved", "sec_cpt", f"回到目标页失败: {exc}", steps)
    if cleared:
        steps.append("sec_cpt_cookie_cleared")
        return AkamaiSolveResult("solved", "sec_cpt", "PoW 已提交并放行", steps)
    steps.append("sec_cpt_not_cleared")
    return AkamaiSolveResult("unsolved", "sec_cpt", "提交后 sec_cpt 仍未放行", steps)


async def _solve_sbsd_async(
    probe: _AsyncPageProbe,
    *,
    target_url: str,
    deadline: float,
    steps: list[str],
) -> AkamaiSolveResult:
    """异步版 SBSD 处理。"""

    documents = probe.documents
    posts = probe.sbsd_posts
    wait_end = min(deadline, time.monotonic() + 10.0)
    while time.monotonic() < wait_end:
        if probe.sbsd_posts - posts >= 2 or probe.documents > documents:
            steps.append(f"sbsd_posts:{probe.sbsd_posts - posts}")
            try:
                await probe.page.goto(target_url, wait_until="domcontentloaded", timeout=15_000)
            except Exception as exc:
                return AkamaiSolveResult("unsolved", "sbsd", f"回到目标页失败: {exc}", steps)
            return AkamaiSolveResult("solved", "sbsd", "SBSD 脚本自行提交并放行", steps)
        await asyncio.sleep(0.5)
    steps.append("sbsd_reload")
    try:
        await probe.page.goto(target_url, wait_until="domcontentloaded", timeout=15_000)
    except Exception as exc:
        return AkamaiSolveResult("unsolved", "sbsd", f"刷新目标页失败: {exc}", steps)
    return AkamaiSolveResult("unsolved", "sbsd", "SBSD 页面未自行放行, 已刷新一次", steps)


async def _warmup_async(
    probe: _AsyncPageProbe,
    *,
    target_url: str,
    deadline: float,
    steps: list[str],
) -> AkamaiSolveResult:
    """异步版边缘封禁兜底(同源首页预热)。"""

    origin = _origin_of(target_url)
    try:
        response = await probe.page.goto(origin + "/", wait_until="domcontentloaded", timeout=20_000)
    except Exception as exc:
        return AkamaiSolveResult("edge_block", "edge_block", f"首页预热失败: {exc}", steps)
    if response is not None and getattr(response, "status", None) in (403, 429):
        steps.append("warmup_root_blocked")
        return AkamaiSolveResult("edge_block", "edge_block", "同源首页也被封, 求解器无解", steps)

    stop_at = min(deadline, time.monotonic() + WARMUP_SENSOR_WAIT)
    while time.monotonic() < stop_at:
        signal = abck_stop_signal((await probe.cookies()).get("_abck"))
        if signal is not None and signal >= 0:
            steps.append(f"warmup_abck_valid:{signal}")
            break
        await asyncio.sleep(0.5)
    else:
        steps.append("warmup_abck_not_valid")
    try:
        await probe.page.goto(target_url, wait_until="domcontentloaded", timeout=20_000)
    except Exception as exc:
        return AkamaiSolveResult("edge_block", "edge_block", f"回到目标页失败: {exc}", steps)
    return AkamaiSolveResult("unsolved", "edge_block", "边缘封禁: 已做同源首页预热, 仍被拒", steps)


async def solve_akamai_page_async(
    page: Any,
    *,
    target_url: str,
    timeout_ms: int = 60_000,
    status: int | None = None,
    headers: dict[str, str] | None = None,
    log: logging.Logger | None = None,
) -> AkamaiSolveResult:
    """异步版 :func:`solve_akamai_page`, 用于 Scrapling 异步会话(批量抓取)。

    页面参数是异步 Playwright/Patchright 的 ``Page``。
    """

    logger = log or LOGGER
    deadline = time.monotonic() + max(1.0, timeout_ms / 1000)
    steps: list[str] = []
    with _AsyncPageProbe(page) as probe:
        signal = detect_akamai(
            await probe.html(), status=status, headers=headers, cookies=await probe.cookies()
        )
        if signal.kind in ("none", "bot_manager"):
            return AkamaiSolveResult("no_challenge", signal.kind, "页面没有 Akamai 挑战", steps)
        logger.info("Akamai: 识别到 %s (%s)", signal.kind, signal.detail or "-")
        if signal.kind == "edge_block":
            return await _warmup_async(
                probe, target_url=target_url, deadline=deadline, steps=steps
            )
        if signal.kind == "sbsd":
            return await _solve_sbsd_async(
                probe, target_url=target_url, deadline=deadline, steps=steps
            )
        return await _solve_sec_cpt_async(
            probe, target_url=target_url, deadline=deadline, signal=signal, steps=steps
        )


def _origin_of(url: str) -> str:
    """URL 的 ``scheme://host[:port]``。"""

    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}"


class _PageProbe:
    """对同步 Playwright/Patchright 页面的一层薄封装, 便于测试时替换。"""

    def __init__(self, page: Any) -> None:
        self.page = page
        self.sensor_posts = 0
        self.sbsd_posts = 0
        self.documents = 0

    # -- 事件 ---------------------------------------------------------------
    def _on_request(self, request: Any) -> None:
        try:
            if request.method != "POST":
                return
            body = request.post_data or ""
        except Exception:
            return
        if body.startswith('{"sensor_data"'):
            self.sensor_posts += 1
        elif body.startswith('{"body"'):
            self.sbsd_posts += 1

    def _on_response(self, response: Any) -> None:
        try:
            request = response.request
            if request.resource_type != "document":
                return
            if request.frame is not None and request.frame != self.page.main_frame:
                return
        except Exception:
            return
        self.documents += 1

    def __enter__(self) -> _PageProbe:
        self.page.on("request", self._on_request)
        self.page.on("response", self._on_response)
        return self

    def __exit__(self, *_args: Any) -> None:
        for event, handler in (("request", self._on_request), ("response", self._on_response)):
            try:
                self.page.remove_listener(event, handler)
            except Exception:
                pass

    # -- 读取 ---------------------------------------------------------------
    def html(self) -> str:
        return str(self.page.content())

    def cookies(self) -> dict[str, str]:
        try:
            return {str(item.get("name")): str(item.get("value")) for item in self.page.context.cookies()}
        except Exception:
            return {}

    def status(self) -> int | None:
        try:
            return self.page.evaluate("() => window.performance.getEntriesByType('navigation')[0]?.responseStatus ?? null")
        except Exception:
            return None


_POST_JSON_JS = """
async ({url, body}) => {
  try {
    const response = await fetch(url, {
      method: 'POST',
      credentials: 'include',
      headers: {'content-type': 'application/json'},
      body: body,
    });
    return {status: response.status, ok: response.ok};
  } catch (error) {
    return {status: 0, ok: false, error: String(error)};
  }
}
"""

_GET_JSON_JS = """
async ({url}) => {
  try {
    const response = await fetch(url, {credentials: 'include'});
    return {status: response.status, ok: response.ok};
  } catch (error) {
    return {status: 0, ok: false, error: String(error)};
  }
}
"""


def _sleep_until(deadline: float, seconds: float) -> bool:
    """睡到目标时刻; 返回 False 表示超出总预算。"""

    target = time.monotonic() + max(0.0, seconds)
    while time.monotonic() < target:
        if time.monotonic() >= deadline:
            return False
        time.sleep(min(0.25, max(0.0, target - time.monotonic())))
    return time.monotonic() < deadline


def _sec_cpt_cleared(probe: _PageProbe, documents: int) -> bool:
    """挑战是否已经过去: `sec_cpt` 出现 ``~3~``, 或出现了不带挑战标记的新文档。"""

    if "~3~" in probe.cookies().get("sec_cpt", ""):
        return True
    if probe.documents <= documents:
        return False
    sample = probe.html()[:CHALLENGE_PAGE_MAX_BYTES].lower()
    return not any(marker in sample for marker in SEC_CPT_MARKERS)


def _solve_sec_cpt(
    probe: _PageProbe,
    *,
    target_url: str,
    deadline: float,
    signal: AkamaiSignal,
    steps: list[str],
) -> AkamaiSolveResult:
    """处理 SEC-CPT 挑战: 先等页面自己解, 不行再本地算 PoW 并从页面内提交。"""

    html = probe.html()
    challenge = parse_sec_cpt_html(html) or parse_sec_cpt_json(html)
    provider = challenge.provider if challenge else (signal.provider or "crypto")
    duration = challenge.duration if challenge else signal.duration
    documents = probe.documents
    grace = SEC_GRACE_SENSOR if provider == "behavioral" else SEC_GRACE_POW

    # 阶段 A: 让页面自己的 iframe 去解(它会等满 duration 再算 PoW, 然后自己重载)。
    phase_a_start = time.monotonic()
    phase_a_end = min(deadline, phase_a_start + float(duration) + grace)
    while time.monotonic() < phase_a_end:
        if _sec_cpt_cleared(probe, documents):
            steps.append("sec_cpt_self_solved")
            return AkamaiSolveResult("solved", "sec_cpt", "页面自己解开了挑战", steps)
        time.sleep(0.5)
    steps.append("sec_cpt_self_solve_timeout")

    if challenge is None or not challenge.has_pow:
        # behavioral 型或没解析出参数: 本模块不伪造行为数据, 只能再等一次并刷新。
        steps.append("sec_cpt_no_local_pow")
        try:
            probe.page.goto(target_url, wait_until="domcontentloaded", timeout=15_000)
        except Exception as exc:
            return AkamaiSolveResult("unsolved", "sec_cpt", f"刷新目标页失败: {exc}", steps)
        return AkamaiSolveResult("unsolved", "sec_cpt", "只有行为型挑战, 本模块不伪造行为数据", steps)

    cookie = probe.cookies().get("sec_cpt", "")
    sec = cookie.split("~", 1)[0] if cookie else ""
    if not sec:
        steps.append("sec_cpt_missing_cookie")
        return AkamaiSolveResult("unsolved", "sec_cpt", "没有 sec_cpt cookie, 无法计算 PoW", steps)

    # 服务端要求的最短等待(duration)必须已过, 否则提交会被拒。
    remaining_wait = float(duration) - (time.monotonic() - phase_a_start)
    if remaining_wait > 0 and not _sleep_until(deadline, remaining_wait):
        return AkamaiSolveResult("unsolved", "sec_cpt", "等待最短挑战时长时超出预算", steps)

    try:
        answers = solve_sec_cpt_answers(sec, challenge, deadline=deadline - 1.0)
    except (TimeoutError, ValueError) as exc:
        steps.append("sec_cpt_pow_failed")
        return AkamaiSolveResult("unsolved", "sec_cpt", f"本地 PoW 失败: {exc}", steps)
    steps.append(f"sec_cpt_pow_solved:{len(answers)}")

    payload = json.dumps({"token": challenge.token, "answers": answers})
    try:
        posted = probe.page.evaluate(
            _POST_JSON_JS, {"url": f"/_sec/verify?provider={provider}", "body": payload}
        )
    except Exception as exc:
        steps.append("sec_cpt_post_failed")
        return AkamaiSolveResult("unsolved", "sec_cpt", f"提交 PoW 答案失败: {exc}", steps)
    steps.append(f"sec_cpt_post:{posted.get('status') if isinstance(posted, dict) else '?'}")

    try:
        probe.page.evaluate(_GET_JSON_JS, {"url": "/_sec/cp_challenge/verify"})
    except Exception:
        pass

    cleared = "~3~" in probe.cookies().get("sec_cpt", "")
    try:
        probe.page.goto(target_url, wait_until="domcontentloaded", timeout=15_000)
    except Exception as exc:
        return AkamaiSolveResult("unsolved", "sec_cpt", f"回到目标页失败: {exc}", steps)
    if cleared:
        steps.append("sec_cpt_cookie_cleared")
        return AkamaiSolveResult("solved", "sec_cpt", "PoW 已提交并放行", steps)
    steps.append("sec_cpt_not_cleared")
    return AkamaiSolveResult("unsolved", "sec_cpt", "提交后 sec_cpt 仍未放行", steps)


def _solve_sbsd(
    probe: _PageProbe,
    *,
    target_url: str,
    deadline: float,
    steps: list[str],
) -> AkamaiSolveResult:
    """处理 SBSD 挑战页: 脚本会自己提交并重载, 等不到就手动刷一次。"""

    documents = probe.documents
    posts = probe.sbsd_posts
    wait_end = min(deadline, time.monotonic() + 10.0)
    while time.monotonic() < wait_end:
        if probe.sbsd_posts - posts >= 2 or probe.documents > documents:
            steps.append(f"sbsd_posts:{probe.sbsd_posts - posts}")
            try:
                probe.page.goto(target_url, wait_until="domcontentloaded", timeout=15_000)
            except Exception as exc:
                return AkamaiSolveResult("unsolved", "sbsd", f"回到目标页失败: {exc}", steps)
            return AkamaiSolveResult("solved", "sbsd", "SBSD 脚本自行提交并放行", steps)
        time.sleep(0.5)
    steps.append("sbsd_reload")
    try:
        probe.page.goto(target_url, wait_until="domcontentloaded", timeout=15_000)
    except Exception as exc:
        return AkamaiSolveResult("unsolved", "sbsd", f"刷新目标页失败: {exc}", steps)
    return AkamaiSolveResult("unsolved", "sbsd", "SBSD 页面未自行放行, 已刷新一次", steps)


def _warmup(
    probe: _PageProbe,
    *,
    target_url: str,
    deadline: float,
    steps: list[str],
) -> AkamaiSolveResult:
    """边缘封禁的兜底: 去同源首页让 bmak 把 `_abck` 发到有效, 再回目标页。"""

    origin = _origin_of(target_url)
    try:
        response = probe.page.goto(origin + "/", wait_until="domcontentloaded", timeout=20_000)
    except Exception as exc:
        return AkamaiSolveResult("edge_block", "edge_block", f"首页预热失败: {exc}", steps)
    if response is not None and getattr(response, "status", None) in (403, 429):
        steps.append("warmup_root_blocked")
        return AkamaiSolveResult("edge_block", "edge_block", "同源首页也被封, 求解器无解", steps)

    stop_at = min(deadline, time.monotonic() + WARMUP_SENSOR_WAIT)
    while time.monotonic() < stop_at:
        signal = abck_stop_signal(probe.cookies().get("_abck"))
        if signal is not None and signal >= 0:
            steps.append(f"warmup_abck_valid:{signal}")
            break
        time.sleep(0.5)
    else:
        steps.append("warmup_abck_not_valid")
    try:
        probe.page.goto(target_url, wait_until="domcontentloaded", timeout=20_000)
    except Exception as exc:
        return AkamaiSolveResult("edge_block", "edge_block", f"回到目标页失败: {exc}", steps)
    return AkamaiSolveResult("unsolved", "edge_block", "边缘封禁: 已做同源首页预热, 仍被拒", steps)


def solve_akamai_page(
    page: Any,
    *,
    target_url: str,
    timeout_ms: int = 60_000,
    status: int | None = None,
    headers: dict[str, str] | None = None,
    log: logging.Logger | None = None,
) -> AkamaiSolveResult:
    """在已打开的页面上处理 Akamai 挑战。

    只在目标 origin 内导航(目标页、同源首页、SEC-CPT 校验接口), 不会跳去别的站点。
    页面参数是同步 Playwright/Patchright 的 ``Page``。

    :param page: 已导航到目标页的浏览器页面。
    :param target_url: 目标 URL, 求解失败或放行后要回到这里。
    :param timeout_ms: 求解的总时间预算。
    :param status: 首个响应的状态码(用于区分边缘封禁)。
    :param headers: 首个响应的响应头。
    """

    logger = log or LOGGER
    deadline = time.monotonic() + max(1.0, timeout_ms / 1000)
    steps: list[str] = []
    with _PageProbe(page) as probe:
        html = probe.html()
        effective_status = status if status is not None else probe.status()
        signal = detect_akamai(
            html, status=effective_status, headers=headers, cookies=probe.cookies()
        )
        if signal.kind in ("none", "bot_manager"):
            return AkamaiSolveResult("no_challenge", signal.kind, "页面没有 Akamai 挑战", steps)
        logger.info("Akamai: 识别到 %s (%s)", signal.kind, signal.detail or "-")
        if signal.kind == "edge_block":
            return _warmup(probe, target_url=target_url, deadline=deadline, steps=steps)
        if signal.kind == "sbsd":
            return _solve_sbsd(probe, target_url=target_url, deadline=deadline, steps=steps)
        return _solve_sec_cpt(
            probe, target_url=target_url, deadline=deadline, signal=signal, steps=steps
        )
