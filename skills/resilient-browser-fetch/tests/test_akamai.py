"""Akamai 检测与求解的测试: 纯函数 + 本地仿真挑战页的端到端流程。"""

from __future__ import annotations

import base64
import hashlib
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, ClassVar

import akamai
import pytest
import resilient_fetch

SEC_CPT_HTML = """<!DOCTYPE html>
<html><head><title>Challenge</title></head>
<body>
<div id="sec-if-cpt-container" role="main" style="display: none">
  <div class="behavioral-content"><div id="sec-bc-text-container"></div></div>
  <div id="sec-bc-tile-parent"><div id="sec-bc-tile-container"></div></div>
  <p class="scf-akamai-protected-by">Powered and protected by</p>
</div>
<iframe data-duration="{duration}" provider="{provider}" challenge="{challenge}" src="/_sec/cp_challenge/crypto_message-4-3.htm"></iframe>
</body></html>
"""

SBSD_HTML = """<!DOCTYPE html>
<html><head><title>Challenge Page</title></head>
<body>
<script type="text/javascript" src="/.well-known/sbsd/b2ea79?v=d86025d3-fa31-2dab-d4d7-b8d71bf3172f&amp;t=126116865"></script>
<div id="sec-if-cpt-container" role="main" style="display: none"></div>
</body></html>
"""

EDGE_BLOCK_HTML = (
    "<html><head> <title>Access Denied</title> </head><body> <h1>Access Denied</h1> "
    "You don't have permission to access \"http://www.example.com/\" on this server.<p> "
    "Reference #18.a5f7d517.1792565137.49bd9361 </p><p>https://errors.edgesuite.net/18.a5f7d517.1792565137.49bd9361"
    " </p> </body></html>"
)

NORMAL_HTML = "<html><head><title>Product</title></head><body><h1>Real product page</h1></body></html>"

# 实测的边缘封禁页: 硬拒绝 + Reference #18, 同时带一个混淆的 SBSD 脚本标签。
# 按脚本分支先判会把它误报成"可求解的挑战页"(akamai_challenge), 而边缘封禁没有挑战窗口。
EDGE_BLOCK_WITH_SBSD_HTML = (
    "<html><head>\n<title>Access Denied</title>\n</head><body>\n<h1>Access Denied</h1>\n \n"
    "You don't have permission to access \"http://www2.hm.com/en_us/productpage.1367517001.html\" "
    "on this server.<p>\nReference #18.ad51c317.1792573687.61d891a7\n</p><p>"
    "https://errors.edgesuite.net/18.ad51c317.1792573687.61d891a7</p>"
    "<script type=\"text/javascript\" src=\"/hnuG7-/Yvf/Wl9/0TkHU3o8/cJOcNmYwb1GO/WmM9MQ/"
    "DCgcaR/pSa0kV?v=21eb9360-5437-e892-1cd6-6d64917917c3\" defer=\"\"></script>\n\n"
    "</body></html>"
)


def _challenge_payload(difficulty: int = 64, count: int = 1) -> tuple[str, dict[str, Any]]:
    """构造挑战数据与它的 base64 形式。"""

    data = {
        "token": "token-abc",
        "timestamp": 1792565137,
        "nonce": "nonce-xyz",
        "difficulty": difficulty,
        "count": count,
    }
    return base64.b64encode(json.dumps(data).encode("utf-8")).decode("ascii"), data


# ---- 检测 ------------------------------------------------------------------


def test_detect_sec_cpt_container() -> None:
    challenge, _ = _challenge_payload()
    html = SEC_CPT_HTML.format(duration=30, provider="crypto", challenge=challenge)
    signal = akamai.detect_akamai(html)
    assert signal.kind == "sec_cpt"
    assert signal.provider == "crypto"
    assert signal.duration == 30


