"""Create trial users for the Invisible Arr multi-tenant platform.

Run inside the agent-api container:
    docker compose exec agent-api python scripts/create_trial_users.py

Creates:
- Ensures willynikes is admin/power
- Creates a trial invite code
- Creates 9 trial users (trial_user_1 .. trial_user_9)
- Creates default Prefs for each
- Optionally creates Jellyfin accounts
"""

from __future__ import annotations

import asyncio
import logging
import secrets
import sys
from pathlib import Path

# Ensure shared package is importable
_app_root = Path("/app")
if str(_app_root) not in sys.path:
    sys.path.insert(0, str(_app_root))

import bcrypt  # noqa: E402
import httpx  # noqa: E402
from sqlalchemy import select  # noqa: E402

from shared.config import get_config  # noqa: E402
from shared.database import init_db, get_session_factory  # noqa: E402
from shared.models import Invite, Prefs, User  # noqa: E402
from shared.tiers import get_tier_limits  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("create_trial_users")

NUM_TRIAL_USERS = 9
TRIAL_PASSWORD_PREFIX = "AutoMedia2026!"
TRIAL_TIER = "starter"


async def ensure_admin(session) -> None:
    """Ensure willynikes and default users are admin/power."""
    for name in ("willynikes", "default"):
        result = await session.execute(select(User).where(User.name == name))
        user = result.scalar_one_or_none()
        if user:
            user.role = "admin"
            user.tier = "power"
            user.is_active = True
            limits = get_tier_limits("power")
            user.storage_quota_gb = limits["storage_quota_gb"]
            user.max_concurrent_jobs = limits["max_concurrent_jobs"]
            user.max_requests_per_day = limits["max_requests_per_day"]
            logger.info("Updated %s -> admin/power", name)
    await session.commit()


async def create_invite(session, admin_user: User) -> Invite:
    """Create a trial invite code."""
    code = f"AUTOMEDIA-TRIAL-{secrets.token_hex(4).upper()}"
    invite = Invite(
        code=code,
        created_by=admin_user.id,
        tier=TRIAL_TIER,
        max_uses=NUM_TRIAL_USERS,
        times_used=0,
    )
    session.add(invite)
    await session.flush()
    logger.info("Created invite code: %s (tier=%s, max_uses=%d)", code, TRIAL_TIER, NUM_TRIAL_USERS)
    return invite


async def create_jellyfin_user(username: str, password: str, config) -> str | None:
    """Create a Jellyfin user account. Returns jellyfin_user_id or None."""
    if not config.jellyfin_admin_token:
        return None

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"{config.jellyfin_url}/Users/New",
                headers={"X-Emby-Token": config.jellyfin_admin_token},
                json={"Name": username, "Password": password},
            )
            if resp.status_code in (200, 201):
                data = resp.json()
                jf_id = data.get("Id")
                logger.info("Created Jellyfin user: %s (id=%s)", username, jf_id)
                return jf_id
            else:
                logger.warning("Jellyfin user creation failed for %s: %s", username, resp.text[:200])
    except Exception as exc:
        logger.warning("Jellyfin API error for %s: %s", username, exc)
    return None


async def main() -> None:
    init_db()
    config = get_config()
    factory = get_session_factory()
    limits = get_tier_limits(TRIAL_TIER)

    credentials: list[dict] = []

    async with factory() as session:
        # 1. Ensure admin users
        await ensure_admin(session)

        # 2. Get admin user for invite creation
        result = await session.execute(
            select(User).where(User.name == "willynikes")
        )
        admin_user = result.scalar_one_or_none()
        if admin_user is None:
            result = await session.execute(
                select(User).where(User.role == "admin")
            )
            admin_user = result.scalar_one_or_none()
        if admin_user is None:
            logger.error("No admin user found. Run migrations first.")
            sys.exit(1)

        # 3. Create invite
        invite = await create_invite(session, admin_user)

        # 4. Create trial users
        for i in range(1, NUM_TRIAL_USERS + 1):
            username = f"trial_user_{i}"
            email = f"trial{i}@automedia.local"
            password = f"{TRIAL_PASSWORD_PREFIX}{i}"

            # Check if already exists
            existing = await session.execute(
                select(User).where(User.email == email)
            )
            if existing.scalar_one_or_none() is not None:
                logger.info("User %s already exists, skipping", username)
                continue

            password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

            user = User(
                name=username,
                email=email,
                password_hash=password_hash,
                role="user",
                tier=TRIAL_TIER,
                storage_quota_gb=limits["storage_quota_gb"],
                max_concurrent_jobs=limits["max_concurrent_jobs"],
                max_requests_per_day=limits["max_requests_per_day"],
                invited_by=admin_user.id,
            )
            session.add(user)
            await session.flush()

            # Create default prefs
            prefs = Prefs(
                user_id=user.id,
                max_resolution=limits["max_resolution"],
                allow_4k=limits["allow_4k"],
                max_movie_size_gb=limits["max_movie_size_gb"],
                max_episode_size_gb=limits["max_episode_size_gb"],
                prune_watched_after_days=14,
                storage_soft_limit_percent=80,
            )
            session.add(prefs)

            invite.times_used += 1

            # Create Jellyfin account
            jf_id = await create_jellyfin_user(username, password, config)
            if jf_id:
                user.jellyfin_user_id = jf_id

            credentials.append({
                "username": username,
                "email": email,
                "password": password,
                "api_key": user.api_key,
                "tier": TRIAL_TIER,
            })

            logger.info("Created trial user: %s", username)

        await session.commit()

    # Print credentials table
    print("\n" + "=" * 80)
    print("TRIAL USER CREDENTIALS")
    print("=" * 80)
    print(f"{'Username':<20} {'Email':<30} {'Password':<25} {'API Key'}")
    print("-" * 80)
    for cred in credentials:
        print(f"{cred['username']:<20} {cred['email']:<30} {cred['password']:<25} {cred['api_key']}")
    print("=" * 80)
    print(f"\nInvite code: {invite.code}")
    print(f"Total users created: {len(credentials)}")
    print()


if __name__ == "__main__":
    asyncio.run(main())
