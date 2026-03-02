# Claude Code Master Prompt — Invisible Arr + Agent Brain v1

> Paste this entire file as a single message into Claude Code. It will build the complete monorepo.

---

## ROLE

You are building v1 of the "Invisible Arr + Agent Brain" media automation platform. This is a Docker Compose-based edge node that wraps the *Arr ecosystem (Sonarr, Radarr, Prowlarr) with an intelligent agent layer. Users only interact with Seerr (requests) and Jellyfin (playback). Everything else is automated.

## WORKING DIRECTORY

Create everything under `./invisible-arr/`. This is a monorepo.

## IMPLEMENTATION ORDER

Build in this exact sequence. After each phase, confirm what was created.

---

## PHASE 1: REPO SCAFFOLD + DOCS

Create this directory structure:

```
invisible-arr/
├── README.md
├── LICENSE
├── .gitignore
├── edge-node/
│   ├── docker-compose.yml          (Phase 2)
│   ├── .env.template               (Phase 2)
│   ├── docs/
│   │   ├── ARCHITECTURE.md
│   │   ├── SETUP.md
│   │   └── FLARESOLVERR.md
│   ├── scripts/
│   │   ├── install.sh              (Phase 8)
│   │   └── smoke.sh                (Phase 8)
│   └── services/
│       ├── shared/
│       │   ├── __init__.py
│       │   ├── config.py
│       │   ├── database.py
│       │   ├── models.py
│       │   ├── schemas.py
│       │   ├── redis_client.py
│       │   ├── rd_client.py
│       │   ├── prowlarr_client.py
│       │   ├── tmdb_client.py
│       │   ├── scoring.py
│       │   └── naming.py
│       ├── agent-api/
│       │   ├── Dockerfile
│       │   ├── requirements.txt
│       │   ├── main.py
│       │   └── routers/
│       │       ├── __init__.py
│       │       ├── health.py
│       │       ├── requests.py
│       │       ├── jobs.py
│       │       ├── prefs.py
│       │       └── webhooks.py
│       ├── agent-worker/
│       │   ├── Dockerfile
│       │   ├── requirements.txt
│       │   ├── main.py
│       │   └── worker.py
│       ├── agent-qc/
│       │   ├── Dockerfile
│       │   ├── requirements.txt
│       │   ├── main.py
│       │   └── qc.py
│       ├── agent-storage/
│       │   ├── Dockerfile
│       │   ├── requirements.txt
│       │   ├── main.py
│       │   └── storage.py
│       ├── iptv-gateway/
│       │   ├── Dockerfile
│       │   ├── requirements.txt
│       │   ├── main.py
│       │   ├── m3u_parser.py
│       │   ├── xmltv_parser.py
│       │   ├── timezone_converter.py
│       │   └── routers/
│       │       ├── __init__.py
│       │       ├── sources.py
│       │       ├── channels.py
│       │       └── playlist.py
│       └── migrations/
│           ├── alembic.ini
│           ├── env.py
│           └── versions/
│               └── 001_initial_schema.py
├── control-plane/
│   └── README.md
└── seerr-fork/
    └── NOTES.md
```

### README.md content:
- Project name, one-line description
- Architecture diagram (ASCII)
- Quick start: `cd edge-node && bash scripts/install.sh`
- Link to docs/SETUP.md

### docs/ARCHITECTURE.md:
- Container map table (all 16 services: tier, image, exposed Y/N, port)
- Data flow: Seerr → agent-api → worker → Prowlarr/RD → import → QC → Jellyfin
- Network topology: Traefik ingress, internal Docker network, Gluetun VPN subnet

### docs/SETUP.md:
- Prerequisites: Docker Engine 24+, Docker Compose v2, domain (optional), TMDB key (free), RD token (optional), VPN creds (optional)
- Step-by-step first run
- Env var reference table

### docs/FLARESOLVERR.md:
- What FlareSolverr does
- How to configure per-indexer in Prowlarr UI
- Healthcheck and timeout settings

### .gitignore:
```
.env
__pycache__/
*.pyc
.venv/
node_modules/
*.egg-info/
data/
```

---

## PHASE 2: DOCKER COMPOSE + ENV

### .env.template

```env
# ══════════════════════════════════════════
# Invisible Arr — Edge Node Configuration
# ══════════════════════════════════════════

# ── Domain & TLS ──
DOMAIN=                          # e.g., media.example.com (leave empty for HTTP-only)
ACME_EMAIL=                      # Let's Encrypt email

# ── TMDB ──
TMDB_API_KEY=                    # Required: https://www.themoviedb.org/settings/api

# ── Real-Debrid ──
RD_API_TOKEN=                    # Optional: https://real-debrid.com/apitoken
RD_ENABLED=false

# ── VPN (Gluetun) ──
VPN_ENABLED=false
VPN_PROVIDER=                    # e.g., mullvad, nordvpn, protonvpn
VPN_TYPE=wireguard               # wireguard or openvpn
WIREGUARD_PRIVATE_KEY=
WIREGUARD_ADDRESSES=
SERVER_COUNTRIES=

# ── LLM (optional) ──
LLM_PROVIDER=none                # none | openai | anthropic
LLM_API_KEY=
LLM_MODEL=

# ── Storage Paths ──
DATA_PATH=./data
CONFIG_PATH=./config
MEDIA_PATH=./data/media
DOWNLOADS_PATH=./data/downloads

# ── Database ──
POSTGRES_USER=invisiblearr
POSTGRES_PASSWORD=CHANGEME_GENERATE_THIS
POSTGRES_DB=invisiblearr

# ── Quality Defaults ──
DEFAULT_MAX_RESOLUTION=1080
DEFAULT_ALLOW_4K=false
DEFAULT_MAX_MOVIE_SIZE_GB=15
DEFAULT_MAX_EPISODE_SIZE_GB=4

# ── IPTV ──
IPTV_ENABLED=false

# ── Service Ports (internal, rarely changed) ──
AGENT_API_PORT=8880
IPTV_GATEWAY_PORT=8881
JELLYFIN_PORT=8096
SEERR_PORT=5055
SONARR_PORT=8989
RADARR_PORT=7878
PROWLARR_PORT=9696
QBITTORRENT_PORT=8080
FLARESOLVERR_PORT=8191

# ── UIDs (match host user) ──
PUID=1000
PGID=1000
TZ=America/New_York
```

