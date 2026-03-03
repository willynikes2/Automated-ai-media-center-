"""Application configuration loaded from environment variables via pydantic-settings."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All configuration for the Invisible Arr edge node.

    Values are loaded from environment variables (case-insensitive).
    A .env file in the working directory is also read automatically.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Domain & TLS
    domain: str = ""
    acme_email: str = ""

    # TMDB
    tmdb_api_key: str = ""

    # Real-Debrid
    rd_api_token: str = ""
    rd_enabled: bool = False

    # VPN
    vpn_enabled: bool = False
    vpn_provider: str = ""

    # qBittorrent (VPN torrent fallback)
    qbt_url: str = "http://gluetun:8080"
    qbt_username: str = "admin"
    qbt_password: str = ""

    # Usenet
    usenet_enabled: bool = False
    sabnzbd_url: str = "http://sabnzbd:8080"
    sabnzbd_api_key: str = ""

    # LLM (optional)
    llm_provider: str = "none"
    llm_api_key: str = ""
    llm_model: str = ""

    # Storage paths
    data_path: str = "./data"
    config_path: str = "./config"
    media_path: str = "./data/media"
    downloads_path: str = "./data/downloads"

    # Database
    postgres_user: str = "invisiblearr"
    postgres_password: str = ""
    postgres_db: str = "invisiblearr"
    database_url: str = ""

    # Redis
    redis_url: str = "redis://redis:6379/0"
    redis_password: str = ""

    # Quality defaults
    default_max_resolution: int = 1080
    default_allow_4k: bool = False
    default_max_movie_size_gb: float = 15.0
    default_max_episode_size_gb: float = 4.0

    # IPTV
    iptv_enabled: bool = False

    # Service ports
    agent_api_port: int = 8880
    iptv_gateway_port: int = 8881

    # Arr stack URLs
    prowlarr_url: str = "http://prowlarr:9696"
    prowlarr_api_key: str = ""
    sonarr_url: str = "http://sonarr:8989"
    sonarr_api_key: str = ""
    radarr_url: str = "http://radarr:7878"
    radarr_api_key: str = ""

    # Jellyfin
    jellyfin_url: str = "http://jellyfin:8096"

    # UIDs
    puid: int = 1000
    pgid: int = 1000
    tz: str = "America/New_York"


@lru_cache(maxsize=1)
def get_config() -> Settings:
    """Return a cached singleton of the application settings."""
    return Settings()