def test_detect_sbsd_script() -> None:
    sbsd_only = (
        "<html><head><title>Challenge Page</title></head><body>"
        "<script type=\"text/javascript\" src=\"/.well-known/sbsd/b2ea79"
        "?v=d86025d3-fa31-2dab-d4d7-b8d71bf3172f&amp;t=126116865\"></script>"
        "</body></html>"
    )
    signal = akamai.detect_akamai(sbsd_only)
    assert signal.kind == "sbsd"


def test_detect_sec_cpt_wins_over_sbsd_when_both_present() -> None:
    """真实挑战页两者同时出现(容器 + SBSD 脚本), 判定顺序与上游一致: 先认 SEC-CPT。"""

    signal = akamai.detect_akamai(SBSD_HTML)
    assert signal.kind == "sec_cpt"


def test_passive_sbsd_on_a_real_page_is_not_a_challenge() -> None:
    """实测: 正常商品页也带 /.well-known/sbsd 传感器脚本, 不能据此判成挑战页。"""

    body = (
        "<html><head><title>Breakfast Included Package</title></head><body>"
        + "<p>产品正文</p>" * 8000
        + '<script src="/.well-known/sbsd/16ab20?v=33565e70-8b27-bff3-8fa9-440a20fc17c9" defer=""></script>'
        + "</body></html>"
    )
    assert len(body) > akamai.CHALLENGE_PAGE_MAX_BYTES
    signal = akamai.detect_akamai(body)
    assert signal.kind == "bot_manager"
    assert signal.detail == "sbsd_sensor"


def test_detect_edge_block() -> None:
    signal = akamai.detect_akamai(EDGE_BLOCK_HTML, status=403)
    assert signal.kind == "edge_block"
    assert signal.reference == "18.a5f7d517.1792565137.49bd9361"


def test_edge_block_with_sbsd_script_is_not_mistaken_for_a_challenge() -> None:
    """实测的封禁页带混淆 SBSD 脚本标签; 判成挑战页会让人去加求解器, 而封禁没有挑战窗口。"""

    signal = akamai.detect_akamai(EDGE_BLOCK_WITH_SBSD_HTML)
    assert signal.kind == "edge_block"
    assert signal.reference == "18.ad51c317.1792573687.61d891a7"

    reasons = resilient_fetch.block_reasons(EDGE_BLOCK_WITH_SBSD_HTML)
    assert "akamai_edge_block" in reasons
    assert "akamai_challenge" not in reasons


def test_detect_normal_page() -> None:
    assert akamai.detect_akamai(NORMAL_HTML).kind == "none"


def test_detect_bot_manager_cookies_only() -> None:
    signal = akamai.detect_akamai(NORMAL_HTML, cookies={"_abck": "~0~-1~-1~-1", "bm_sz": "x"})
    assert signal.kind == "bot_manager"


def test_block_reasons_separates_challenge_from_edge_block() -> None:
    import resilient_fetch

    challenge, _ = _challenge_payload()
    html = SEC_CPT_HTML.format(duration=30, provider="crypto", challenge=challenge)
    assert "akamai_challenge" in resilient_fetch.block_reasons(html)
    assert "akamai_edge_block" in resilient_fetch.block_reasons(EDGE_BLOCK_HTML)
    assert "akamai_edge_block" not in resilient_fetch.block_reasons(NORMAL_HTML)


# ---- _abck 语义 ------------------------------------------------------------


def test_abck_state_and_stop_signal() -> None:
    assert akamai.abck_state("~-1~-1~-1") == "invalid"
    assert akamai.abck_state("~0~-1~-1") == "valid"
    assert akamai.abck_state(None) == "missing"
    assert akamai.abck_stop_signal("~-1~-1~-1") == -1
    assert akamai.abck_stop_signal("~0~-1~-1") == 0
    assert akamai.abck_stop_signal("garbage") is None
    # 第四个 ~ 字段 >= 0 表示 cookie 被受保护接口作废
    assert akamai.abck_invalidated("~0~-1~-1") is False
    assert akamai.abck_invalidated("~0~-1~0~-1") is True