### docker-compose.yml

Write a complete docker-compose.yml with ALL of these services. Key rules:

**traefik:**
- Image: `traefik:v3.3`
- Ports: 80, 443
- Volumes: `/var/run/docker.sock:/var/run/docker.sock:ro`, `./config/traefik:/etc/traefik`
- Command flags for Docker provider, entrypoints, ACME
- Labels: dashboard disabled by default

**jellyfin:**
- Image: `jellyfin/jellyfin:latest`
- Volumes: `${CONFIG_PATH}/jellyfin:/config`, `${MEDIA_PATH}:/data/media:ro`
- Traefik labels for `${DOMAIN}` routing (if DOMAIN set)
- Device passthrough commented out for GPU transcoding

**seerr:**
- Image: `ghcr.io/seerr-team/seerr:latest`
- Volumes: `${CONFIG_PATH}/seerr:/app/config`
- Traefik labels
- Depends on: jellyfin

**sonarr:**
- Image: `lscr.io/linuxserver/sonarr:latest`
- NO Traefik labels (not exposed)
- Volumes: config + media + downloads
- Environment: PUID, PGID, TZ

**radarr:**
- Same pattern as sonarr, image `lscr.io/linuxserver/radarr:latest`

**prowlarr:**
- Image: `lscr.io/linuxserver/prowlarr:latest`
- NOT exposed
- Volumes: config only
- Links to flaresolverr for indexer proxy

**gluetun:**
- Image: `qmcgaw/gluetun:latest`
- Cap_add: NET_ADMIN
- Environment from VPN_* vars
- Ports: expose qbittorrent webui port through gluetun (8080)
- Healthcheck: `wget -q --spider http://127.0.0.1:9999 || exit 1`
- Profiles: use `profiles: [vpn]` so it only starts when VPN_ENABLED

**qbittorrent:**
- Image: `lscr.io/linuxserver/qbittorrent:latest`
- `network_mode: service:gluetun` (CRITICAL — all traffic through VPN)
- NO ports (gluetun exposes them)
- Depends on: gluetun
- Volumes: config + downloads
- Profiles: `[vpn]`

**flaresolverr:**
- Image: `ghcr.io/flaresolverr/flaresolverr:latest`
- NOT exposed
- Environment: LOG_LEVEL=info, CAPTCHA_SOLVER=none

**postgres:**
- Image: `postgres:16-alpine`
- Volumes: named volume for data persistence
- Environment from POSTGRES_* vars
- Healthcheck: `pg_isready -U ${POSTGRES_USER}`

**redis:**
- Image: `redis:7-alpine`
- Healthcheck: `redis-cli ping`
- Volumes: named volume

**agent-api:**
- Build context: `./services/agent-api`
- Volumes: mount `./services/shared:/app/shared:ro`
- Depends on: postgres, redis
- Environment: all DB, Redis, RD, TMDB vars
- Healthcheck on /health
- Traefik labels: optional, route `/api/*` if DOMAIN set

**agent-worker:**
- Build context: `./services/agent-worker`
- Volumes: shared + downloads + media
- Depends on: postgres, redis, agent-api
- Environment: same as agent-api plus Prowlarr/Sonarr/Radarr API keys

**agent-qc:**
- Build context: `./services/agent-qc`
- Volumes: shared + downloads + media
- Note: Dockerfile must include ffmpeg/ffprobe

**agent-storage:**
- Build context: `./services/agent-storage`
- Volumes: shared + media

**iptv-gateway:**
- Build context: `./services/iptv-gateway`
- Volumes: shared
- Depends on: postgres, redis
- Profiles: `[iptv]`
- NOT exposed via Traefik (internal, Jellyfin calls it directly)

**Networks:**
- `internal` (default bridge for all services)

**Volumes:**
- `postgres_data`
- `redis_data`

---

## PHASE 3: SHARED LIBRARY + AGENT-API

### services/shared/config.py
- Use pydantic-settings `BaseSettings` to load from environment
- All vars from .env.template as typed fields with defaults
- Singleton pattern via lru_cache

### services/shared/database.py
- SQLAlchemy 2.0 async engine + sessionmaker
- `get_db()` async generator for FastAPI dependency injection
- Connection URL from config

