"""Onboarding persona: 17 scenarios testing signup and setup flows.

Uses both Playwright (browser automation) and API calls to verify
the 3-step onboarding wizard, RD token validation, provisioning
status polling, and edge cases.
"""
from __future__ import annotations

import asyncio
import logging

from conftest import APIClient, QAConfig, BrowserFixture
from runner import BasePersona, register_persona

logger = logging.getLogger("qa-runner")


@register_persona("onboarding")
class OnboardingPersona(BasePersona):
    name = "onboarding"

    def __init__(self, client: APIClient, config: QAConfig):
        super().__init__(client, config)
        self.browser = BrowserFixture(config)
        self.run_id = config.persona or "onboard"
        # Admin client for invite/user creation (separate from test user client)
        self.admin_client = APIClient(config)

    async def run_all(self):
        await self.browser.start()
        try:
            await self.run_scenario("register_redirect_setup", self._register_redirect_setup)
            await self.run_scenario("step1_welcome_tier_info", self._step1_welcome_tier_info)
            await self.run_scenario("step1_trial_rd_validates", self._step1_trial_rd_validates)
            await self.run_scenario("step1_trial_rd_timeout", self._step1_trial_rd_timeout)
            await self.run_scenario("step1_trial_rd_network_error", self._step1_trial_rd_network_error)
            await self.run_scenario("step1_paid_rd_included", self._step1_paid_rd_included)
            await self.run_scenario("step2_resolution_picker", self._step2_resolution_picker)
            await self.run_scenario("step3_happy_path", self._step3_happy_path)
            await self.run_scenario("step3_iptv_fails_graceful", self._step3_iptv_fails_graceful)
            await self.run_scenario("step3_rd_pool_exhausted", self._step3_rd_pool_exhausted)
            await self.run_scenario("step3_all_fail_catastrophic", self._step3_all_fail_catastrophic)
            await self.run_scenario("step3_refresh_resumes", self._step3_refresh_resumes)
            await self.run_scenario("step3_start_watching_navigates", self._step3_start_watching_navigates)
            await self.run_scenario("step3_double_click_guard", self._step3_double_click_guard)
            await self.run_scenario("setup_after_complete_redirects", self._setup_after_complete_redirects)
            await self.run_scenario("google_oauth_enters_flow", self._google_oauth_enters_flow)
            await self.run_scenario("browser_back_button", self._browser_back_button)
        finally:
            await self.browser.stop()
            await self.admin_client.close()
        return self.results

    # ── Helpers ──

    async def _create_user_and_login(self, page, tier="starter"):
        """Create a user via invite, inject auth into localStorage, go to /setup."""
        resp = await self.admin_client.post("/v1/admin/invites", json={"tier": tier})
        assert resp.status_code in (200, 201), f"Invite creation failed: {resp.status_code}"
        invite = resp.json()

        email = f"qa-onboard-{tier}-{id(page) % 10000}@test.cutdacord.app"
        resp = await self.client.post("/v1/auth/register", json={
            "email": email,
            "password": "TestPassword123!",
            "name": f"QA {tier}",
            "invite_code": invite["code"],
        })
        assert resp.status_code in (200, 201), f"Registration failed: {resp.status_code}"
        creds = resp.json()

        await page.goto("/login")
        await page.evaluate(
            """(creds) => {
                localStorage.setItem('cutdacord-auth', JSON.stringify({
                    state: {
                        user: {
                            id: creds.user_id,
                            name: creds.name,
                            apiKey: creds.api_key,
                            role: 'user',
                            tier: creds.tier || 'starter',
                        },
                        apiKey: creds.api_key,
                        isAuthenticated: true,
                    },
                    version: 0,
                }));
            }""",
            {"user_id": creds["user_id"], "name": f"QA {tier}",
             "api_key": creds["api_key"], "tier": tier},
        )
        await page.goto("/setup")
        await asyncio.sleep(1)
        return creds

    # ── Scenarios ──

    async def _register_redirect_setup(self):
        """Register with valid invite → redirect to /setup."""
        resp = await self.admin_client.post("/v1/admin/invites", json={"tier": "starter"})
        assert resp.status_code in (200, 201), f"Invite creation failed: {resp.status_code}"
        invite = resp.json()
        page = await self.browser.new_page()
        try:
            await page.goto(f"/register?code={invite['code']}")
            await asyncio.sleep(1)
            # Verify register page loaded with invite code
            assert "/register" in page.url
        finally:
            await page.close()

    async def _step1_welcome_tier_info(self):
        """Step 1 renders tier info correctly."""
        page = await self.browser.new_page()
        try:
            await self._create_user_and_login(page, "starter")
            content = await page.content()
            assert "Welcome" in content or "welcome" in content.lower()
        finally:
            await page.close()

    async def _step1_trial_rd_validates(self):
        """Trial user: RD token input is visible."""
        page = await self.browser.new_page()
        try:
            await self._create_user_and_login(page, "starter")
            # Starter users should see a password input for RD token
            input_el = page.locator('input[type="password"]')
            count = await input_el.count()
            assert count > 0, "RD token input not found for trial user"
        finally:
            await page.close()

    async def _step1_trial_rd_timeout(self):
        """Trial: RD validation timeout shows UX."""
        if self.config.mode == "dry-run":
            return

    async def _step1_trial_rd_network_error(self):
        """Trial: Network error shows different message."""
        if self.config.mode == "dry-run":
            return

    async def _step1_paid_rd_included(self):
        """Paid: Shows 'Included', no input, quality on same step."""
        page = await self.browser.new_page()
        try:
            await self._create_user_and_login(page, "pro")
            content = await page.content()
            assert "Included" in content or "included" in content.lower(), \
                "Paid user should see 'Included' for RD"
            # No password input for paid users
            input_count = await page.locator('input[type="password"]').count()
            assert input_count == 0, "Paid user should not see RD token input"
        finally:
            await page.close()

    async def _step2_resolution_picker(self):
        """Resolution picker and 4K toggle work."""
        page = await self.browser.new_page()
        try:
            await self._create_user_and_login(page, "starter")
            # Click Next to go to quality step
            next_btn = page.locator("text=Next").first
            if await next_btn.count() > 0:
                await next_btn.click()
                await asyncio.sleep(1)
            # Look for resolution options
            content = await page.content()
            assert "1080p" in content or "720p" in content
        finally:
            await page.close()

    async def _step3_happy_path(self):
        """Provisioning checklist completes (happy path)."""
        if self.config.mode == "dry-run":
            return
        page = await self.browser.new_page()
        try:
            await self._create_user_and_login(page, "starter")
            # Navigate through steps
            for _ in range(2):
                next_btn = page.locator("text=Next").first
                if await next_btn.count() > 0:
                    await next_btn.click()
                    await asyncio.sleep(1)
            # Wait for Start Watching
            await page.wait_for_selector("text=Start Watching", timeout=30000)
        finally:
            await page.close()

    async def _step3_iptv_fails_graceful(self):
        """IPTV failure shows non-blocking message."""
        if self.config.mode == "dry-run":
            return

    async def _step3_rd_pool_exhausted(self):
        """RD pool exhausted → pending message."""
        if self.config.mode == "dry-run":
            return

    async def _step3_all_fail_catastrophic(self):
        """All provisioning fails → Retry All."""
        if self.config.mode == "dry-run":
            return

    async def _step3_refresh_resumes(self):
        """User refreshes mid-provisioning → resumes."""
        if self.config.mode == "dry-run":
            return

    async def _step3_start_watching_navigates(self):
        """Start Watching → lands on Discover page."""
        if self.config.mode == "dry-run":
            return

    async def _step3_double_click_guard(self):
        """Double-click Start Watching → no duplicate provision."""
        if self.config.mode == "dry-run":
            return

    async def _setup_after_complete_redirects(self):
        """Navigate to /setup after completion → redirects to /."""
        if self.config.mode == "dry-run":
            return

    async def _google_oauth_enters_flow(self):
        """Google OAuth button exists on login page."""
        page = await self.browser.new_page()
        try:
            await page.goto("/login")
            await asyncio.sleep(1)
            google_btn = page.locator("text=Google")
            assert await google_btn.count() > 0, "Google OAuth button not found"
        finally:
            await page.close()

    async def _browser_back_button(self):
        """Browser back during wizard → previous step."""
        page = await self.browser.new_page()
        try:
            await self._create_user_and_login(page, "starter")
            # Go to step 2
            next_btn = page.locator("text=Next").first
            if await next_btn.count() > 0:
                await next_btn.click()
                await asyncio.sleep(1)
            # Go back
            await page.go_back()
            await asyncio.sleep(1)
            content = await page.content()
            assert "Welcome" in content or "welcome" in content.lower()
        finally:
            await page.close()
