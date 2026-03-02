"""Media file naming and path generation.

Produces Jellyfin/Plex-compatible folder structures:
- Movies: ``Title (Year)/Title (Year).ext``
- TV: ``Show/Season 01/Show - S01E01.ext``
"""

import re
from pathlib import Path


def sanitize(name: str) -> str:
    """Remove filesystem-unsafe characters and path traversal sequences."""
    name = name.replace('..', '')
    return re.sub(r'[<>:"/\\|?*]', '', name).strip()


def validate_path(dest: Path, root: Path) -> Path:
    """Resolve *dest* and ensure it lives under *root*.

    Raises
    ------
    ValueError
        If the resolved *dest* escapes the *root* directory.
    """
    resolved_dest = dest.resolve()
    resolved_root = root.resolve()
    try:
        resolved_dest.relative_to(resolved_root)
    except ValueError:
        raise ValueError(
            f"Path {resolved_dest} is outside root {resolved_root}"
        ) from None
    return resolved_dest


def movie_path(title: str, year: int, ext: str) -> Path:
    """Return the relative path for a movie file.

    Example::

        >>> movie_path("The Matrix", 1999, ".mkv")
        PosixPath('The Matrix (1999)/The Matrix (1999).mkv')
    """
    clean = sanitize(title)
    folder = f"{clean} ({year})"
    return Path(folder) / f"{clean} ({year}){ext}"


def tv_path(show: str, season: int, episode: int, ext: str) -> Path:
    """Return the relative path for a TV episode file.

    Example::

        >>> tv_path("Breaking Bad", 1, 1, ".mkv")
        PosixPath('Breaking Bad/Season 01/Breaking Bad - S01E01.mkv')
    """
    clean = sanitize(show)
    return (
        Path(clean)
        / f"Season {season:02d}"
        / f"{clean} - S{season:02d}E{episode:02d}{ext}"
    )