# ---- PoW -------------------------------------------------------------------


def test_solve_sec_cpt_answers_satisfies_difficulty() -> None:
    _challenge, data = _challenge_payload(difficulty=32, count=2)
    challenge = akamai.SecCptChallenge(
        provider="crypto",
        duration=30,
        token=data["token"],
        timestamp=data["timestamp"],
        nonce=data["nonce"],
        difficulty=data["difficulty"],
        count=data["count"],
    )
    answers = akamai.solve_sec_cpt_answers("secrethash", challenge)
    assert len(answers) == 2
    assert akamai.verify_sec_cpt_answer("secrethash", challenge, answers[0])
    # 第二个答案的难度加一
    assert akamai.verify_sec_cpt_answer("secrethash", challenge, answers[1], difficulty=33)


def test_solve_sec_cpt_answers_matches_manual_hash() -> None:
    challenge = akamai.SecCptChallenge(
        provider="crypto", duration=1, token="t", timestamp=7, nonce="n", difficulty=8, count=1
    )
    answers = akamai.solve_sec_cpt_answers("sec", challenge)
    digest = hashlib.sha256(f"sec7n8{answers[0]}".encode("ascii")).digest()
    assert int.from_bytes(digest, "big") % 8 == 0


def test_solve_sec_cpt_answers_rejects_bad_difficulty() -> None:
    challenge = akamai.SecCptChallenge(provider="crypto", duration=1, difficulty=0)
    with pytest.raises(ValueError):
        akamai.solve_sec_cpt_answers("sec", challenge)


# ---- 挑战解析 --------------------------------------------------------------


def test_parse_sec_cpt_html() -> None:
    challenge_b64, data = _challenge_payload()
    html = SEC_CPT_HTML.format(duration=17, provider="adaptive", challenge=challenge_b64)
    parsed = akamai.parse_sec_cpt_html(html)
    assert parsed is not None
    assert parsed.duration == 17
    assert parsed.provider == "adaptive"
    assert parsed.token == data["token"]
    assert parsed.nonce == data["nonce"]
    assert parsed.difficulty == data["difficulty"]
    assert parsed.has_pow


def test_parse_sec_cpt_json() -> None:
    payload = json.dumps(
        {
            "sec-cp-challenge": "true",
            "provider": "crypto",
            "branding_url_content": "/_sec/cp_challenge/crypto_message-4-3.htm",
            "chlg_duration": 30,
            "token": "tok",
            "timestamp": 1,
            "nonce": "non",
            "difficulty": 4,
            "count": 1,
        }
    )
    parsed = akamai.parse_sec_cpt_json(payload)
    assert parsed is not None
    assert parsed.duration == 30
    assert parsed.difficulty == 4
    assert parsed.provider == "crypto"


def test_parse_sec_cpt_json_rejects_normal_payload() -> None:
    assert akamai.parse_sec_cpt_json('{"hello": "world"}') is None


# ---- 端到端: 本地仿真 SEC-CPT ------------------------------------------------


