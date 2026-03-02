"""M3U playlist parser and generator for IPTV channel lists."""

import logging
import re

logger = logging.getLogger(__name__)

_ATTR_PATTERN = re.compile(r'(\w[\w-]*)="([^"]*)"')


def extract_attr(line: str, attr: str) -> str | None:
    """Extract a named attribute value from an EXTINF line.

    Attributes follow the pattern: attr="value"

    Parameters
    ----------
    line:
        The full #EXTINF line.
    attr:
        The attribute name to extract (e.g. ``tvg-id``, ``tvg-logo``).

    Returns
    -------
    str | None
        The attribute value if found, otherwise ``None``.
    """
    pattern = re.compile(rf'{re.escape(attr)}="([^"]*)"')
    match = pattern.search(line)
    if match:
        return match.group(1) or None
    return None


def parse_extinf(line: str) -> dict:
    """Parse an #EXTINF line into a channel metadata dictionary.

    Expected format::

        #EXTINF:-1 tvg-id="channel.id" tvg-name="Name" tvg-logo="http://logo.png" group-title="Group",Display Name

    Parameters
    ----------
    line:
        A single #EXTINF line from an M3U file.

    Returns
    -------
    dict
        Keys: ``tvg_id``, ``name``, ``logo``, ``group_title``.
    """
    tvg_id = extract_attr(line, "tvg-id")
    tvg_name = extract_attr(line, "tvg-name")
    logo = extract_attr(line, "tvg-logo")
    group_title = extract_attr(line, "group-title")

    # The display name follows the last comma in the EXTINF line
    display_name: str | None = None
    comma_idx = line.rfind(",")
    if comma_idx != -1:
        display_name = line[comma_idx + 1 :].strip() or None

    # Prefer tvg-name, fall back to display name
    name = tvg_name or display_name or "Unknown"

    return {
        "tvg_id": tvg_id,
        "name": name,
        "logo": logo,
        "group_title": group_title,
    }


def parse_m3u(content: str) -> list[dict]:
    """Parse an M3U playlist string into a list of channel dictionaries.

    Each channel dict contains: ``tvg_id``, ``name``, ``logo``,
    ``group_title``, ``stream_url``.

    Parameters
    ----------
    content:
        The full M3U file content as a string.

    Returns
    -------
    list[dict]
        Parsed channel entries.
    """
    channels: list[dict] = []
    lines = content.strip().splitlines()

    if not lines:
        logger.warning("Empty M3U content received")
        return channels

    # Optionally skip #EXTM3U header
    current_meta: dict | None = None

    for line in lines:
        line = line.strip()
        if not line:
            continue

        if line.startswith("#EXTINF"):
            current_meta = parse_extinf(line)
        elif line.startswith("#"):
            # Skip other directives (#EXTM3U, #EXTVLCOPT, etc.)
            continue
        else:
            # This is a stream URL line
            if current_meta is not None:
                current_meta["stream_url"] = line
                channels.append(current_meta)
                current_meta = None
            else:
                # URL without preceding EXTINF -- still capture it
                channels.append({
                    "tvg_id": None,
                    "name": "Unknown",
                    "logo": None,
                    "group_title": None,
                    "stream_url": line,
                })

    logger.info("Parsed %d channels from M3U content", len(channels))
    return channels


def generate_m3u(channels: list[dict]) -> str:
    """Generate an M3U playlist string from a list of channel dictionaries.

    Uses ``preferred_name`` over ``name`` if present and non-empty.
    Uses ``preferred_group`` over ``group_title`` if present and non-empty.

    Parameters
    ----------
    channels:
        List of channel dicts. Expected keys: ``tvg_id``, ``name``,
        ``preferred_name``, ``logo``, ``group_title``, ``preferred_group``,
        ``stream_url``, and optionally ``channel_number``.

    Returns
    -------
    str
        A valid M3U playlist string.
    """
    lines: list[str] = ["#EXTM3U"]

    for ch in channels:
        display_name = ch.get("preferred_name") or ch.get("name", "Unknown")
        group = ch.get("preferred_group") or ch.get("group_title", "")
        tvg_id = ch.get("tvg_id", "") or ""
        logo = ch.get("logo", "") or ""
        channel_number = ch.get("channel_number")

        attrs: list[str] = []
        if tvg_id:
            attrs.append(f'tvg-id="{tvg_id}"')
        if channel_number is not None:
            attrs.append(f'tvg-chno="{channel_number}"')
        if logo:
            attrs.append(f'tvg-logo="{logo}"')
        if group:
            attrs.append(f'group-title="{group}"')

        attr_str = " ".join(attrs)
        if attr_str:
            attr_str = " " + attr_str

        lines.append(f"#EXTINF:-1{attr_str},{display_name}")
        lines.append(ch.get("stream_url", ""))

    return "\n".join(lines) + "\n"
