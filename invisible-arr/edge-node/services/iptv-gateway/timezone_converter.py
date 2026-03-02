"""XMLTV timezone conversion -- the core IPTV EPG feature.

Converts programme start/stop times between timezones using stdlib
``zoneinfo`` and ``datetime``.  Handles XMLTV timestamps both with and
without UTC-offset suffixes.
"""

import logging
import re
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

from lxml import etree

logger = logging.getLogger(__name__)

# Matches XMLTV time format: YYYYMMDDHHmmSS optionally followed by " +/-HHMM"
_XMLTV_TIME_RE = re.compile(
    r"^(\d{14})\s*([+-]\d{4})?$"
)


def convert_xmltv_time(
    time_str: str,
    source_tz: str,
    target_tz: str,
) -> str:
    """Convert a single XMLTV timestamp between timezones.

    XMLTV timestamps are formatted as ``YYYYMMDDHHmmSS +HHMM`` (with offset)
    or ``YYYYMMDDHHmmSS`` (without offset).

    - If an offset is present in *time_str*, it is parsed directly and the
      ``source_tz`` parameter is ignored for that timestamp.
    - If no offset is present, the time is treated as local to ``source_tz``.

    The result is always expressed in ``target_tz`` and formatted as
    ``%Y%m%d%H%M%S %z`` (e.g. ``"20260228070000 -0500"``).

    Parameters
    ----------
    time_str:
        The XMLTV timestamp string.
    source_tz:
        IANA timezone name used when no offset is present (e.g. ``"Europe/London"``).
    target_tz:
        IANA timezone name for the output (e.g. ``"America/New_York"``).

    Returns
    -------
    str
        The converted timestamp formatted for XMLTV.

    Raises
    ------
    ValueError
        If *time_str* cannot be parsed.
    """
    time_str = time_str.strip()
    match = _XMLTV_TIME_RE.match(time_str)
    if not match:
        raise ValueError(f"Invalid XMLTV time format: {time_str!r}")

    dt_part = match.group(1)
    offset_part = match.group(2)

    # Parse the base datetime (naive)
    naive_dt = datetime.strptime(dt_part, "%Y%m%d%H%M%S")

    if offset_part:
        # Parse the explicit offset: +HHMM or -HHMM
        sign = 1 if offset_part[0] == "+" else -1
        offset_hours = int(offset_part[1:3])
        offset_minutes = int(offset_part[3:5])
        total_offset = timedelta(hours=offset_hours, minutes=offset_minutes) * sign
        aware_dt = naive_dt.replace(tzinfo=timezone(total_offset))
    else:
        # No offset -- interpret as source timezone
        source_zone = ZoneInfo(source_tz)
        aware_dt = naive_dt.replace(tzinfo=source_zone)

    # Convert to target timezone
    target_zone = ZoneInfo(target_tz)
    converted = aware_dt.astimezone(target_zone)

    return converted.strftime("%Y%m%d%H%M%S %z")


def localize_xmltv(
    xmltv_content: str,
    source_tz: str,
    target_tz: str,
) -> str:
    """Convert all programme start/stop times in an XMLTV document.

    Parses the XMLTV content with lxml, iterates over every ``<programme>``
    element, and converts the ``start`` and ``stop`` attributes from
    *source_tz* to *target_tz*.

    Parameters
    ----------
    xmltv_content:
        The full XMLTV XML document as a string.
    source_tz:
        IANA timezone for timestamps lacking an explicit offset.
    target_tz:
        IANA timezone for the output timestamps.

    Returns
    -------
    str
        The full XMLTV document with converted timestamps, including an
        XML declaration.
    """
    parser = etree.XMLParser(resolve_entities=False, no_network=True, dtd_validation=False)
    root = etree.fromstring(xmltv_content.encode("utf-8"), parser=parser)
    programmes = root.findall(".//programme")
    converted_count = 0

    for prog in programmes:
        start = prog.get("start")
        stop = prog.get("stop")

        if start:
            try:
                prog.set("start", convert_xmltv_time(start, source_tz, target_tz))
            except ValueError:
                logger.warning("Could not convert start time %r", start)

        if stop:
            try:
                prog.set("stop", convert_xmltv_time(stop, source_tz, target_tz))
            except ValueError:
                logger.warning("Could not convert stop time %r", stop)

        converted_count += 1

    logger.info(
        "Localized %d programmes from %s to %s",
        converted_count,
        source_tz,
        target_tz,
    )

    return etree.tostring(
        root,
        pretty_print=True,
        xml_declaration=True,
        encoding="UTF-8",
    ).decode("utf-8")