### services/shared/models.py (SQLAlchemy ORM)
```python
# Tables: users, prefs, jobs, job_events, blacklists, iptv_sources, iptv_channels

class User(Base):
    __tablename__ = "users"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str]
    api_key: Mapped[str] = mapped_column(unique=True)
    created_at: Mapped[datetime]

class Prefs(Base):
    __tablename__ = "prefs"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    max_resolution: Mapped[int] = mapped_column(default=1080)
    allow_4k: Mapped[bool] = mapped_column(default=False)
    max_movie_size_gb: Mapped[float] = mapped_column(default=15.0)
    max_episode_size_gb: Mapped[float] = mapped_column(default=4.0)
    prune_watched_after_days: Mapped[Optional[int]]
    keep_favorites: Mapped[bool] = mapped_column(default=True)
    storage_soft_limit_percent: Mapped[int] = mapped_column(default=90)
    upgrade_policy: Mapped[str] = mapped_column(default="off")  # off | on

class JobState(str, enum.Enum):
    CREATED = "CREATED"
    RESOLVING = "RESOLVING"
    SEARCHING = "SEARCHING"
    SELECTED = "SELECTED"
    ACQUIRING = "ACQUIRING"
    IMPORTING = "IMPORTING"
    VERIFYING = "VERIFYING"
    DONE = "DONE"
    FAILED = "FAILED"

class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    media_type: Mapped[str]  # movie | tv
    tmdb_id: Mapped[Optional[int]]
    title: Mapped[str]
    query: Mapped[Optional[str]]
    season: Mapped[Optional[int]]
    episode: Mapped[Optional[int]]
    state: Mapped[JobState] = mapped_column(default=JobState.CREATED)
    selected_candidate: Mapped[Optional[dict]] = mapped_column(type_=JSON)
    rd_torrent_id: Mapped[Optional[str]]
    imported_path: Mapped[Optional[str]]
    retry_count: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]

class JobEvent(Base):
    __tablename__ = "job_events"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("jobs.id"))
    state: Mapped[str]
    message: Mapped[str]
    metadata_json: Mapped[Optional[dict]] = mapped_column(type_=JSON)
    created_at: Mapped[datetime]

class Blacklist(Base):
    __tablename__ = "blacklists"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    release_hash: Mapped[str]
    release_title: Mapped[str]
    reason: Mapped[str]
    created_at: Mapped[datetime]

# IPTV tables
class IptvSource(Base):
    __tablename__ = "iptv_sources"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    m3u_url: Mapped[str]
    epg_url: Mapped[Optional[str]]
    source_timezone: Mapped[str] = mapped_column(default="UTC")
    headers_json: Mapped[Optional[dict]] = mapped_column(type_=JSON)
    enabled: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime]

class IptvChannel(Base):
    __tablename__ = "iptv_channels"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("iptv_sources.id"))
    tvg_id: Mapped[Optional[str]]
    name: Mapped[str]
    group_title: Mapped[Optional[str]]
    logo: Mapped[Optional[str]]
    stream_url: Mapped[str]
    enabled: Mapped[bool] = mapped_column(default=True)
    channel_number: Mapped[Optional[int]]
    preferred_name: Mapped[Optional[str]]
    preferred_group: Mapped[Optional[str]]
```

### services/shared/schemas.py (Pydantic)
- RequestCreate: query, tmdb_id (optional), media_type, season, episode
- JobResponse: all job fields + events list
- PrefsUpdate: all pref fields (all optional for PATCH semantics)
- CandidateInfo: title, resolution, source, codec, audio, size_gb, seeders, score, magnet_link, info_hash

### services/shared/redis_client.py
- Async Redis connection via redis.asyncio
- `enqueue_job(job_id)` — push to "jobs" queue
- `dequeue_job()` — blocking pop from "jobs" queue

### services/shared/rd_client.py
- Class `RealDebridClient` with async httpx
- Base URL: `https://api.real-debrid.com/rest/1.0`
- Auth: `Authorization: Bearer {token}` header
- Methods:
  - `check_auth() -> dict` — GET /user
  - `add_magnet(magnet: str) -> str` — POST /torrents/addMagnet, returns torrent id
  - `select_files(torrent_id: str, file_ids: str = "all")` — POST /torrents/selectFiles/{id}
  - `get_torrent_info(torrent_id: str) -> dict` — GET /torrents/info/{id}
  - `poll_until_ready(torrent_id: str, timeout: int = 600) -> dict` — poll get_torrent_info until status == "downloaded"
  - `unrestrict_link(link: str) -> str` — POST /unrestrict/link, returns download URL
  - `download_file(url: str, dest_path: Path)` — stream download to local file
- Handle rate limiting (250 req/min): if 429, sleep and retry with backoff
- All errors raise custom `RealDebridError`

### services/shared/prowlarr_client.py
- Class `ProwlarrClient` with async httpx
- Base URL from config (internal: `http://prowlarr:9696`)
- Auth: `X-Api-Key` header
- Methods:
  - `search(query: str, categories: list[int] = None, indexer_ids: list[int] = None) -> list[dict]`
    - GET /api/v1/search with params
    - Returns raw Prowlarr results
  - `get_indexers() -> list[dict]` — GET /api/v1/indexer

### services/shared/tmdb_client.py
- Class `TMDBClient` with async httpx
- Base URL: `https://api.themoviedb.org/3`
- Auth: `api_key` query param
- Methods:
  - `search_movie(query: str, year: int = None) -> dict` — /search/movie
  - `search_tv(query: str, year: int = None) -> dict` — /search/tv
  - `get_movie(tmdb_id: int) -> dict` — /movie/{id}
  - `get_tv(tmdb_id: int) -> dict` — /tv/{id}
  - `resolve(query: str, media_type: str) -> tuple[int, str, int]` — returns (tmdb_id, canonical_title, year)

### services/shared/scoring.py
DETERMINISTIC scoring — NO LLM required.

