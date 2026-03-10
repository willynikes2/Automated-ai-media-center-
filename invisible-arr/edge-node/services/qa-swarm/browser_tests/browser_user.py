"""Browser User persona: Playwright tests for frontend pages."""
from __future__ import annotations

import asyncio

from playwright.async_api import async_playwright, Page, ConsoleMessage

from conftest import QAConfig
from runner import BasePersona, register_persona


@register_persona("browser_user")
class BrowserUserPersona(BasePersona):
    name = "browser_user"

    def __init__(self, client, config: QAConfig):
        super().__init__(client, config)
        self._console_errors: list[str] = []

    async def run_all(self):
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            try:
                context = await browser.new_context(
                    viewport={"width": 1280, "height": 720},
                )
                page = await context.new_page()
                page.on("console", self._on_console)

                await self.run_scenario("load_library", lambda: self._load_page(page, "/library"))
                await self.run_scenario("load_activity", lambda: self._load_page(page, "/activity"))
                await self.run_scenario("load_search", lambda: self._load_page(page, "/search"))
                await self.run_scenario("check_console_errors", lambda: self._check_errors())

                # Mobile viewport test
                await context.close()
                mobile_ctx = await browser.new_context(
                    viewport={"width": 375, "height": 812},
                )
                mobile_page = await mobile_ctx.new_page()
                await self.run_scenario("mobile_library", lambda: self._load_page(mobile_page, "/library"))
                await mobile_ctx.close()
            finally:
                await browser.close()

        return self.results

    def _on_console(self, msg: ConsoleMessage):
        if msg.type == "error":
            self._console_errors.append(msg.text)

    async def _load_page(self, page: Page, path: str):
        """Navigate to a page, verify it loads within 10s without crashing."""
        url = f"{self.config.frontend_url}{path}"
        resp = await page.goto(url, wait_until="networkidle", timeout=10000)
        assert resp is not None, f"No response from {url}"
        assert resp.status < 500, f"Page {path} returned {resp.status}"

        # Take screenshot on any non-200 for debugging
        screenshots = []
        if resp.status != 200:
            path_safe = path.replace("/", "_")
            screenshot_path = f"/tmp/qa-screenshot-{path_safe}.png"
            await page.screenshot(path=screenshot_path)
            screenshots.append(screenshot_path)

        return screenshots

    async def _check_errors(self):
        """Verify no JS console errors were captured across all page loads."""
        # Filter out known noise (e.g., favicon 404)
        real_errors = [e for e in self._console_errors if "favicon" not in e.lower()]
        if real_errors:
            raise AssertionError(
                f"{len(real_errors)} JS console errors:\n" +
                "\n".join(f"  - {e[:200]}" for e in real_errors[:10])
            )
        return []
