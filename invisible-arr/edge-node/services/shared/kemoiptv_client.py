"""Async KemoIPTV reseller API client.

Security note: KemoIPTV does NOT support HTTPS. All traffic (including
credentials) is transmitted in plaintext over HTTP. This is an accepted risk
given that KemoIPTV provides no TLS endpoint — ensure this client is only
called from within a trusted private network or VPN.
"""
from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Custom exception
# ---------------------------------------------------------------------------


class KemoIPTVError(Exception):
    """Raised for KemoIPTV API errors."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        self.status_code = status_code
        super().__init__(message)


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


class KemoIPTVClient:
    """Async wrapper around the KemoIPTV reseller API.

    Parameters
    ----------
    base_url:
        Base URL of the KemoIPTV panel (e.g. ``http://panel.example.com``).
        Must be HTTP — KemoIPTV does not support HTTPS.
    username:
        Reseller account username.
    password:
        Reseller account password.
    """

    def __init__(self, base_url: str, username: str, password: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._username = username
        self._password = password
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(30.0, connect=10.0),
        )

    # -- helpers -----------------------------------------------------------

    async def _request(self, action: str, sub: str, **params: Any) -> dict:
        """Execute a GET request against ``/api.php``.

        All requests pass ``action``, ``sub``, ``username``, and ``password``
        as query parameters. Additional keyword arguments are merged in.

        Raises
        ------
        KemoIPTVError
            On non-200 HTTP status or when the API returns ``result=False``.
        """
        query: dict[str, Any] = {
            "action": action,
            "sub": sub,
            "username": self._username,
            "password": self._password,
            **params,
        }

        url = f"{self._base_url}/api.php"
        logger.debug("KemoIPTV request: action=%s sub=%s params=%s", action, sub, params)

        response = await self._client.get(url, params=query)

        if response.status_code != 200:
            raise KemoIPTVError(
                f"KemoIPTV API HTTP error {response.status_code}: {response.text}",
                status_code=response.status_code,
            )

        # Some endpoints return an empty body on success
        if not response.content:
            return {}

        body: dict = response.json()

        if body.get("result") is False:
            msg = body.get("message", "unknown error")
            raise KemoIPTVError(f"KemoIPTV API error: {msg}")

        return body

    # -- public API --------------------------------------------------------

    async def create_line(
        self,
        line_username: str,
        line_password: str,
        max_connections: int = 1,
        exp_date: str | None = None,
        bouquet: str = "",
    ) -> dict:
        """Create a new subscriber line.

        Parameters
        ----------
        line_username:
            Username for the new line.
        line_password:
            Password for the new line.
        max_connections:
            Maximum simultaneous connections allowed (default: 1).
        exp_date:
            Expiry date string (e.g. ``"2026-12-31"``). If *None*, the panel
            default is used.
        bouquet:
            Comma-separated bouquet IDs to assign. Empty string assigns none.
        """
        user_data: dict[str, Any] = {
            "user_data[username]": line_username,
            "user_data[password]": line_password,
            "user_data[max_connections]": max_connections,
            "user_data[bouquet]": bouquet,
        }
        if exp_date is not None:
            user_data["user_data[exp_date]"] = exp_date

        result = await self._request("user", "create", **user_data)
        logger.info("KemoIPTV line created: username=%s", line_username)
        return result

    async def update_line(
        self,
        line_username: str,
        max_connections: int | None = None,
        exp_date: str | None = None,
    ) -> dict:
        """Edit an existing subscriber line.

        Only the provided keyword arguments are sent; omitted values remain
        unchanged on the panel.

        Parameters
        ----------
        line_username:
            Username of the line to modify.
        max_connections:
            New maximum simultaneous connections, or *None* to leave as-is.
        exp_date:
            New expiry date string, or *None* to leave as-is.
        """
        user_data: dict[str, Any] = {
            "user_data[username]": line_username,
        }
        if max_connections is not None:
            user_data["user_data[max_connections]"] = max_connections
        if exp_date is not None:
            user_data["user_data[exp_date]"] = exp_date

        result = await self._request("user", "edit", **user_data)
        logger.info(
            "KemoIPTV line updated: username=%s max_connections=%s exp_date=%s",
            line_username,
            max_connections,
            exp_date,
        )
        return result

    async def disable_line(self, line_username: str) -> dict:
        """Disable a subscriber line by setting max_connections to 0.

        Parameters
        ----------
        line_username:
            Username of the line to disable.
        """
        result = await self._request(
            "user",
            "edit",
            **{
                "user_data[username]": line_username,
                "user_data[max_connections]": 0,
            },
        )
        logger.info("KemoIPTV line disabled: username=%s", line_username)
        return result

    async def check_status(self, line_username: str) -> dict:
        """Retrieve info / status for a subscriber line.

        Parameters
        ----------
        line_username:
            Username of the line to query.
        """
        result = await self._request(
            "user",
            "info",
            **{"user_data[username]": line_username},
        )
        logger.debug("KemoIPTV status for %s: %s", line_username, result)
        return result

    # -- lifecycle ---------------------------------------------------------

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()

    async def __aenter__(self) -> "KemoIPTVClient":
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()