```python
import re
from dataclasses import dataclass

@dataclass
class ParsedRelease:
    title: str
    resolution: int = 0       # 480, 720, 1080, 2160
    source: str = "unknown"   # BluRay, WEB-DL, WEBRip, HDTV, etc.
    codec: str = "unknown"    # x265, x264, AV1, etc.
    audio: str = "unknown"    # DTS-HD, TrueHD, Atmos, AAC, etc.
    size_gb: float = 0.0
    seeders: int = 0
    info_hash: str = ""
    magnet_link: str = ""
    indexer: str = ""
    banned: bool = False
    ban_reason: str = ""

def parse_release_title(title: str) -> ParsedRelease:
    """Extract structured metadata from release title using regex."""
    p = ParsedRelease(title=title)

    # Resolution
    m = re.search(r'(2160|1080|720|480)[pi]?', title, re.I)
    if m:
        p.resolution = int(m.group(1))

    # Source
    source_map = [
        (r'REMUX', 'REMUX'), (r'Blu[\-\.]?Ray', 'BluRay'),
        (r'WEB[\-\.]?DL', 'WEB-DL'), (r'WEB[\-\.]?Rip', 'WEBRip'),
        (r'HDRip', 'HDRip'), (r'BDRip', 'BDRip'), (r'HDTV', 'HDTV'),
        (r'DVDRip', 'DVDRip'), (r'WEB', 'WEB'),
    ]
    for pattern, label in source_map:
        if re.search(pattern, title, re.I):
            p.source = label
            break

    # Codec
    codec_map = [
        (r'[xh][\.\-]?265|HEVC', 'x265'), (r'[xh][\.\-]?264|AVC', 'x264'),
        (r'AV1', 'AV1'), (r'VP9', 'VP9'), (r'MPEG[\-]?2', 'MPEG2'),
    ]
    for pattern, label in codec_map:
        if re.search(pattern, title, re.I):
            p.codec = label
            break

    # Audio
    audio_map = [
        (r'DTS[\-\.]?HD(?:[\.\-]?MA)?', 'DTS-HD'), (r'TrueHD', 'TrueHD'),
        (r'Atmos', 'Atmos'), (r'DTS', 'DTS'), (r'DD[\+P]?5[\.\-]1', 'DD5.1'),
        (r'AAC', 'AAC'), (r'FLAC', 'FLAC'), (r'EAC3|E-AC-3', 'EAC3'),
        (r'AC3|AC-3', 'AC3'),
    ]
    for pattern, label in audio_map:
        if re.search(pattern, title, re.I):
            p.audio = label
            break

    # Banned tags (hard reject)
    banned_tags = [r'\bCAM\b', r'\bTS\b', r'\bHDCAM\b', r'\bTELESYNC\b', r'\bHDTS\b']
    for bt in banned_tags:
        if re.search(bt, title, re.I):
            p.banned = True
            p.ban_reason = f"Banned tag: {bt}"
            break

    return p


def score_candidate(parsed: ParsedRelease, prefs: dict) -> int:
    """Score a release candidate. Higher = better. Returns -1 if rejected by policy."""
    if parsed.banned:
        return -1

    # Hard policy filters
    max_res = prefs.get("max_resolution", 1080)
    if parsed.resolution > max_res:
        if parsed.resolution == 2160 and not prefs.get("allow_4k", False):
            return -1

    max_size = prefs.get("max_movie_size_gb", 15.0)  # caller passes correct field
    if parsed.size_gb > 0 and parsed.size_gb > max_size:
        return -1

    # Resolution score
    res_scores = {2160: 100, 1080: 80, 720: 50, 480: 20}
    score = res_scores.get(parsed.resolution, 10)

    # Source score
    src_scores = {"REMUX": 100, "BluRay": 90, "WEB-DL": 80, "WEB": 75,
                  "WEBRip": 60, "BDRip": 55, "HDRip": 50, "HDTV": 40,
                  "DVDRip": 20, "unknown": 10}
    score += src_scores.get(parsed.source, 10)

    # Codec score
    codec_scores = {"AV1": 85, "x265": 80, "x264": 60, "VP9": 50,
                    "MPEG2": 20, "unknown": 30}
    score += codec_scores.get(parsed.codec, 30)

    # Seeder bonus (cap at 20)
    score += min(parsed.seeders // 10, 20)

    return score


def select_best_candidate(candidates: list[ParsedRelease], prefs: dict) -> ParsedRelease | None:
    """Pick the best candidate by score. Ties broken by smallest size."""
    scored = [(c, score_candidate(c, prefs)) for c in candidates]
    valid = [(c, s) for c, s in scored if s > 0]
    if not valid:
        return None
    valid.sort(key=lambda x: (-x[1], x[0].size_gb))
    return valid[0][0]
```

### services/shared/naming.py
```python
import re
from pathlib import Path

def movie_path(title: str, year: int, ext: str) -> Path:
    """Movies: Title (Year)/Title (Year).ext"""
    clean = sanitize(title)
    folder = f"{clean} ({year})"
    return Path(folder) / f"{clean} ({year}){ext}"

def tv_path(show: str, season: int, episode: int, ext: str) -> Path:
    """TV: Show/Season 01/Show - S01E01.ext"""
    clean = sanitize(show)
    return Path(clean) / f"Season {season:02d}" / f"{clean} - S{season:02d}E{episode:02d}{ext}"

def sanitize(name: str) -> str:
    """Remove filesystem-unsafe characters."""
    return re.sub(r'[<>:"/\\|?*]', '', name).strip()
```

### agent-api/main.py
- FastAPI app with lifespan (init DB, Redis on startup)
- Include all routers
- CORS middleware (allow all origins for dev)
- Exception handlers

### agent-api/routers/health.py
```
GET /health → {"status": "ok", "db": "connected", "redis": "connected", "version": "1.0.0"}
```
Actually ping DB and Redis.

### agent-api/routers/requests.py
```
POST /v1/request
Body: {"query": "...", "tmdb_id": null, "media_type": "movie", "season": null, "episode": null}
→ Create Job row (state=CREATED), enqueue to Redis, return job
```

### agent-api/routers/jobs.py
```
GET /v1/jobs/{id} → Job + events
GET /v1/jobs?status=&limit=20 → list of recent jobs
```

### agent-api/routers/prefs.py
```
POST /v1/prefs → Create or update user preferences
GET /v1/prefs → Get current prefs
```

### agent-api/routers/webhooks.py
```
POST /v1/webhooks/arr → Receive Sonarr/Radarr webhook payload, log to job_events
```

### Dockerfile for agent-api
```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
COPY ../shared /app/shared
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8880"]
```

### requirements.txt for agent-api
```
fastapi>=0.115.0
uvicorn[standard]>=0.34.0
sqlalchemy[asyncio]>=2.0
asyncpg>=0.30.0
alembic>=1.14.0
pydantic>=2.10.0
pydantic-settings>=2.7.0
redis>=5.2.0
httpx>=0.28.0
```

---

## PHASE 4: AGENT-WORKER (SCORING + STATE MACHINE)

