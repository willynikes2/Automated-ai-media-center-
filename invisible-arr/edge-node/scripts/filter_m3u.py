#!/usr/bin/env python3
"""Filter a large M3U file into a proper cable-like lineup for a given zip code.

Usage:
    python3 filter_m3u.py input.m3u output.m3u

Keeps:
  - Dayton OH local channels (mapped to correct channel numbers)
  - USA Entertainment, News, Sports, Movies, Family & Kids, Documentary, Music
  - All USA sports packages (NFL, NBA, MLB, NHL, NCAA, etc.)
  - PPV channels
  - Adult channels

Drops:
  - All non-US channels/groups
  - All non-Dayton local channels
  - Latin/Spanish channels (separate from main lineup)
  - Religion, STIRR TV
  - Series/VOD content (we only want live channels)
"""

import re
import sys
from collections import defaultdict

# ═══════════════════════════════════════════════════════════════
# DAYTON OH (45406) LOCAL CHANNEL MAP
# Real OTA channel numbers for the Dayton DMA
# ═══════════════════════════════════════════════════════════════

DAYTON_LOCALS = {
    "WDTN":  {"number": 2,  "network": "NBC", "name": "WDTN 2 (NBC) Dayton"},
    "WHIO":  {"number": 7,  "network": "CBS", "name": "WHIO 7 (CBS) Dayton"},
    "WPTD":  {"number": 16, "network": "PBS", "name": "WPTD 16 (PBS) Dayton"},
    "WKEF":  {"number": 22, "network": "ABC", "name": "WKEF 22 (ABC) Dayton"},
    "WBDT":  {"number": 26, "network": "CW",  "name": "WBDT 26 (CW) Dayton"},
    "WRGT":  {"number": 45, "network": "FOX", "name": "WRGT 45 (FOX) Dayton"},
}

# Groups containing local channels from every city — we only keep Dayton
LOCAL_GROUPS = {
    "USA Local - ABC",
    "USA Local - CBS",
    "USA Local - NBC",
    "USA Local - FOX",
    "USA Local - MISC",
    "USA Local Channels ( Full List )",
}

# ═══════════════════════════════════════════════════════════════
# CABLE LINEUP GROUPS TO KEEP
# Maps source group → output group name for clean organization
# ═══════════════════════════════════════════════════════════════

KEEP_GROUPS = {
    # Entertainment
    "USA Entertainment":       "Entertainment",
    "USA Family & Kids":       "Family & Kids",
    "USA Documentary":         "Documentary",
    "USA Music":               "Music",
    "USA News":                "News",
    "USA Peacock Network":     "Entertainment",

    # Sports
    "USA Sports":              "Sports",
    "USA FanDuel Sports":      "Sports",
    "USA NBC Sports":          "Sports",
    "USA Bein Sports":         "Sports",
    "USA NFL - Sunday Ticket": "NFL Sunday Ticket",
    "USA MLB":                 "MLB",
    "USA MILB":                "MiLB",
    "USA NBA":                 "NBA",
    "USA WNBA":                "WNBA",
    "USA NHL":                 "NHL",
    "USA NCAAF":               "NCAA Football",
    "USA SEC+ ACC EXTRA":      "NCAA",

    # Movies
    "USA Movies Channels":     "Movies",
    "USA PPV Cinema":          "PPV Movies",

    # PPV
    "Pay Per View Events":     "PPV Events",
    "PPV-MMA/BOXING/WWE/UFC":  "PPV Fighting",
    "PPV FLOSPORTS":           "PPV FloSports",

    # Adult — disabled by default
    # "Adults":                  "Adult",
    # "Adults (18+)":            "Adult",
    # "Adults 24-7":             "Adult",
    # "24/7 Adult":              "Adult",
    # "VOD Adults":              "Adult VOD",
    # "Private (18+) Vods":      "Adult VOD",
}


def is_dayton_channel(name: str) -> bool:
    """Check if channel name references Dayton (not Daytona) or a Dayton call sign."""
    upper = name.upper()
    if re.search(r"DAYTON(?!A)", upper):
        return True
    for call in DAYTON_LOCALS:
        if call in upper:
            return True
    return False


