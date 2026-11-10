"""opencode_proxy.py 的回归测试：变量名审计、NO_PROXY 合并、URL 校验与写入范围。

pytest 风格（与兄弟 skill 的测试一致）；也可直接运行 `python tests/test_opencode_proxy.py`。
不启动服务、不出网：所有子命令都加 --no-restart / --no-probe，作用域限于临时 service.json。
"""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve()
SCRIPT = HERE.parent.parent / "scripts" / "opencode_proxy.py"


def load_module():
    spec = importlib.util.spec_from_file_location("opencode_proxy", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


proxy = load_module()


def temp_service(env: object) -> Path:
    tmp = Path(tempfile.mkdtemp(prefix="opencode-proxy-"))
    path = tmp / "service.json"
    path.write_text(
        json.dumps({"password": "probe-token", "env": env}, ensure_ascii=False), encoding="utf-8"
    )
    return path


def test_audit_detects_typos():
    issues = proxy.audit_names({"HPPTS_PROXY": "http://127.0.0.1:10808", "HPPT_PROXY": "x"})
    suggested = {item["name"]: item["suggest"] for item in issues}
    assert suggested == {"HPPTS_PROXY": "HTTPS_PROXY", "HPPT_PROXY": "HTTP_PROXY"}


def test_audit_ignores_canonical_and_unrelated():
    env = {
        "HTTP_PROXY": "http://127.0.0.1:10808",
        "https_proxy": "http://127.0.0.1:10808",
        "NO_PROXY": "localhost",
        "OPENCODE_CONSOLE_TOKEN": "oc_sk_x",
        "CORP_GATEWAY": "x",
    }
    assert proxy.audit_names(env) == []


def test_merge_no_proxy_keeps_order_and_adds_loopback():
    merged = proxy.merge_no_proxy("corp.local, 127.0.0.1")
    assert merged == "corp.local,127.0.0.1,localhost,::1"


def test_merge_no_proxy_normalizes_space_separator():
    assert proxy.merge_no_proxy("a.local b.local") == "a.local,b.local,localhost,127.0.0.1,::1"


def test_merge_no_proxy_dedupes_case_insensitively():
    assert proxy.merge_no_proxy("LocalHost,corp.local") == "LocalHost,corp.local,127.0.0.1,::1"


def test_check_no_proxy_reports_space_separator():
    problems = proxy.check_no_proxy({"NO_PROXY": "localhost 127.0.0.1"}, True)
    assert any("空格分隔" in item for item in problems)


def test_check_no_proxy_reports_missing_loopback():
    problems = proxy.check_no_proxy({"NO_PROXY": "corp.local"}, True)
    assert any("回环" in item for item in problems)


def test_check_no_proxy_silent_when_no_proxy_configured():
    assert proxy.check_no_proxy({}, False) == []


def test_parse_proxy_accepts_http_and_defaults_port():
    info = proxy.parse_proxy("http://127.0.0.1:10808")
    assert (info["host"], info["port"], info["auth"]) == ("127.0.0.1", 10808, False)
    assert proxy.parse_proxy("https://proxy.example")["port"] == 443


def test_parse_proxy_rejects_bad_input():
    for bad in ("", "socks5://127.0.0.1:1080", "http://", "http://127.0.0.1:abc", " http://127.0.0.1:10808"):
        try:
            proxy.parse_proxy(bad)
        except ValueError:
            continue
        raise AssertionError(f"应拒绝：{bad!r}")


def test_proxy_entries_prefers_uppercase():
    env = {"https_proxy": "lower", "HTTPS_PROXY": "upper", "NO_PROXY": "localhost"}
    assert proxy.proxy_entries(env) == {"HTTPS_PROXY": "upper"}


def test_evaluate_flags_live_mismatch():
    problems, _ = proxy.evaluate({"HTTPS_PROXY": "http://127.0.0.1:10808"}, {}, None)
    assert any("live 进程未加载" in item for item in problems)


def test_evaluate_flags_live_only_proxy():
    problems, _ = proxy.evaluate({}, {"HTTPS_PROXY": "http://127.0.0.1:10808"}, None)
    assert any("存储层没有代理变量" in item for item in problems)


def test_evaluate_notes_direct_connection():
    problems, notes = proxy.evaluate({}, {}, None)
    assert problems == []
    assert any("走直连" in item for item in notes)


def test_load_service_parses_string_form():
    path = temp_service("{'HTTPS_PROXY': 'http://127.0.0.1:10808'}")
    data, env, fmt = proxy.load_service(path)
    assert env == {"HTTPS_PROXY": "http://127.0.0.1:10808"}
    assert fmt == proxy.FORMAT_STRING


def test_load_service_rejects_unparsable_string():
    path = temp_service("not a mapping")
    try:
        proxy.load_service(path)
    except proxy.ServiceFormatError:
        return
    raise AssertionError("应抛出 ServiceFormatError")


def test_cli_set_and_unset_scope():
    import contextlib
    import io

    path = temp_service({"KEEP_ME": "1", "NO_PROXY": "corp.local"})
    base = ["--service-json", str(path)]

    with contextlib.redirect_stdout(io.StringIO()):
        assert proxy.main(["set", "http://127.0.0.1:10808", "--no-restart", *base]) == 0
    stored = json.loads(path.read_text(encoding="utf-8"))
    assert stored["password"] == "probe-token"
    assert stored["env"]["KEEP_ME"] == "1"
    assert stored["env"]["HTTP_PROXY"] == "http://127.0.0.1:10808"
    assert stored["env"]["HTTPS_PROXY"] == "http://127.0.0.1:10808"
    assert stored["env"]["NO_PROXY"] == "corp.local,localhost,127.0.0.1,::1"

    with contextlib.redirect_stdout(io.StringIO()):
        assert proxy.main(["unset", "--no-restart", *base]) == 0
    stored = json.loads(path.read_text(encoding="utf-8"))
    assert "HTTP_PROXY" not in stored["env"] and "HTTPS_PROXY" not in stored["env"]
    assert stored["env"]["NO_PROXY"] == "corp.local,localhost,127.0.0.1,::1"
    assert stored["env"]["KEEP_ME"] == "1"

    with contextlib.redirect_stdout(io.StringIO()):
        assert proxy.main(["unset", "--all", "--no-restart", *base]) == 0
    assert "NO_PROXY" not in json.loads(path.read_text(encoding="utf-8"))["env"]


def test_cli_set_drops_typo_names():
    import contextlib
    import io

    path = temp_service({"HPPTS_PROXY": "http://127.0.0.1:10808", "NO_PROXY": "localhost"})
    with contextlib.redirect_stdout(io.StringIO()):
        assert proxy.main(
            ["set", "http://127.0.0.1:10808", "--no-restart", "--service-json", str(path)]
        ) == 0
    env = json.loads(path.read_text(encoding="utf-8"))["env"]
    assert "HPPTS_PROXY" not in env
    assert env["HTTP_PROXY"] == env["HTTPS_PROXY"] == "http://127.0.0.1:10808"


def test_cli_set_removes_typo_names_on_unset():
    import contextlib
    import io

    path = temp_service({"HPPTS_PROXY": "http://127.0.0.1:10808", "KEEP_ME": "1"})
    base = ["--service-json", str(path)]
    with contextlib.redirect_stdout(io.StringIO()):
        assert proxy.main(["unset", "--no-restart", *base]) == 0
    env = json.loads(path.read_text(encoding="utf-8"))["env"]
    assert env == {"KEEP_ME": "1"}


def test_cli_status_json_never_leaks_other_env(monkeypatch_free=None):
    path = temp_service({"HTTP_PROXY": "http://127.0.0.1:10808", "OPENCODE_CONSOLE_TOKEN": "oc_sk_secret"})
    originals = (proxy.service_pid, proxy.read_live_env)
    proxy.service_pid = lambda: None
    proxy.read_live_env = lambda pid: (None, "stub")
    try:
        import contextlib
        import io

        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = proxy.main(["status", "--json", "--no-probe", "--service-json", str(path)])
    finally:
        proxy.service_pid, proxy.read_live_env = originals
    report = json.loads(buffer.getvalue())
    assert code == proxy.EXIT_PROBLEM
    assert report["storage"]["proxy"] == {"HTTP_PROXY": "http://127.0.0.1:10808"}
    assert "oc_sk_secret" not in buffer.getvalue()


def _run_all() -> int:
    failed = 0
    for name, func in sorted(globals().items()):
        if not name.startswith("test_") or not callable(func):
            continue
        try:
            func()
        except AssertionError as exc:
            failed += 1
            print(f"FAIL {name}: {exc}")
        else:
            print(f"ok   {name}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(_run_all())