### agent-worker/worker.py

The main job processing loop:

```python
async def process_job(job_id: str):
    """Main job pipeline. Each step transitions state and logs event."""

    job = await get_job(job_id)
    prefs = await get_prefs(job.user_id)

    # 1. RESOLVE
    await transition(job, JobState.RESOLVING, "Resolving TMDB identity")
    tmdb_id, title, year = await tmdb_client.resolve(job.query or job.title, job.media_type)
    job.tmdb_id = tmdb_id
    job.title = title

    # 2. SEARCH
    await transition(job, JobState.SEARCHING, f"Searching Prowlarr for: {title}")
    raw_results = await prowlarr_client.search(
        query=f"{title} {year}",
        categories=[2000] if job.media_type == "movie" else [5000]
    )

    # 3. PARSE + SCORE
    candidates = []
    for r in raw_results:
        parsed = parse_release_title(r["title"])
        parsed.size_gb = r.get("size", 0) / (1024**3)
        parsed.seeders = r.get("seeders", 0)
        parsed.info_hash = r.get("infoHash", "")
        parsed.magnet_link = r.get("magnetUrl") or r.get("downloadUrl", "")
        parsed.indexer = r.get("indexer", "")
        # Check blacklist
        if not is_blacklisted(job.user_id, parsed.info_hash):
            candidates.append(parsed)

    # 4. SELECT
    best = select_best_candidate(candidates, prefs_to_dict(prefs))
    if not best:
        await transition(job, JobState.FAILED, "No valid candidates found")
        return

    job.selected_candidate = asdict(best)
    await transition(job, JobState.SELECTED, f"Selected: {best.title} ({best.resolution}p, {best.source}, {best.size_gb:.1f}GB, score={score_candidate(best, prefs_to_dict(prefs))})")

    # 5. ACQUIRE (Phase 5 implements this)
    await acquire(job, best, prefs)
```

### agent-worker/main.py
- Redis queue consumer loop
- `while True: job_id = await dequeue_job(); await process_job(job_id)`
- Graceful shutdown on SIGTERM
- Error handling: on unhandled exception, transition to FAILED

---

## PHASE 5: REAL-DEBRID INTEGRATION + IMPORT

Extend `process_job()` with the acquire step:

```python
async def acquire(job: Job, candidate: ParsedRelease, prefs: Prefs):
    """Acquire via Real-Debrid, then import."""
    config = get_config()

    if config.rd_enabled and config.rd_api_token:
        await acquire_via_rd(job, candidate)
    elif config.vpn_enabled:
        await acquire_via_torrent(job, candidate)  # Future: qBittorrent API
    else:
        await transition(job, JobState.FAILED, "No acquisition path available (RD disabled, VPN disabled)")
        return

async def acquire_via_rd(job: Job, candidate: ParsedRelease):
    rd = RealDebridClient(config.rd_api_token)

    # ACQUIRING
    await transition(job, JobState.ACQUIRING, "Adding magnet to Real-Debrid")
    torrent_id = await rd.add_magnet(candidate.magnet_link)
    job.rd_torrent_id = torrent_id

    # Select files (video files only)
    await rd.select_files(torrent_id, "all")

    # Poll until ready
    await transition(job, JobState.ACQUIRING, "Waiting for Real-Debrid to cache/download")
    info = await rd.poll_until_ready(torrent_id, timeout=600)

    # Download each link
    staging_dir = Path(config.downloads_path) / "rd" / str(job.id)
    staging_dir.mkdir(parents=True, exist_ok=True)

    for link_info in info["links"]:
        download_url = await rd.unrestrict_link(link_info)
        filename = download_url.split("/")[-1].split("?")[0]
        dest = staging_dir / filename
        await rd.download_file(download_url, dest)

    # IMPORT
    await transition(job, JobState.IMPORTING, "Importing to media library")
    await import_files(job, staging_dir)

async def import_files(job: Job, staging_dir: Path):
    """Rename and move files to media library with correct naming."""
    config = get_config()
    media_root = Path(config.media_path)

    video_extensions = {".mkv", ".mp4", ".avi", ".m4v", ".wmv", ".ts"}
    video_files = [f for f in staging_dir.iterdir() if f.suffix.lower() in video_extensions]

    if not video_files:
        await transition(job, JobState.FAILED, "No video files found in download")
        return

    for vf in video_files:
        if job.media_type == "movie":
            rel = movie_path(job.title, get_year(job), vf.suffix)
            dest = media_root / "Movies" / rel
        else:
            rel = tv_path(job.title, job.season or 1, job.episode or 1, vf.suffix)
            dest = media_root / "TV" / rel

        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(vf), str(dest))
        job.imported_path = str(dest)

    # Clean staging
    shutil.rmtree(staging_dir, ignore_errors=True)

    # Trigger QC
    await enqueue_qc(job.id)
    await transition(job, JobState.VERIFYING, f"File imported to {job.imported_path}, running QC")
```

---

## PHASE 6: AGENT-QC (ffprobe)

### agent-qc/qc.py

```python
import subprocess
import json

async def validate_file(file_path: str) -> tuple[bool, str]:
    """Run ffprobe and validate the file."""
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", "-show_streams", file_path],
            capture_output=True, text=True, timeout=60
        )
        if result.returncode != 0:
            return False, f"ffprobe failed: {result.stderr}"

        data = json.loads(result.stdout)
        streams = data.get("streams", [])
        fmt = data.get("format", {})

        # Check video stream exists
        video_streams = [s for s in streams if s["codec_type"] == "video"]
        if not video_streams:
            return False, "No video stream found"

        # Check audio stream exists
        audio_streams = [s for s in streams if s["codec_type"] == "audio"]
        if not audio_streams:
            return False, "No audio stream found"

        # Check duration (>5 min for TV, >20 min for movies)
        duration = float(fmt.get("duration", 0))
        if duration < 300:  # Less than 5 minutes
            return False, f"Duration too short: {duration:.0f}s (likely a sample)"

        # Check file size (>100MB for movies)
        size_mb = int(fmt.get("size", 0)) / (1024 * 1024)
        if size_mb < 100:
            return False, f"File too small: {size_mb:.0f}MB (likely fake)"

        # Check resolution
        video = video_streams[0]
        width = int(video.get("width", 0))
        height = int(video.get("height", 0))
        if width < 320 or height < 240:
            return False, f"Resolution too low: {width}x{height}"

        return True, f"Valid: {width}x{height}, {duration:.0f}s, {size_mb:.0f}MB"

    except subprocess.TimeoutExpired:
        return False, "ffprobe timed out"
    except Exception as e:
        return False, f"QC error: {str(e)}"
```

