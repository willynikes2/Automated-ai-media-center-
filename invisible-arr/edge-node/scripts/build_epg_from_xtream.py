#!/usr/bin/env python3
"""Build XMLTV EPG from Xtream Codes API for curated M3U channels.

Usage:
    python3 build_epg_from_xtream.py <m3u_file> <output_epg.xml>

Fetches EPG data from the Xtream Codes player_api for channels present
in the given M3U, then generates a standard XMLTV file.
"""

import base64
import json
import re
import sys
import time
from datetime import datetime, timezone
from urllib.parse import urlparse
from xml.etree.ElementTree import Element, SubElement, tostring
from xml.dom.minidom import parseString

import requests

# Xtream Codes credentials (extracted from M3U stream URLs)
XC_BASE = "http://kytv.xyz:80"
XC_USER = "capitalismandme@top"
XC_PASS = "0079122906"


def parse_m3u_channels(m3u_path: str) -> list[dict]:
    """Parse M3U and return list of {tvg_id, name, logo, stream_url, stream_id}."""
    channels = []
    with open(m3u_path, errors="replace") as f:
        extinf = None
        for line in f:
            line = line.strip()
            if line.startswith("#EXTINF"):
                extinf = line
            elif extinf and line and not line.startswith("#"):
                tvg_id = ""
                name = ""
                logo = ""
                m = re.search(r'tvg-id="([^"]*)"', extinf)
                if m:
                    tvg_id = m.group(1)
                m = re.search(r'tvg-name="([^"]*)"', extinf)
                if m:
                    name = m.group(1)
                m = re.search(r'tvg-logo="([^"]*)"', extinf)
                if m:
                    logo = m.group(1)
                # Display name after last comma
                comma = extinf.rfind(",")
                display_name = extinf[comma + 1:].strip() if comma != -1 else name

                # Extract stream_id from URL (e.g., .../175787.ts)
                stream_id = None
                url_match = re.search(r'/(\d+)\.\w+$', line)
                if url_match:
                    stream_id = int(url_match.group(1))

                channels.append({
                    "tvg_id": tvg_id,
                    "name": name,
                    "display_name": display_name,
                    "logo": logo,
                    "stream_url": line,
                    "stream_id": stream_id,
                })
                extinf = None
    return channels


def fetch_epg_for_stream(stream_id: int) -> list[dict]:
    """Fetch short EPG for a single stream via Xtream Codes API."""
    url = f"{XC_BASE}/player_api.php"
    params = {
        "username": XC_USER,
        "password": XC_PASS,
        "action": "get_short_epg",
        "stream_id": stream_id,
        "limit": 50,  # Get up to 50 upcoming programs
    }
    try:
        resp = requests.get(url, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        return data.get("epg_listings", [])
    except Exception as e:
        print(f"  Warning: failed to fetch EPG for stream {stream_id}: {e}", file=sys.stderr)
        return []


def decode_b64(s: str) -> str:
    """Decode base64-encoded string from Xtream API."""
    try:
        return base64.b64decode(s).decode("utf-8", errors="replace")
    except Exception:
        return s


def build_xmltv(channels: list[dict], epg_data: dict[str, list[dict]]) -> str:
    """Build XMLTV XML string from channels and EPG data."""
    tv = Element("tv", attrib={
        "generator-info-name": "CutDaCord EPG Builder",
        "generator-info-url": "https://app.cutdacord.app",
    })

    # Add channel elements
    seen_ids = set()
    for ch in channels:
        tvg_id = ch["tvg_id"]
        if not tvg_id or tvg_id in seen_ids:
            continue
        seen_ids.add(tvg_id)

        channel_el = SubElement(tv, "channel", id=tvg_id)
        display = SubElement(channel_el, "display-name")
        display.text = ch["display_name"] or ch["name"]
        if ch["logo"]:
            icon = SubElement(channel_el, "icon", src=ch["logo"])

    # Add programme elements
    for tvg_id, listings in epg_data.items():
        for prog in listings:
            start_ts = prog.get("start_timestamp")
            stop_ts = prog.get("stop_timestamp")
            if not start_ts or not stop_ts:
                continue

            start_dt = datetime.fromtimestamp(int(start_ts), tz=timezone.utc)
            stop_dt = datetime.fromtimestamp(int(stop_ts), tz=timezone.utc)

            start_str = start_dt.strftime("%Y%m%d%H%M%S +0000")
            stop_str = stop_dt.strftime("%Y%m%d%H%M%S +0000")

            prog_el = SubElement(tv, "programme", attrib={
                "start": start_str,
                "stop": stop_str,
                "channel": tvg_id,
            })

            title_el = SubElement(prog_el, "title", lang="en")
            title_el.text = decode_b64(prog.get("title", ""))

            desc_text = decode_b64(prog.get("description", ""))
            if desc_text:
                desc_el = SubElement(prog_el, "desc", lang="en")
                desc_el.text = desc_text

    raw_xml = tostring(tv, encoding="unicode")
    # Pretty print
    dom = parseString(f'<?xml version="1.0" encoding="UTF-8"?>\n{raw_xml}')
    return dom.toprettyxml(indent="  ", encoding=None)


def main():
    if len(sys.argv) != 3:
        print(f"Usage: {sys.argv[0]} <m3u_file> <output.xml>", file=sys.stderr)
        sys.exit(1)

    m3u_path, output_path = sys.argv[1], sys.argv[2]

    print("Parsing M3U...")
    channels = parse_m3u_channels(m3u_path)
    print(f"  Found {len(channels)} channels")

    # Deduplicate by tvg_id, keeping the one with stream_id
    unique_channels: dict[str, dict] = {}
    for ch in channels:
        tvg_id = ch["tvg_id"]
        if not tvg_id:
            continue
        if tvg_id not in unique_channels or (ch["stream_id"] and not unique_channels[tvg_id].get("stream_id")):
            unique_channels[tvg_id] = ch

    print(f"  Unique tvg-ids with stream IDs: {len(unique_channels)}")

    # Fetch EPG for each unique channel
    epg_data: dict[str, list[dict]] = {}
    total = len(unique_channels)
    for i, (tvg_id, ch) in enumerate(unique_channels.items(), 1):
        stream_id = ch.get("stream_id")
        if not stream_id:
            continue
        print(f"  [{i}/{total}] Fetching EPG for {ch['display_name']} (stream {stream_id})...")
        listings = fetch_epg_for_stream(stream_id)
        if listings:
            epg_data[tvg_id] = listings
        # Small delay to avoid hammering the API
        if i < total:
            time.sleep(0.1)

    print(f"\nGot EPG data for {len(epg_data)}/{total} channels")

    # Count total programs
    total_programs = sum(len(v) for v in epg_data.values())
    print(f"Total program entries: {total_programs}")

    # Build XMLTV
    print("Building XMLTV...")
    xmltv = build_xmltv(channels, epg_data)

    with open(output_path, "w") as f:
        f.write(xmltv)

    print(f"Wrote EPG to {output_path}")


if __name__ == "__main__":
    main()
