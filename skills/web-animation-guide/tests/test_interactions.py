#!/usr/bin/env python3
"""Run browser regressions against the actual Markdown interaction examples.

Usage: python skills/web-animation-guide/tests/test_interactions.py --artifacts <directory>
Requires the existing Playwright Python package and installed Chromium.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import unittest
from pathlib import Path

from playwright.sync_api import Page, sync_playwright


SKILL_DIR = Path(__file__).resolve().parents[1]
SOURCE = SKILL_DIR / "references" / "interactions.md"


def fixture(section: str) -> str:
    """Render the documentation itself, without a second implementation."""
    source = SOURCE.read_text(encoding="utf-8")
    content = next(
        part for part in re.split(r"(?m)^## ", source)[1:] if part.startswith(section)
    )
    blocks = re.findall(r"```(html|css|js)\n(.*?)\n```", content, re.DOTALL)
    html = "\n".join(code for language, code in blocks if language == "html")
    css = "\n".join(code for language, code in blocks if language == "css")
    js = "\n".join(code for language, code in blocks if language == "js")
    return (
        '<!doctype html><html lang="zh"><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        "<style>body {font:16px/1.6 system-ui;margin:24px;} "
        "button {min-height:44px;} dialog {max-width:calc(100vw - 64px);}"
        f"{css}</style><body>{html}<script>{js}</script></body></html>"
    )


class InteractionTests(unittest.TestCase):
    artifacts: Path | None = None

    @classmethod
    def setUpClass(cls) -> None:
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.browser.close()
        cls.playwright.stop()

    def setUp(self) -> None:
        self.context = self.browser.new_context(
            viewport={"width": 390, "height": 844},
            device_scale_factor=1,
            locale="zh-CN",
            timezone_id="Asia/Shanghai",
            reduced_motion="no-preference",
        )
        self.page = self.context.new_page()
        self.errors: list[str] = []
        self.page.on("pageerror", lambda error: self.errors.append(str(error)))

    def tearDown(self) -> None:
        self.context.close()
        self.assertEqual(self.errors, [], "Browser exceptions or unhandled rejections")

    def load(self, section: str, reduced: bool = False) -> Page:
        self.page.close()
        self.page = self.context.new_page()
        self.page.on("pageerror", lambda error: self.errors.append(str(error)))
        self.page.emulate_media(reduced_motion="reduce" if reduced else "no-preference")
        self.page.set_content(fixture(section))
        return self.page

    def assert_disclosure(self, open_: bool) -> None:
        self.page.wait_for_function(
            """open => {
              const panel = document.querySelector('#disclosure-panel');
              return panel.hidden === !open && panel.inert === !open &&
                panel.getAttribute('aria-hidden') === String(!open) &&
                document.querySelector('#disclosure-toggle').getAttribute('aria-expanded') === String(open);
            }""",
            arg=open_,
        )

    def test_dialog_enter_exit_and_focus(self) -> None:
        for reduced in (False, True):
            with self.subTest(reduced=reduced):
                page = self.load("原生弹窗", reduced)
                page.locator("#dialog-open").click()
                self.assertTrue(page.locator("dialog").evaluate("el => el.open"))
                self.assertEqual(
                    page.evaluate("document.activeElement.id"), "dialog-close"
                )
                if not reduced:
                    page.wait_for_function(
                        "dlg.getAnimations().some(a => a.transitionProperty === 'opacity')"
                    )
                else:
                    self.assertEqual(page.evaluate("dlg.getAnimations().length"), 0)
                page.wait_for_function("dlg.getAnimations().length === 0")
                page.locator("#dialog-close").click()
                self.assertFalse(page.locator("dialog").evaluate("el => el.open"))
                self.assertEqual(
                    page.evaluate("document.activeElement.id"), "dialog-open"
                )
                if not reduced:
                    self.assertTrue(
                        page.evaluate(
                            "dlg.getAnimations().some(a => a.transitionProperty === 'opacity')"
                        )
                    )
                page.wait_for_function("getComputedStyle(dlg).display === 'none'")

    def test_dialog_escape_and_rapid_reopen(self) -> None:
        page = self.load("原生弹窗")
        page.locator("#dialog-open").click()
        page.keyboard.press("Escape")
        self.assertFalse(page.locator("dialog").evaluate("el => el.open"))
        self.assertEqual(page.evaluate("document.activeElement.id"), "dialog-open")
        page.evaluate("openButton.click(); closeButton.click(); openButton.click()")
        page.wait_for_function(
            "dlg.open && document.activeElement.id === 'dialog-close'"
        )

    def test_dialog_exit_preserves_layout_throughout(self) -> None:
        for width in (390, 1280):
            for layout in ("flex", "grid"):
                with self.subTest(width=width, layout=layout):
                    page = self.load("原生弹窗")
                    page.set_viewport_size({"width": width, "height": 844})
                    if layout == "grid":
                        page.add_style_tag(content=".motion-dialog[open]{display:grid}")
                    page.locator("#dialog-open").click()
                    page.wait_for_function(
                        "dlg.open && dlg.getAnimations().length === 0"
                    )
                    # Layout geometry excludes the intended whole-dialog translation.
                    sample = """() => ({
                      size: [dlg.offsetWidth, dlg.offsetHeight],
                      text: dlg.textContent,
                      nodes: [...dlg.querySelectorAll('*')].map(el =>
                        [el.offsetWidth, el.offsetHeight, el.offsetLeft, el.offsetTop])
                    })"""
                    before = page.evaluate(sample)
                    page.evaluate(
                        "closeButton.click(); dlg.getAnimations().forEach(a => a.pause())"
                    )
                    self.assertFalse(page.evaluate("dlg.open"))
                    self.assertEqual(
                        page.evaluate("document.activeElement.id"), "dialog-open"
                    )
                    self.assertGreater(page.evaluate("dlg.getAnimations().length"), 0)
                    for fraction in (0, 0.25, 0.5, 0.75, 0.99):
                        page.evaluate(
                            """t => dlg.getAnimations().forEach(a => {
                              a.currentTime = Number(a.effect.getTiming().duration) * t;
                            })""",
                            fraction,
                        )
                        self.assertEqual(
                            page.evaluate(sample), before, f"Exit layout at {fraction}"
                        )
                    # Screenshot export is separate from the geometry assertions.
                    if self.artifacts is not None and width == 390 and layout == "flex":
                        self.artifacts.mkdir(parents=True, exist_ok=True)
                        page.evaluate(
                            "dlg.getAnimations().forEach(a => {a.currentTime = Number(a.effect.getTiming().duration) / 2})"
                        )
                        page.screenshot(
                            path=str(self.artifacts / "dialog-exit-mid.png")
                        )
                    page.evaluate("dlg.getAnimations().forEach(a => a.finish())")
                    page.wait_for_function("getComputedStyle(dlg).display === 'none'")

    def test_dialog_no_transition_and_removed_invoker(self) -> None:
        page = self.load("原生弹窗")
        page.add_style_tag(
            content=".motion-dialog,.motion-dialog::backdrop {transition:none!important}"
        )
        page.locator("#dialog-open").click()
        page.evaluate("openButton.remove(); closeButton.click()")
        page.wait_for_function("!dlg.open && getComputedStyle(dlg).display === 'none'")
        self.assertEqual(page.evaluate("dlg.getAnimations().length"), 0)

    def test_disclosure_enter_exit_semantics(self) -> None:
        for reduced in (False, True):
            with self.subTest(reduced=reduced):
                page = self.load("下拉 disclosure", reduced)
                page.locator("#disclosure-toggle").click()
                self.assert_disclosure(True)
                page.locator("#disclosure-panel a").first.focus()
                page.keyboard.press("Escape")
                self.assertEqual(
                    page.evaluate("document.activeElement.id"), "disclosure-toggle"
                )
                self.assertTrue(
                    page.locator("#disclosure-panel").evaluate("el => el.inert")
                )
                self.assert_disclosure(False)

    def test_disclosure_rapid_commands_and_repeated_close(self) -> None:
        page = self.load("下拉 disclosure")
        page.evaluate(
            "disclosure.setOpen(true); disclosure.setOpen(false); disclosure.setOpen(true)"
        )
        self.assert_disclosure(True)
        page.evaluate("disclosure.setOpen(false); disclosure.setOpen(false)")
        self.assert_disclosure(False)

    def test_disclosure_animates_both_directions(self) -> None:
        page = self.load("下拉 disclosure")
        page.locator("#disclosure-toggle").click()
        page.wait_for_function(
            """document.querySelector('#disclosure-panel').getAnimations().length > 0 &&
            Number(getComputedStyle(document.querySelector('#disclosure-panel')).opacity) > 0 &&
            Number(getComputedStyle(document.querySelector('#disclosure-panel')).opacity) < 1"""
        )
        page.wait_for_function("document.getAnimations().length === 0")
        page.evaluate("void disclosure.setOpen(false)")
        page.wait_for_function(
            """document.querySelector('#disclosure-panel').getAnimations().length > 0 &&
            Number(getComputedStyle(document.querySelector('#disclosure-panel')).opacity) > 0 &&
            Number(getComputedStyle(document.querySelector('#disclosure-panel')).opacity) < 1"""
        )
        self.assert_disclosure(False)

    def test_disclosure_cancelled_exit(self) -> None:
        page = self.load("下拉 disclosure")
        page.evaluate("disclosure.setOpen(true)")
        self.assert_disclosure(True)
        page.evaluate(
            "disclosure.setOpen(false); document.querySelector('#disclosure-panel').getAnimations().forEach(a => a.cancel())"
        )
        self.assert_disclosure(False)
        self.assertEqual(
            page.locator("#disclosure-panel").evaluate(
                "el => el.getAnimations().length"
            ),
            0,
        )

    def test_disclosure_missing_api_and_zero_duration(self) -> None:
        for mode in ("missing-api", "zero-duration"):
            with self.subTest(mode=mode):
                page = self.load("下拉 disclosure")
                if mode == "missing-api":
                    page.evaluate(
                        "document.querySelector('#disclosure-panel').animate = undefined"
                    )
                else:
                    page.evaluate("""disclosure.dispose(); window.zero = createDisclosure(
                      document.querySelector('#disclosure-toggle'), document.querySelector('#disclosure-panel'),
                      {enter:0, exit:0});""")
                page.locator("#disclosure-toggle").click()
                self.assert_disclosure(True)
                page.locator("#disclosure-toggle").click()
                self.assert_disclosure(False)

    def test_disclosure_runtime_reduce_and_dispose(self) -> None:
        page = self.load("下拉 disclosure")
        page.evaluate("disclosure.setOpen(true); disclosure.setOpen(false)")
        page.emulate_media(reduced_motion="reduce")
        self.assert_disclosure(False)
        page.emulate_media(reduced_motion="no-preference")
        page.evaluate("disclosure.setOpen(true); disclosure.dispose()")
        self.assert_disclosure(False)
        page.locator("#disclosure-toggle").click()
        self.assert_disclosure(False)

    def test_busy_success_failure_and_retry(self) -> None:
        page = self.load("按钮忙态")
        page.locator("#busy-button").click()
        self.assertTrue(page.locator("#busy-button").is_disabled())
        self.assertEqual(
            page.locator("#busy-button").get_attribute("aria-busy"), "true"
        )
        page.wait_for_function("jobStatus.textContent === '设置已保存'")
        self.assertFalse(page.locator("#busy-button").is_disabled())
        page.locator("#fail-job").check()
        page.locator("#busy-button").click()
        page.wait_for_function("jobStatus.textContent.includes('失败')")
        self.assertFalse(page.locator("#busy-button").is_disabled())
        self.assertIsNone(page.locator("#busy-button").get_attribute("aria-busy"))
        page.locator("#fail-job").uncheck()
        page.locator("#busy-button").click()
        page.wait_for_function("jobStatus.textContent === '设置已保存'")

    def test_busy_prevents_reentry_and_short_task_flash(self) -> None:
        page = self.load("按钮忙态")
        result = page.evaluate("""async () => {
          let calls = 0; const b = busyButton; const label = b.querySelector('[data-label]');
          const originalNode = label; let flashed = false;
          const observer = new MutationObserver(records => { flashed ||= records.some(r => r.attributeName === 'hidden'); });
          observer.observe(b, {subtree:true, attributes:true, attributeFilter:['hidden']});
          const first = runBusy(b, '正在保存', async () => { calls++; await new Promise(r => setTimeout(r, 20)); });
          await runBusy(b, '正在保存', async () => { calls++; }); await first;
          observer.disconnect();
          return {calls, flashed, sameNode: b.querySelector('[data-label]') === originalNode, label:label.textContent, disabled:b.disabled};
        }""")
        self.assertEqual(
            result,
            {
                "calls": 1,
                "flashed": False,
                "sameNode": True,
                "label": "保存设置",
                "disabled": False,
            },
        )

    def test_busy_reduce_keeps_static_information(self) -> None:
        page = self.load("按钮忙态", True)
        page.locator("#busy-button").click()
        page.wait_for_function("!busyButton.querySelector('.busy-spinner').hidden")
        self.assertEqual(page.locator("[data-label]").inner_text(), "正在保存设置")
        self.assertEqual(
            page.locator(".busy-spinner").evaluate(
                "el => getComputedStyle(el).animationName"
            ),
            "none",
        )
        page.wait_for_function("jobStatus.textContent === '设置已保存'")

    def test_busy_restores_state_after_detach(self) -> None:
        page = self.load("按钮忙态")
        result = page.evaluate("""async () => {
          const job = runBusy(busyButton, '正在保存', async () => {
            await new Promise(r => setTimeout(r, 30)); throw new Error('failed');
          }, 0);
          busyButton.remove();
          try { await job; } catch (error) { if(error.message !== 'failed') throw error; }
          return {disabled:busyButton.disabled, busy:busyButton.getAttribute('aria-busy'),
            label:busyButton.querySelector('[data-label]').textContent};
        }""")
        self.assertEqual(result, {"disabled": False, "busy": None, "label": "保存设置"})

    def test_key_state_screenshots(self) -> None:
        if self.artifacts is None:
            return  # Behavior assertions remain active; artifact export is optional.
        self.artifacts.mkdir(parents=True, exist_ok=True)
        for section, action, name in (
            ("原生弹窗", "openButton.click()", "dialog-open"),
            ("下拉 disclosure", "disclosure.setOpen(true)", "disclosure-open"),
            ("按钮忙态", "busyButton.click()", "busy-reduced"),
        ):
            page = self.load(section, reduced=section == "按钮忙态")
            page.evaluate(action)
            if section == "按钮忙态":
                page.wait_for_function(
                    "!busyButton.querySelector('.busy-spinner').hidden"
                )
            else:
                page.wait_for_function("document.getAnimations().length === 0")
            self.assertFalse(
                page.evaluate("document.documentElement.scrollWidth > innerWidth")
            )
            page.screenshot(path=str(self.artifacts / f"{name}.png"))
            if section == "原生弹窗":
                page.locator("#dialog-close").click()
                page.wait_for_function("getComputedStyle(dlg).display === 'none'")
                page.screenshot(path=str(self.artifacts / "dialog-closed.png"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--artifacts", type=Path, help="Optional screenshot and result directory"
    )
    args = parser.parse_args()
    InteractionTests.artifacts = args.artifacts
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(InteractionTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if args.artifacts is not None:
        args.artifacts.mkdir(parents=True, exist_ok=True)
        manifest = {
            "source": "skills/web-animation-guide/references/interactions.md",
            "sha256": hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
            "browser": InteractionTests.browser.version,
            "tests": result.testsRun,
            "failures": len(result.failures),
            "errors": len(result.errors),
            "skipped": len(result.skipped),
            "successful": result.wasSuccessful() and result.testsRun > 0,
        }
        (args.artifacts / "result.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    return 0 if result.wasSuccessful() and result.testsRun > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