### agent-qc/main.py
- Redis queue consumer for QC jobs
- On pass: transition job to DONE, trigger Jellyfin library scan
- On fail: add to blacklists table, if retry_count < 1 then re-enqueue for retry with next candidate, else FAILED

### agent-qc/Dockerfile
```dockerfile
FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
COPY ../shared /app/shared
CMD ["python", "main.py"]
```

---

## PHASE 7: IPTV GATEWAY

### iptv-gateway/m3u_parser.py
```python
def parse_m3u(content: str) -> list[dict]:
    """Parse M3U playlist into channel dicts."""
    channels = []
    lines = content.strip().split("\n")
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith("#EXTINF:"):
            info = parse_extinf(line)
            if i + 1 < len(lines) and not lines[i+1].startswith("#"):
                info["stream_url"] = lines[i+1].strip()
                channels.append(info)
                i += 2
                continue
        i += 1
    return channels

def parse_extinf(line: str) -> dict:
    """Extract tvg-id, tvg-name, tvg-logo, group-title from EXTINF line."""
    import re
    info = {}
    info["tvg_id"] = extract_attr(line, "tvg-id")
    info["name"] = extract_attr(line, "tvg-name") or line.split(",")[-1].strip()
    info["logo"] = extract_attr(line, "tvg-logo")
    info["group_title"] = extract_attr(line, "group-title")
    return info

def extract_attr(line: str, attr: str) -> str | None:
    import re
    m = re.search(f'{attr}="([^"]*)"', line)
    return m.group(1) if m else None

def generate_m3u(channels: list[dict]) -> str:
    """Generate M3U playlist string from channel list."""
    lines = ["#EXTM3U"]
    for ch in channels:
        attrs = []
        if ch.get("tvg_id"): attrs.append(f'tvg-id="{ch["tvg_id"]}"')
        if ch.get("logo"): attrs.append(f'tvg-logo="{ch["logo"]}"')
        if ch.get("group_title"): attrs.append(f'group-title="{ch["group_title"]}"')
        attr_str = " ".join(attrs)
        name = ch.get("preferred_name") or ch.get("name", "Unknown")
        lines.append(f'#EXTINF:-1 {attr_str},{name}')
        lines.append(ch["stream_url"])
    return "\n".join(lines)
```

### iptv-gateway/xmltv_parser.py
```python
from lxml import etree

def parse_xmltv(content: str) -> etree._Element:
    """Parse XMLTV string into lxml tree."""
    return etree.fromstring(content.encode("utf-8") if isinstance(content, str) else content)

def get_programmes(tree: etree._Element) -> list[etree._Element]:
    """Get all programme elements."""
    return tree.findall(".//programme")

def get_channels(tree: etree._Element) -> list[dict]:
    """Extract channel info from XMLTV."""
    channels = []
    for ch in tree.findall(".//channel"):
        channels.append({
            "id": ch.get("id"),
            "name": ch.findtext("display-name", ""),
            "icon": ch.find("icon").get("src") if ch.find("icon") is not None else None,
        })
    return channels
```

### iptv-gateway/timezone_converter.py

THIS IS THE CORE IPTV FEATURE. Implement carefully.

```python
from datetime import datetime
from zoneinfo import ZoneInfo
import re

def convert_xmltv_time(time_str: str, source_tz: str, target_tz: str) -> str:
    """Convert XMLTV timestamp to target timezone.

    XMLTV timestamps:
    - With offset: "20260228120000 +0100" → parse offset directly
    - Without offset: "20260228120000" → treat as source_timezone
    """
    # Parse the base datetime
    m = re.match(r'(\d{14})\s*([+-]\d{4})?', time_str.strip())
    if not m:
        return time_str

    dt_str = m.group(1)
    offset_str = m.group(2)

    dt = datetime.strptime(dt_str, "%Y%m%d%H%M%S")

    if offset_str:
        # Has explicit offset — parse it
        sign = 1 if offset_str[0] == '+' else -1
        hours = int(offset_str[1:3])
        minutes = int(offset_str[3:5])
        from datetime import timezone, timedelta
        tz = timezone(timedelta(hours=sign * hours, minutes=sign * minutes))
        dt = dt.replace(tzinfo=tz)
    else:
        # No offset — assume source_timezone
        dt = dt.replace(tzinfo=ZoneInfo(source_tz))

    # Convert to target
    target = dt.astimezone(ZoneInfo(target_tz))
    return target.strftime("%Y%m%d%H%M%S %z")


def localize_xmltv(xmltv_content: str, source_tz: str, target_tz: str) -> str:
    """Convert all programme times in XMLTV to target timezone."""
    from lxml import etree
    tree = etree.fromstring(xmltv_content.encode("utf-8") if isinstance(xmltv_content, str) else xmltv_content)

    for prog in tree.findall(".//programme"):
        for attr in ["start", "stop"]:
            val = prog.get(attr)
            if val:
                prog.set(attr, convert_xmltv_time(val, source_tz, target_tz))

    return etree.tostring(tree, encoding="unicode", xml_declaration=True)
```

