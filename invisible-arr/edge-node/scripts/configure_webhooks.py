#!/usr/bin/env python3
"""Configure Radarr and Sonarr to send webhooks to agent-api.

Run from inside a container with network access to radarr/sonarr:
  docker exec agent-api python /app/scripts/configure_webhooks.py

Or from the host if ports are exposed.
"""

import json
import os
import sys
import urllib.request
import urllib.error

RADARR_URL = os.environ.get("RADARR_URL", "http://radarr:7878")
RADARR_API = os.environ.get("RADARR_API_KEY", "48cf4fe0d7c049e9942649e4e65a45e2")
SONARR_URL = os.environ.get("SONARR_URL", "http://sonarr:8989")
SONARR_API = os.environ.get("SONARR_API_KEY", "6084b33179eb49c884cc1847ef4089d5")
WEBHOOK_BASE = os.environ.get("WEBHOOK_BASE", "http://agent-api:8880/v1")
WEBHOOK_NAME = "InvisibleArr"


def api_request(url: str, api_key: str, method: str = "GET", data: dict | None = None):
    """Simple HTTP helper using stdlib only."""
    headers = {"X-Api-Key": api_key, "Content-Type": "application/json"}
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        print(f"  HTTP {e.code}: {e.read().decode()[:200]}")
        raise


def configure_radarr():
    print(f"Configuring Radarr webhook -> {WEBHOOK_BASE}/webhooks/radarr")

    notifications = api_request(
        f"{RADARR_URL}/api/v3/notification", RADARR_API
    )
    existing = [n for n in notifications if n.get("name") == WEBHOOK_NAME]

    webhook_config = {
        "name": WEBHOOK_NAME,
        "implementation": "Webhook",
        "configContract": "WebhookSettings",
        "fields": [
            {"name": "url", "value": f"{WEBHOOK_BASE}/webhooks/radarr"},
            {"name": "method", "value": 1},  # POST
        ],
        "onGrab": True,
        "onDownload": True,
        "onUpgrade": True,
        "onMovieFileDelete": True,
        "onMovieDelete": False,
        "onHealthIssue": True,
        "onHealthRestored": True,
        "onApplicationUpdate": False,
        "supportsOnGrab": True,
        "supportsOnDownload": True,
        "supportsOnUpgrade": True,
        "supportsOnMovieFileDelete": True,
        "supportsOnHealthIssue": True,
        "supportsOnHealthRestored": True,
        "tags": [],
    }

    if existing:
        wh_id = existing[0]["id"]
        webhook_config["id"] = wh_id
        api_request(
            f"{RADARR_URL}/api/v3/notification/{wh_id}",
            RADARR_API, "PUT", webhook_config,
        )
        print(f"  Updated Radarr webhook (id={wh_id})")
    else:
        result = api_request(
            f"{RADARR_URL}/api/v3/notification",
            RADARR_API, "POST", webhook_config,
        )
        print(f"  Created Radarr webhook (id={result.get('id')})")


def configure_sonarr():
    print(f"Configuring Sonarr webhook -> {WEBHOOK_BASE}/webhooks/sonarr")

    notifications = api_request(
        f"{SONARR_URL}/api/v3/notification", SONARR_API
    )
    existing = [n for n in notifications if n.get("name") == WEBHOOK_NAME]

    webhook_config = {
        "name": WEBHOOK_NAME,
        "implementation": "Webhook",
        "configContract": "WebhookSettings",
        "fields": [
            {"name": "url", "value": f"{WEBHOOK_BASE}/webhooks/sonarr"},
            {"name": "method", "value": 1},  # POST
        ],
        "onGrab": True,
        "onDownload": True,
        "onUpgrade": True,
        "onEpisodeFileDelete": True,
        "onSeriesDelete": False,
        "onHealthIssue": True,
        "onHealthRestored": True,
        "onApplicationUpdate": False,
        "supportsOnGrab": True,
        "supportsOnDownload": True,
        "supportsOnUpgrade": True,
        "supportsOnEpisodeFileDelete": True,
        "supportsOnHealthIssue": True,
        "supportsOnHealthRestored": True,
        "tags": [],
    }

    if existing:
        wh_id = existing[0]["id"]
        webhook_config["id"] = wh_id
        api_request(
            f"{SONARR_URL}/api/v3/notification/{wh_id}",
            SONARR_API, "PUT", webhook_config,
        )
        print(f"  Updated Sonarr webhook (id={wh_id})")
    else:
        result = api_request(
            f"{SONARR_URL}/api/v3/notification",
            SONARR_API, "POST", webhook_config,
        )
        print(f"  Created Sonarr webhook (id={result.get('id')})")


def main():
    print("=== Configuring Arr Webhooks ===\n")
    try:
        configure_radarr()
        print()
        configure_sonarr()
        print("\nDone! Webhooks configured.")
    except Exception as e:
        print(f"\nFailed: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