class _SecCptHandler(BaseHTTPRequestHandler):
    """仿真 Akamai SEC-CPT: 挑战页 → 校验 PoW → 放行正文。"""

    difficulty = 16
    sec = "sec-value"
    solved = False
    received: ClassVar[list[dict[str, Any]]] = []

    def log_message(self, format: str, *args: Any) -> None:  # 静音
        return

    def _challenge_b64(self) -> str:
        data = {
            "token": "token-abc",
            "timestamp": 1792565137,
            "nonce": "nonce-xyz",
            "difficulty": self.difficulty,
            "count": 1,
        }
        return base64.b64encode(json.dumps(data).encode("utf-8")).decode("ascii")

    def do_GET(self) -> None:
        if self.path.startswith("/_sec/cp_challenge/verify"):
            self.send_response(200)
            self.send_header("Set-Cookie", f"sec_cpt={self.sec}~3~; Path=/")
            self.end_headers()
            self.wfile.write(b"ok")
            return
        if self.path == "/protected":
            if not type(self).solved:
                body = SEC_CPT_HTML.format(
                    duration=1, provider="crypto", challenge=self._challenge_b64()
                ).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Set-Cookie", f"sec_cpt={self.sec}~0~; Path=/")
                self.end_headers()
                self.wfile.write(body)
                return
            body = b"<html><head><title>Protected product</title></head><body>REAL CONTENT</body></html>"
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Set-Cookie", f"sec_cpt={self.sec}~3~; Path=/")
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_response(404)
        self.end_headers()

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length).decode("utf-8") if length else ""
        if self.path.startswith("/_sec/verify"):
            payload = json.loads(raw)
            type(self).received.append(payload)
            answer = payload["answers"][0]
            digest = hashlib.sha256(
                f"{self.sec}1792565137nonce-xyz{self.difficulty}{answer}".encode("ascii")
            ).digest()
            if int.from_bytes(digest, "big") % self.difficulty == 0:
                type(self).solved = True
                self.send_response(200)
                self.send_header("Set-Cookie", f"sec_cpt={self.sec}~3~; Path=/")
                self.end_headers()
                self.wfile.write(b"ok")
                return
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b"bad")
            return
        self.send_response(404)
        self.end_headers()


@pytest.fixture
def sec_cpt_server() -> Any:
    _SecCptHandler.solved = False
    _SecCptHandler.received = []
    server = ThreadingHTTPServer(("127.0.0.1", 0), _SecCptHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()


def test_end_to_end_solves_sec_cpt_with_local_server(sec_cpt_server: Any) -> None:
    playwright = pytest.importorskip("patchright.sync_api")
    url = f"http://127.0.0.1:{sec_cpt_server.server_address[1]}/protected"
    with playwright.sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, args=["--no-sandbox"])
        try:
            page = browser.new_page()
            page.goto(url, wait_until="domcontentloaded")
            assert akamai.detect_akamai(page.content()).kind == "sec_cpt"
            result = akamai.solve_akamai_page(
                page, target_url=url, timeout_ms=30_000, status=200
            )
            assert result.outcome == "solved", result.steps
            assert "REAL CONTENT" in page.content()
        finally:
            browser.close()
    assert _SecCptHandler.received, "求解器应当向 /_sec/verify 提交过 PoW 答案"
    assert _SecCptHandler.solved


def test_end_to_end_edge_block_is_reported(sec_cpt_server: Any) -> None:
    playwright = pytest.importorskip("patchright.sync_api")
    url = f"http://127.0.0.1:{sec_cpt_server.server_address[1]}/missing"
    with playwright.sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, args=["--no-sandbox"])
        try:
            page = browser.new_page()
            page.goto(url, wait_until="domcontentloaded")
            page.set_content(EDGE_BLOCK_HTML)
            result = akamai.solve_akamai_page(
                page, target_url=url, timeout_ms=10_000, status=403
            )
            assert result.outcome in ("edge_block", "unsolved")
            assert result.kind == "edge_block"
        finally:
            browser.close()


@pytest.mark.asyncio
async def test_end_to_end_async_solves_sec_cpt(sec_cpt_server: Any) -> None:
    """批量会话走 Scrapling 异步接口, 求解器必须有异步孪生。"""

    playwright = pytest.importorskip("patchright.async_api")
    url = f"http://127.0.0.1:{sec_cpt_server.server_address[1]}/protected"
    async with playwright.async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True, args=["--no-sandbox"])
        try:
            page = await browser.new_page()
            await page.goto(url, wait_until="domcontentloaded")
            result = await akamai.solve_akamai_page_async(
                page, target_url=url, timeout_ms=30_000, status=200
            )
            assert result.outcome == "solved", result.steps
            assert "REAL CONTENT" in await page.content()
        finally:
            await browser.close()
    assert _SecCptHandler.received, "异步求解器应当提交过 PoW 答案"