### iptv-gateway/routers/sources.py
```
POST /v1/iptv/sources → Add source, fetch+parse M3U, store channels in DB
GET /v1/iptv/sources → List user sources
DELETE /v1/iptv/sources/{id}
```

### iptv-gateway/routers/channels.py
```
GET /v1/iptv/channels?source_id=&group=&enabled= → List channels with filters
POST /v1/iptv/channels/bulk → [{"id": ..., "enabled": true, "channel_number": 1, "preferred_name": "..."}]
```

### iptv-gateway/routers/playlist.py
```
GET /playlist.m3u?user_token=... → Generate merged M3U from all enabled sources/channels
GET /epg.xml?user_token=...&tz=America/New_York → Generate timezone-localized XMLTV
```
- Auth by user_token query param (lookup user by api_key)
- Cache EPG in Redis with 1-hour TTL
- Return proper Content-Type headers (application/x-mpegurl, application/xml)

---

## PHASE 8: INSTALL.SH + SMOKE.SH

### scripts/install.sh
```bash
#!/usr/bin/env bash
set -euo pipefail

echo "═══════════════════════════════════════"
echo "  Invisible Arr — Edge Node Installer"
echo "═══════════════════════════════════════"

# Check Docker
if ! command -v docker &> /dev/null; then
    echo "❌ Docker not found. Install: https://docs.docker.com/engine/install/"
    exit 1
fi
if ! docker compose version &> /dev/null; then
    echo "❌ Docker Compose v2 not found."
    exit 1
fi
echo "✅ Docker + Compose found"

# Generate .env
if [ ! -f .env ]; then
    cp .env.template .env
    POSTGRES_PW=$(openssl rand -hex 16)
    sed -i "s/CHANGEME_GENERATE_THIS/$POSTGRES_PW/" .env
    echo "📝 Generated .env with random Postgres password"

    # Interactive prompts
    read -p "TMDB API Key (required): " TMDB_KEY
    sed -i "s/^TMDB_API_KEY=.*/TMDB_API_KEY=$TMDB_KEY/" .env

    read -p "Real-Debrid API Token (optional, press Enter to skip): " RD_TOKEN
    if [ -n "$RD_TOKEN" ]; then
        sed -i "s/^RD_API_TOKEN=.*/RD_API_TOKEN=$RD_TOKEN/" .env
        sed -i "s/^RD_ENABLED=.*/RD_ENABLED=true/" .env
    fi

    read -p "Domain for TLS (optional, press Enter for local-only): " DOMAIN
    if [ -n "$DOMAIN" ]; then
        sed -i "s/^DOMAIN=.*/DOMAIN=$DOMAIN/" .env
        read -p "Email for Let's Encrypt: " ACME_EMAIL
        sed -i "s/^ACME_EMAIL=.*/ACME_EMAIL=$ACME_EMAIL/" .env
    fi

    read -p "Enable VPN? (y/N): " VPN_YN
    if [[ "$VPN_YN" =~ ^[Yy]$ ]]; then
        sed -i "s/^VPN_ENABLED=.*/VPN_ENABLED=true/" .env
        read -p "VPN Provider (e.g., mullvad, nordvpn): " VPN_PROV
        sed -i "s/^VPN_PROVIDER=.*/VPN_PROVIDER=$VPN_PROV/" .env
    fi

    read -p "Enable IPTV Gateway? (y/N): " IPTV_YN
    if [[ "$IPTV_YN" =~ ^[Yy]$ ]]; then
        sed -i "s/^IPTV_ENABLED=.*/IPTV_ENABLED=true/" .env
    fi

    echo "📝 .env configured"
else
    echo "ℹ️  .env already exists, skipping generation"
fi

# Create directories
mkdir -p config/{traefik,jellyfin,seerr,sonarr,radarr,prowlarr,qbittorrent}
mkdir -p data/{media/{Movies,TV},downloads/rd}
echo "📁 Directories created"

# Build and start
COMPOSE_PROFILES=""
source .env
if [ "$VPN_ENABLED" = "true" ]; then COMPOSE_PROFILES="vpn"; fi
if [ "$IPTV_ENABLED" = "true" ]; then
    [ -n "$COMPOSE_PROFILES" ] && COMPOSE_PROFILES="$COMPOSE_PROFILES,iptv" || COMPOSE_PROFILES="iptv"
fi

if [ -n "$COMPOSE_PROFILES" ]; then
    COMPOSE_PROFILES="$COMPOSE_PROFILES" docker compose up -d --build
else
    docker compose up -d --build
fi

echo ""
echo "═══════════════════════════════════════"
echo "  ✅ Stack is starting!"
echo "═══════════════════════════════════════"
echo "  Seerr:    http://localhost:${SEERR_PORT:-5055}"
echo "  Jellyfin: http://localhost:${JELLYFIN_PORT:-8096}"
echo "  API:      http://localhost:${AGENT_API_PORT:-8880}/health"
if [ -n "${DOMAIN:-}" ]; then
    echo "  Seerr:    https://$DOMAIN"
fi
echo ""
echo "Run 'bash scripts/smoke.sh' to verify everything is healthy."
```