def relabel_dayton(name: str) -> tuple[str, int | None]:
    """Return a clean label and channel number for Dayton locals."""
    upper = name.upper()
    for call, info in DAYTON_LOCALS.items():
        if call in upper:
            return info["name"], info["number"]
    return name, None


def main():
    if len(sys.argv) != 3:
        print(f"Usage: {sys.argv[0]} input.m3u output.m3u", file=sys.stderr)
        sys.exit(1)

    input_path, output_path = sys.argv[1], sys.argv[2]

    kept = 0
    skipped = 0
    dayton_count = 0
    group_counts: dict[str, int] = defaultdict(int)

    with open(input_path, "r", errors="replace") as fin, open(output_path, "w") as fout:
        fout.write("#EXTM3U\n")

        extinf_line = None
        for line in fin:
            line = line.rstrip("\n\r")

            if line.startswith("#EXTM3U"):
                continue
            if line.startswith("#EXT-X-SESSION-DATA"):
                continue

            if line.startswith("#EXTINF"):
                extinf_line = line
                continue

            if extinf_line and line and not line.startswith("#"):
                stream_url = line

                # Extract group-title
                group_match = re.search(r'group-title="([^"]*)"', extinf_line)
                group = group_match.group(1) if group_match else ""

                # ── Local channels: only keep Dayton ──
                if group in LOCAL_GROUPS:
                    name_match = re.search(r'tvg-name="([^"]*)"', extinf_line)
                    ch_name = name_match.group(1) if name_match else ""

                    if not is_dayton_channel(ch_name):
                        skipped += 1
                        extinf_line = None
                        continue

                    # Relabel with proper name + channel number
                    new_name, ch_num = relabel_dayton(ch_name)
                    dayton_count += 1

                    extinf_line = re.sub(
                        r'tvg-name="[^"]*"',
                        f'tvg-name="{new_name}"',
                        extinf_line,
                    )
                    extinf_line = re.sub(
                        r'group-title="[^"]*"',
                        'group-title="Local"',
                        extinf_line,
                    )
                    if ch_num and "tvg-chno=" not in extinf_line:
                        extinf_line = extinf_line.replace(
                            "tvg-name=",
                            f'tvg-chno="{ch_num}" tvg-name=',
                        )
                    extinf_line = re.sub(r',([^,]*)$', f',{new_name}', extinf_line)

                    fout.write(extinf_line + "\n")
                    fout.write(stream_url + "\n")
                    group_counts["Local"] += 1
                    kept += 1
                    extinf_line = None
                    continue

                # ── Cable lineup groups ──
                if group in KEEP_GROUPS:
                    output_group = KEEP_GROUPS[group]

                    # Discard logos that are too long (base64 data URIs)
                    logo_match = re.search(r'tvg-logo="([^"]*)"', extinf_line)
                    if logo_match and len(logo_match.group(1)) > 2000:
                        extinf_line = re.sub(r'tvg-logo="[^"]*"', 'tvg-logo=""', extinf_line)

                    # Remap group name
                    extinf_line = re.sub(
                        r'group-title="[^"]*"',
                        f'group-title="{output_group}"',
                        extinf_line,
                    )

                    fout.write(extinf_line + "\n")
                    fout.write(stream_url + "\n")
                    group_counts[output_group] += 1
                    kept += 1
                    extinf_line = None
                    continue

                # Everything else is skipped
                skipped += 1
                extinf_line = None
            elif line.startswith("#"):
                extinf_line = None

    # Summary
    print(f"\n{'='*50}")
    print(f"  CABLE LINEUP SUMMARY — Dayton OH (45406)")
    print(f"{'='*50}")
    print(f"  Total channels: {kept}")
    print(f"  Skipped:        {skipped}")
    print()
    for group, count in sorted(group_counts.items(), key=lambda x: (-x[1], x[0])):
        print(f"  {group:<25} {count:>5} channels")
    print(f"{'='*50}\n")


if __name__ == "__main__":
    main()
