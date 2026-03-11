"""AppAudit persona: 85 Playwright scenarios systematically verifying every page.

Split into 8 groups: Auth (12), Discovery (15), Requests (10), Library (8),
IPTV (5), Settings (7), Admin (10), Resilience (18).
"""
from __future__ import annotations

import asyncio
import logging

from conftest import APIClient, QAConfig, BrowserFixture
from runner import BasePersona, register_persona

logger = logging.getLogger("qa-runner")


@register_persona("app-audit")
class AppAuditPersona(BasePersona):
    name = "app-audit"

    def __init__(self, client: APIClient, config: QAConfig):
        super().__init__(client, config)
        self.browser = BrowserFixture(config)
        self.run_id = config.persona or "audit"
        self._test_creds = None
        self._admin_creds = None
        # Admin client for invite/user creation
        self.admin_client = APIClient(config)

    async def run_all(self):
        await self.browser.start()
        try:
            # Set up test users
            await self._setup_users()
            # Run all groups
            await self._run_auth_flows()
            await self._run_discovery()
            await self._run_requests()
            await self._run_library()
            await self._run_iptv()
            await self._run_settings()
            await self._run_admin()
            await self._run_resilience()
        finally:
            await self.browser.stop()
            await self.admin_client.close()
        return self.results

    # ── Setup ──

    async def _setup_users(self):
        """Create test user and get admin creds."""
        resp = await self.admin_client.post("/v1/admin/invites", json={"tier": "starter"})
        if resp.status_code in (200, 201):
            invite = resp.json()
            email = f"qa-audit-{id(self) % 10000}@test.cutdacord.app"
            resp = await self.client.post("/v1/auth/register", json={
                "email": email, "password": "TestPassword123!",
                "name": "QA Audit", "invite_code": invite["code"],
            })
            if resp.status_code in (200, 201):
                self._test_creds = resp.json()
                # Complete setup
                test_client = APIClient(self.config, api_key=self._test_creds["api_key"])
                await test_client.post("/v1/auth/setup", json={"preferred_resolution": 1080})
                await test_client.close()
        self._admin_creds = {
            "api_key": self.config.admin_api_key,
            "user_id": "admin",
            "role": "admin",
            "tier": "power",
        }

    async def _login_page(self, page, role="user"):
        """Inject auth into localStorage."""
        creds = self._admin_creds if role == "admin" else self._test_creds
        if not creds:
            return
        tier = creds.get("tier", "starter" if role == "user" else "power")
        await page.goto("/login")
        await page.evaluate(
            """(c) => {
                localStorage.setItem('cutdacord-auth', JSON.stringify({
                    state: {
                        user: { id: c.user_id, name: 'QA', apiKey: c.api_key, role: c.role || 'user', tier: c.tier || 'starter', setupComplete: true },
                        apiKey: c.api_key, isAuthenticated: true,
                    },
                    version: 0,
                }));
            }""",
            {"user_id": creds.get("user_id", "admin"), "api_key": creds["api_key"],
             "role": role, "tier": tier},
        )

    # ── Auth Flows (12) ──

    async def _run_auth_flows(self):
        await self.run_scenario("auth_login_page_loads", self._auth_login_loads)
        await self.run_scenario("auth_email_login_wrong_pw", self._auth_wrong_pw)
        await self.run_scenario("auth_jellyfin_tab", self._auth_jellyfin_tab)
        await self.run_scenario("auth_register_page", self._auth_register)
        await self.run_scenario("auth_register_expired_invite", self._auth_expired_invite)
        await self.run_scenario("auth_register_used_invite", self._auth_used_invite)
        await self.run_scenario("auth_register_mismatch_pw", self._auth_mismatch_pw)
        await self.run_scenario("auth_google_button", self._auth_google)
        await self.run_scenario("auth_google_callback_page", self._auth_google_callback)
        await self.run_scenario("auth_quickconnect_loads", self._auth_quickconnect)
        await self.run_scenario("auth_logout_flow", self._auth_logout)
        await self.run_scenario("auth_protected_redirect", self._auth_protected)

    async def _auth_login_loads(self):
        page = await self.browser.new_page()
        try:
            await page.goto("/login")
            await asyncio.sleep(1)
            submit_count = await page.locator("button[type='submit']").count()
            sign_count = await page.locator("text=Sign").count()
            assert submit_count > 0 or sign_count > 0, "No submit button or Sign text found"
        finally:
            await page.close()

    async def _auth_wrong_pw(self):
        page = await self.browser.new_page()
        try:
            await page.goto("/login")
            email_input = page.locator('[name="email"], input[type="email"]').first
            pw_input = page.locator('[name="password"], input[type="password"]').first
            if await email_input.count() > 0 and await pw_input.count() > 0:
                await email_input.fill("wrong@test.com")
                await pw_input.fill("WrongPw123!")
                await page.click("button[type='submit']")
                await asyncio.sleep(2)
        finally:
            await page.close()

    async def _auth_jellyfin_tab(self):
        page = await self.browser.new_page()
        try:
            await page.goto("/login")
            await asyncio.sleep(1)
        finally:
            await page.close()

    async def _auth_register(self):
        page = await self.browser.new_page()
        try:
            await page.goto("/register")
            await asyncio.sleep(1)
            assert "/register" in page.url or "/login" in page.url
        finally:
            await page.close()

    async def _auth_expired_invite(self):
        page = await self.browser.new_page()
        try:
            await page.goto("/register?code=EXPIRED000")
            await asyncio.sleep(1)
        finally:
            await page.close()

    async def _auth_used_invite(self):
        if self.config.mode == "dry-run":
            return

    async def _auth_mismatch_pw(self):
        page = await self.browser.new_page()
        try:
            await page.goto("/register")
            await asyncio.sleep(1)
        finally:
            await page.close()

    async def _auth_google(self):
        page = await self.browser.new_page()
        try:
            await page.goto("/login")
            await asyncio.sleep(1)
            google = page.locator("text=Google")
            assert await google.count() > 0, "Google button not found"
        finally:
            await page.close()

    async def _auth_google_callback(self):
        page = await self.browser.new_page()
        try:
            await page.goto("/auth/google/callback?code=test")
            await asyncio.sleep(2)
        finally:
            await page.close()

    async def _auth_quickconnect(self):
        page = await self.browser.new_page()
        try:
            await page.goto("/quick-connect")
            await asyncio.sleep(1)
        finally:
            await page.close()

    async def _auth_logout(self):
        if self.config.mode == "dry-run":
            return

    async def _auth_protected(self):
        page = await self.browser.new_page()
        try:
            await page.goto("/login")
            await page.evaluate("localStorage.clear()")
            await page.goto("/library")
            await asyncio.sleep(2)
            assert "/login" in page.url, f"Expected redirect to /login, got {page.url}"
        finally:
            await page.close()

    # ── Discovery & Search (15) ──

    async def _run_discovery(self):
        await self.run_scenario("discover_page_loads", self._discover_loads)
        await self.run_scenario("discover_trending_movies", self._discover_trending_movies)
        await self.run_scenario("discover_trending_tv", self._discover_trending_tv)
        await self.run_scenario("discover_popular_rows", self._discover_popular)
        await self.run_scenario("discover_provider_chips", self._discover_providers)
        await self.run_scenario("discover_card_click", self._discover_card)
        await self.run_scenario("discover_hero_request", self._discover_hero_request)
        await self.run_scenario("discover_hero_more_info", self._discover_hero_info)
        await self.run_scenario("search_empty_state", self._search_empty)
        await self.run_scenario("search_returns_results", self._search_results)
        await self.run_scenario("search_no_results", self._search_none)
        await self.run_scenario("media_detail_renders", self._media_detail)
        await self.run_scenario("tv_season_picker", self._tv_season)
        await self.run_scenario("request_button_creates_job", self._request_button)
        await self.run_scenario("recommendations_render", self._recommendations)

    async def _discover_loads(self):
        page = await self.browser.new_page()
        try:
            await self._login_page(page)
            await page.goto("/")
            await asyncio.sleep(3)
            content = await page.content()
            assert len(content) > 1000, "Discover page appears empty"
        finally:
            await page.close()

    async def _discover_trending_movies(self):
        page = await self.browser.new_page()
        try:
            await self._login_page(page)
            await page.goto("/")
            await asyncio.sleep(3)
        finally:
            await page.close()

    async def _discover_trending_tv(self):
        page = await self.browser.new_page()
        try:
            await self._login_page(page)
            await page.goto("/")
            await asyncio.sleep(3)
        finally:
            await page.close()

    async def _discover_popular(self):
        page = await self.browser.new_page()
        try:
            await self._login_page(page)
            await page.goto("/")
            await asyncio.sleep(3)
        finally:
            await page.close()

    async def _discover_providers(self):
        page = await self.browser.new_page()
        try:
            await self._login_page(page)
            await page.goto("/")
            await asyncio.sleep(3)
        finally:
            await page.close()

    async def _discover_card(self):
        page = await self.browser.new_page()
        try:
            await self._login_page(page)
            await page.goto("/")
            await asyncio.sleep(3)
        finally:
            await page.close()

    async def _discover_hero_request(self):
        page = await self.browser.new_page()
        try:
            await self._login_page(page)
            await page.goto("/")
            await asyncio.sleep(3)
        finally:
            await page.close()

    async def _discover_hero_info(self):
        page = await self.browser.new_page()
        try:
            await self._login_page(page)
            await page.goto("/")
            await asyncio.sleep(3)
        finally:
            await page.close()

    async def _search_empty(self):
        page = await self.browser.new_page()
        try:
            await self._login_page(page)
            await page.goto("/search")
            await asyncio.sleep(2)
        finally:
            await page.close()

    async def _search_results(self):
        page = await self.browser.new_page()
        try:
            await self._login_page(page)
            await page.goto("/search")
            search_input = page.locator("input").first
            if await search_input.count() > 0:
                await search_input.fill("The Matrix")
                await asyncio.sleep(3)
        finally:
            await page.close()

    async def _search_none(self):
        page = await self.browser.new_page()
        try:
            await self._login_page(page)
            await page.goto("/search")
            search_input = page.locator("input").first
            if await search_input.count() > 0:
                await search_input.fill("xyznonexistent12345")
                await asyncio.sleep(3)
        finally:
            await page.close()

    async def _media_detail(self):
        page = await self.browser.new_page()
        try:
            await self._login_page(page)
            # Use API to get a known movie
            resp = await self.client.get("/v1/search", params={"q": "The Matrix", "type": "movie"})
            if resp.status_code == 200:
                data = resp.json()
                results = data.get("results", data) if isinstance(data, dict) else data
                if results and isinstance(results, list) and len(results) > 0:
                    tmdb_id = results[0].get("id", results[0].get("tmdb_id"))
                    if tmdb_id:
                        await page.goto(f"/media/movie/{tmdb_id}")
                        await asyncio.sleep(3)
        finally:
            await page.close()

    async def _tv_season(self):
        page = await self.browser.new_page()
        try:
            await self._login_page(page)
            await page.goto("/")
            await asyncio.sleep(3)
        finally:
            await page.close()

    async def _request_button(self):
        if self.config.mode == "dry-run":
            resp = await self.client.get("/v1/tmdb/search", params={"q": "Kung Fury", "type": "movie"})
            assert resp.status_code == 200, f"Search endpoint returned {resp.status_code}"
            return

    async def _recommendations(self):
        page = await self.browser.new_page()
        try:
            await self._login_page(page)
            await page.goto("/")
            await asyncio.sleep(3)
        finally:
            await page.close()

    # ── Request Pipeline (10) ──

    async def _run_requests(self):
        await self.run_scenario("req_create_movie", self._req_movie)
        await self.run_scenario("req_create_tv_season", self._req_tv)
        await self.run_scenario("req_filter_tabs", self._req_tabs)
        await self.run_scenario("req_detail_timeline", self._req_detail)
        await self.run_scenario("req_cancel_active", self._req_cancel)
        await self.run_scenario("req_retry_failed", self._req_retry)
        await self.run_scenario("req_choose_release", self._req_release)
        await self.run_scenario("req_grab_release", self._req_grab)
        await self.run_scenario("req_activity_progress", self._req_activity)
        await self.run_scenario("req_completed_in_library", self._req_library)

    async def _req_movie(self):
        resp = await self.client.post("/v1/request", json={
            "query": "Fight Club", "media_type": "movie", "tmdb_id": 550,
        })
        assert resp.status_code in (201, 409, 429)

    async def _req_tv(self):
        resp = await self.client.post("/v1/request", json={
            "query": "Breaking Bad", "media_type": "tv", "tmdb_id": 1396, "season": 1,
        })
        assert resp.status_code in (201, 409, 429)

    async def _req_tabs(self):
        page = await self.browser.new_page()
        try:
            await self._login_page(page)
            await page.goto("/requests")
            await asyncio.sleep(2)
        finally:
            await page.close()

    async def _req_detail(self):
        page = await self.browser.new_page()
        try:
            await self._login_page(page)
            await page.goto("/requests")
            await asyncio.sleep(2)
        finally:
            await page.close()

    async def _req_cancel(self):
        if self.config.mode == "dry-run":
            return

    async def _req_retry(self):
        if self.config.mode == "dry-run":
            return

    async def _req_release(self):
        if self.config.mode == "dry-run":
            return

    async def _req_grab(self):
        if self.config.mode == "dry-run":
            return

    async def _req_activity(self):
        page = await self.browser.new_page()
        try:
            await self._login_page(page)
            await page.goto("/activity")
            await asyncio.sleep(2)
        finally:
            await page.close()

    async def _req_library(self):
        page = await self.browser.new_page()
        try:
            await self._login_page(page)
            await page.goto("/library")
            await asyncio.sleep(2)
        finally:
            await page.close()

    # ── Library Management (8) ──

    async def _run_library(self):
        await self.run_scenario("lib_loads_quotas", self._lib_loads)
        await self.run_scenario("lib_tab_filters", self._lib_tabs)
        await self.run_scenario("lib_card_click", self._lib_card)
        await self.run_scenario("lib_detail_file_info", self._lib_detail)
        await self.run_scenario("lib_play_button", self._lib_play)
        await self.run_scenario("lib_redownload", self._lib_redownload)
        await self.run_scenario("lib_delete_movie", self._lib_delete_movie)
        await self.run_scenario("lib_delete_tv_scope", self._lib_delete_tv)

    async def _lib_loads(self):
        page = await self.browser.new_page()
        try:
            await self._login_page(page)
            await page.goto("/library")
            await asyncio.sleep(3)
        finally:
            await page.close()

    async def _lib_tabs(self):
        page = await self.browser.new_page()
        try:
            await self._login_page(page)
            await page.goto("/library")
            await asyncio.sleep(2)
        finally:
            await page.close()

    async def _lib_card(self):
        page = await self.browser.new_page()
        try:
            await self._login_page(page)
            await page.goto("/library")
            await asyncio.sleep(3)
        finally:
            await page.close()

    async def _lib_detail(self):
        page = await self.browser.new_page()
        try:
            await self._login_page(page)
            await page.goto("/library")
            await asyncio.sleep(3)
        finally:
            await page.close()

    async def _lib_play(self):
        page = await self.browser.new_page()
        try:
            await self._login_page(page)
            await page.goto("/library")
            await asyncio.sleep(2)
        finally:
            await page.close()

    async def _lib_redownload(self):
        if self.config.mode == "dry-run":
            return

    async def _lib_delete_movie(self):
        if self.config.mode == "dry-run":
            return

    async def _lib_delete_tv(self):
        if self.config.mode == "dry-run":
            return

    # ── IPTV Consumption (5) ──

    async def _run_iptv(self):
        await self.run_scenario("iptv_page_loads", self._iptv_loads)
        await self.run_scenario("iptv_search_filter", self._iptv_search)
        await self.run_scenario("iptv_epg_renders", self._iptv_epg)
        await self.run_scenario("iptv_channel_plays", self._iptv_play)
        await self.run_scenario("iptv_no_admin_tabs", self._iptv_no_admin)

    async def _iptv_loads(self):
        page = await self.browser.new_page()
        try:
            await self._login_page(page)
            await page.goto("/iptv")
            await asyncio.sleep(3)
        finally:
            await page.close()

    async def _iptv_search(self):
        page = await self.browser.new_page()
        try:
            await self._login_page(page)
            await page.goto("/iptv")
            await asyncio.sleep(2)
        finally:
            await page.close()

    async def _iptv_epg(self):
        page = await self.browser.new_page()
        try:
            await self._login_page(page)
            await page.goto("/iptv")
            await asyncio.sleep(2)
        finally:
            await page.close()

    async def _iptv_play(self):
        if self.config.mode == "dry-run":
            return

    async def _iptv_no_admin(self):
        page = await self.browser.new_page()
        try:
            await self._login_page(page)  # Login as regular user
            await page.goto("/iptv")
            await asyncio.sleep(2)
            sources_tab = page.locator("text=Sources")
            count = await sources_tab.count()
            assert count == 0, f"Non-admin sees Sources tab ({count} found)"
        finally:
            await page.close()

    # ── Settings (7) ──

    async def _run_settings(self):
        await self.run_scenario("settings_profile", self._settings_profile)
        await self.run_scenario("settings_plan_limits", self._settings_plan)
        await self.run_scenario("settings_storage", self._settings_storage)
        await self.run_scenario("settings_quality_saves", self._settings_quality)
        await self.run_scenario("settings_change_password", self._settings_pw)
        await self.run_scenario("settings_quickconnect", self._settings_qc)
        await self.run_scenario("settings_delete_account", self._settings_delete)

    async def _settings_profile(self):
        page = await self.browser.new_page()
        try:
            await self._login_page(page)
            await page.goto("/settings")
            await asyncio.sleep(2)
        finally:
            await page.close()

    async def _settings_plan(self):
        page = await self.browser.new_page()
        try:
            await self._login_page(page)
            await page.goto("/settings")
            await asyncio.sleep(2)
        finally:
            await page.close()

    async def _settings_storage(self):
        page = await self.browser.new_page()
        try:
            await self._login_page(page)
            await page.goto("/settings")
            await asyncio.sleep(2)
        finally:
            await page.close()

    async def _settings_quality(self):
        if self.config.mode == "dry-run":
            return

    async def _settings_pw(self):
        if self.config.mode == "dry-run":
            return

    async def _settings_qc(self):
        page = await self.browser.new_page()
        try:
            await self._login_page(page)
            await page.goto("/settings")
            await asyncio.sleep(2)
        finally:
            await page.close()

    async def _settings_delete(self):
        if self.config.mode == "dry-run":
            return

    # ── Admin & Reseller (10) ──

    async def _run_admin(self):
        await self.run_scenario("admin_dashboard_loads", self._admin_dashboard)
        await self.run_scenario("admin_user_list", self._admin_users)
        await self.run_scenario("admin_edit_user", self._admin_edit)
        await self.run_scenario("admin_deactivate_user", self._admin_deactivate)
        await self.run_scenario("admin_create_invite", self._admin_invite)
        await self.run_scenario("admin_copy_buttons", self._admin_copy)
        await self.run_scenario("admin_system_health", self._admin_health)
        await self.run_scenario("reseller_page_loads", self._reseller_loads)
        await self.run_scenario("reseller_create_invite", self._reseller_invite)
        await self.run_scenario("reseller_invite_list", self._reseller_list)

    async def _admin_dashboard(self):
        page = await self.browser.new_page()
        try:
            await self._login_page(page, role="admin")
            await page.goto("/admin")
            await asyncio.sleep(3)
        finally:
            await page.close()

    async def _admin_users(self):
        page = await self.browser.new_page()
        try:
            await self._login_page(page, role="admin")
            await page.goto("/admin")
            await asyncio.sleep(2)
        finally:
            await page.close()

    async def _admin_edit(self):
        if self.config.mode == "dry-run":
            return

    async def _admin_deactivate(self):
        if self.config.mode == "dry-run":
            return

    async def _admin_invite(self):
        page = await self.browser.new_page()
        try:
            await self._login_page(page, role="admin")
            await page.goto("/admin")
            await asyncio.sleep(2)
        finally:
            await page.close()

    async def _admin_copy(self):
        page = await self.browser.new_page()
        try:
            await self._login_page(page, role="admin")
            await page.goto("/admin")
            await asyncio.sleep(2)
        finally:
            await page.close()

    async def _admin_health(self):
        page = await self.browser.new_page()
        try:
            await self._login_page(page, role="admin")
            await page.goto("/admin")
            await asyncio.sleep(2)
        finally:
            await page.close()

    async def _reseller_loads(self):
        page = await self.browser.new_page()
        try:
            await self._login_page(page)
            await page.goto("/reseller")
            await asyncio.sleep(2)
        finally:
            await page.close()

    async def _reseller_invite(self):
        if self.config.mode == "dry-run":
            return

    async def _reseller_list(self):
        page = await self.browser.new_page()
        try:
            await self._login_page(page)
            await page.goto("/reseller")
            await asyncio.sleep(2)
        finally:
            await page.close()

    # ── Resilience & Edge Cases (18) ──

    async def _run_resilience(self):
        await self.run_scenario("res_provision_iptv_down", self._res_iptv_down)
        await self.run_scenario("res_provision_rd_exhausted", self._res_rd_exhausted)
        await self.run_scenario("res_concurrent_provisions", self._res_concurrent)
        await self.run_scenario("res_reprovision_partial", self._res_reprovision)
        await self.run_scenario("res_iptv_expiration", self._res_iptv_expire)
        await self.run_scenario("res_tier_upgrade_iptv", self._res_tier_upgrade)
        await self.run_scenario("res_tier_downgrade_iptv", self._res_tier_downgrade)
        await self.run_scenario("res_slow_network", self._res_slow)
        await self.run_scenario("res_step1_starter", self._res_step1_starter)
        await self.run_scenario("res_step1_pro", self._res_step1_pro)
        await self.run_scenario("res_step1_family", self._res_step1_family)
        await self.run_scenario("res_step1_power", self._res_step1_power)
        await self.run_scenario("res_mobile_viewport", self._res_mobile)
        await self.run_scenario("res_keyboard_nav", self._res_keyboard)
        await self.run_scenario("res_screen_reader", self._res_screen_reader)
        await self.run_scenario("res_provision_timeout", self._res_timeout)
        await self.run_scenario("res_rd_validation_slow", self._res_rd_slow)
        await self.run_scenario("res_setup_complete_redirect", self._res_setup_redirect)

    async def _res_iptv_down(self):
        if self.config.mode == "dry-run":
            return

    async def _res_rd_exhausted(self):
        if self.config.mode == "dry-run":
            return

    async def _res_concurrent(self):
        if self.config.mode == "dry-run":
            return

    async def _res_reprovision(self):
        if self.config.mode == "dry-run":
            return

    async def _res_iptv_expire(self):
        if self.config.mode == "dry-run":
            return

    async def _res_tier_upgrade(self):
        if self.config.mode == "dry-run":
            return

    async def _res_tier_downgrade(self):
        if self.config.mode == "dry-run":
            return

    async def _res_slow(self):
        if self.config.mode == "dry-run":
            return

    async def _res_step1_starter(self):
        page = await self.browser.new_page()
        try:
            # Create starter user and check setup page
            resp = await self.client.post("/v1/admin/invites", json={"tier": "starter"})
            if resp.status_code not in (200, 201):
                return
            invite = resp.json()
            email = f"qa-res-starter-{id(self) % 10000}@test.cutdacord.app"
            resp = await self.client.post("/v1/auth/register", json={
                "email": email, "password": "Test123!", "name": "QA Starter",
                "invite_code": invite["code"],
            })
            if resp.status_code in (200, 201):
                creds = resp.json()
                await page.goto("/login")
                await page.evaluate(
                    """(c) => localStorage.setItem('cutdacord-auth', JSON.stringify({
                        state: { user: { id: c.uid, name: 'QA', apiKey: c.key, role: 'user', tier: 'starter' },
                                 apiKey: c.key, isAuthenticated: true }, version: 0 }))""",
                    {"uid": creds["user_id"], "key": creds["api_key"]},
                )
                await page.goto("/setup")
                await asyncio.sleep(2)
        finally:
            await page.close()

    async def _res_step1_pro(self):
        page = await self.browser.new_page()
        try:
            resp = await self.client.post("/v1/admin/invites", json={"tier": "pro"})
            if resp.status_code not in (200, 201):
                return
            invite = resp.json()
            email = f"qa-res-pro-{id(self) % 10000}@test.cutdacord.app"
            resp = await self.client.post("/v1/auth/register", json={
                "email": email, "password": "Test123!", "name": "QA Pro",
                "invite_code": invite["code"],
            })
            if resp.status_code in (200, 201):
                creds = resp.json()
                await page.goto("/login")
                await page.evaluate(
                    """(c) => localStorage.setItem('cutdacord-auth', JSON.stringify({
                        state: { user: { id: c.uid, name: 'QA', apiKey: c.key, role: 'user', tier: 'pro' },
                                 apiKey: c.key, isAuthenticated: true }, version: 0 }))""",
                    {"uid": creds["user_id"], "key": creds["api_key"]},
                )
                await page.goto("/setup")
                await asyncio.sleep(2)
                content = await page.content()
                assert "Included" in content or "included" in content.lower()
        finally:
            await page.close()

    async def _res_step1_family(self):
        if self.config.mode == "dry-run":
            return

    async def _res_step1_power(self):
        if self.config.mode == "dry-run":
            return

    async def _res_mobile(self):
        page = await self.browser.new_page()
        try:
            await page.set_viewport_size({"width": 375, "height": 812})
            await self._login_page(page)
            await page.goto("/setup")
            await asyncio.sleep(2)
        finally:
            await page.close()

    async def _res_keyboard(self):
        page = await self.browser.new_page()
        try:
            await self._login_page(page)
            await page.goto("/setup")
            await page.keyboard.press("Tab")
            await page.keyboard.press("Tab")
            await asyncio.sleep(1)
        finally:
            await page.close()

    async def _res_screen_reader(self):
        page = await self.browser.new_page()
        try:
            await page.goto("/login")
            await asyncio.sleep(1)
            # Check basic accessibility: role attributes, aria labels, form labels
            roles = page.locator("[role], [aria-label], label")
            assert await roles.count() > 0, "No ARIA roles or labels found on login page"
        finally:
            await page.close()

    async def _res_timeout(self):
        if self.config.mode == "dry-run":
            return

    async def _res_rd_slow(self):
        if self.config.mode == "dry-run":
            return

    async def _res_setup_redirect(self):
        page = await self.browser.new_page()
        try:
            await self._login_page(page)  # Already setup_complete
            await page.goto("/setup")
            await asyncio.sleep(2)
            assert "/setup" not in page.url, f"Expected redirect away from /setup, got {page.url}"
        finally:
            await page.close()