### scripts/smoke.sh
```bash
#!/usr/bin/env bash
set -euo pipefail

source .env 2>/dev/null || true
PASS=0; FAIL=0; SKIP=0

check() {
    local name="$1" result="$2"
    if [ "$result" = "SKIP" ]; then
        echo "⏭️  $name (skipped)"
        SKIP=$((SKIP + 1))
    elif [ "$result" = "PASS" ]; then
        echo "✅ $name"
        PASS=$((PASS + 1))
    else
        echo "❌ $name — $result"
        FAIL=$((FAIL + 1))
    fi
}

echo "═══════════════════════════════════"
echo "  Invisible Arr — Smoke Tests"
echo "═══════════════════════════════════"

# Postgres
PG=$(docker compose exec -T postgres pg_isready -U ${POSTGRES_USER:-invisiblearr} 2>&1 && echo "PASS" || echo "pg_isready failed")
check "PostgreSQL" "$PG"

# Redis
RD_PING=$(docker compose exec -T redis redis-cli ping 2>&1)
[ "$RD_PING" = "PONG" ] && check "Redis" "PASS" || check "Redis" "$RD_PING"

# agent-api
API_HEALTH=$(curl -sf http://localhost:${AGENT_API_PORT:-8880}/health 2>&1 && echo "PASS" || echo "unreachable")
check "agent-api /health" "$API_HEALTH"

# Seerr
SEERR=$(curl -sf -o /dev/null -w "%{http_code}" http://localhost:${SEERR_PORT:-5055} 2>&1)
[ "$SEERR" = "200" ] || [ "$SEERR" = "302" ] && check "Seerr" "PASS" || check "Seerr" "HTTP $SEERR"

# Jellyfin
JF=$(curl -sf -o /dev/null -w "%{http_code}" http://localhost:${JELLYFIN_PORT:-8096}/health 2>&1)
[ "$JF" = "200" ] && check "Jellyfin" "PASS" || check "Jellyfin" "HTTP $JF"

# Real-Debrid auth
if [ "${RD_ENABLED:-false}" = "true" ] && [ -n "${RD_API_TOKEN:-}" ]; then
    RD_AUTH=$(curl -sf -H "Authorization: Bearer $RD_API_TOKEN" https://api.real-debrid.com/rest/1.0/user 2>&1 && echo "PASS" || echo "auth failed")
    check "Real-Debrid auth" "$RD_AUTH"
else
    check "Real-Debrid auth" "SKIP"
fi

# VPN leak test
if [ "${VPN_ENABLED:-false}" = "true" ]; then
    VPS_IP=$(curl -sf https://api.ipify.org 2>&1 || echo "unknown")
    QBIT_IP=$(docker compose exec -T gluetun wget -qO- https://api.ipify.org 2>&1 || echo "unknown")
    if [ "$VPS_IP" != "$QBIT_IP" ] && [ "$QBIT_IP" != "unknown" ]; then
        check "VPN leak test (VPS=$VPS_IP, VPN=$QBIT_IP)" "PASS"
    else
        check "VPN leak test" "VPS=$VPS_IP QBIT=$QBIT_IP — POSSIBLE LEAK"
    fi
else
    check "VPN leak test" "SKIP"
fi

# IPTV gateway
if [ "${IPTV_ENABLED:-false}" = "true" ]; then
    IPTV=$(curl -sf -o /dev/null -w "%{http_code}" http://localhost:${IPTV_GATEWAY_PORT:-8881}/health 2>&1)
    [ "$IPTV" = "200" ] && check "iptv-gateway" "PASS" || check "iptv-gateway" "HTTP $IPTV"
else
    check "iptv-gateway" "SKIP"
fi

# Job dry-run (create request, check it reaches SELECTED)
DRY_RUN=$(curl -sf -X POST http://localhost:${AGENT_API_PORT:-8880}/v1/request \
    -H "Content-Type: application/json" \
    -d '{"query":"The Matrix","media_type":"movie"}' 2>&1)
if echo "$DRY_RUN" | grep -q '"id"'; then
    JOB_ID=$(echo "$DRY_RUN" | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])" 2>/dev/null)
    echo "ℹ️  Job created: $JOB_ID — check GET /v1/jobs/$JOB_ID for state progression"
    check "Job dry-run (created)" "PASS"
else
    check "Job dry-run" "Failed to create: $DRY_RUN"
fi

# Traefik (if domain)
if [ -n "${DOMAIN:-}" ]; then
    TF=$(curl -sf -o /dev/null -w "%{http_code}" https://$DOMAIN 2>&1)
    [ "$TF" = "200" ] || [ "$TF" = "302" ] && check "Traefik TLS ($DOMAIN)" "PASS" || check "Traefik TLS" "HTTP $TF"
else
    check "Traefik TLS" "SKIP"
fi

echo ""
echo "═══════════════════════════════════"
echo "  Results: ✅ $PASS passed, ❌ $FAIL failed, ⏭️ $SKIP skipped"
echo "═══════════════════════════════════"
[ $FAIL -eq 0 ] && exit 0 || exit 1
```

---

## PHASE 9: ALEMBIC MIGRATIONS

### migrations/alembic.ini
Standard config pointing to env.py. sqlalchemy.url = from DATABASE_URL env var.

### migrations/env.py
- Import all models from shared/models.py
- Use async engine
- target_metadata = Base.metadata

### migrations/versions/001_initial_schema.py
Auto-generate from all models: users, prefs, jobs, job_events, blacklists, iptv_sources, iptv_channels.

---

## CONSTRAINTS

1. **Python 3.12+** everywhere. Use modern typing (X | None, not Optional[X]).
2. **Async throughout.** All DB access, HTTP calls, Redis operations are async.
3. **No LLM in default path.** LLM_PROVIDER=none must work end-to-end. LLM is a future optional tie-breaker only.
4. **Type hints on every function.** Use Pydantic models for all API I/O.
5. **Logging, not print.** Use Python `logging` module with structured output.
6. **Error handling.** Every external call (RD, Prowlarr, TMDB, ffprobe) wrapped in try/except with job_events logging.
7. **Windows-compatible file creation.** No symlinks. Use forward slashes in paths. This is being developed on Windows with VS Code.
8. **All files must be complete and runnable.** No TODOs, no placeholders, no "implement this later." Every function has a real implementation.

---

## AFTER COMPLETION

After all phases, list:
1. Every file created with its path
2. How to test locally without Docker (just the Python code): `pip install -r requirements.txt && uvicorn main:app`
3. How to deploy: `cd edge-node && bash scripts/install.sh`
4. What needs manual config: Seerr → Jellyfin, Prowlarr indexers, Sonarr/Radarr root folders
