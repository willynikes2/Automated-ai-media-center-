#!/usr/bin/env python3
"""Filter a large M3U file to US-only channels with Dayton local labeling.

Usage:
    python3 filter_m3u.py input.m3u output.m3u

Keeps only groups starting with "USA".
Renames Dayton-area local channels with proper call signs and channel numbers.
"""

import re
import sys

# Dayton OH (45406) local channel mappings
DAYTON_LOCALS = {
    "WDTN": {"number": 2, "network": "NBC", "name": "WDTN 2 (NBC) Dayton"},
    "WHIO": {"number": 7, "network": "CBS", "name": "WHIO 7 (CBS) Dayton"},
    "WPTD": {"number": 16, "network": "PBS", "name": "WPTD 16 (PBS) Dayton"},
    "WKEF": {"number": 22, "network": "ABC", "name": "WKEF 22 (ABC) Dayton"},
    "WBDT": {"number": 26, "network": "CW", "name": "WBDT 26 (CW) Dayton"},
    "WRGT": {"number": 45, "network": "FOX", "name": "WRGT 45 (FOX) Dayton"},
}

# Non-Dayton local channels to skip (we only want Dayton locals, not every city)
# We keep all USA non-local groups, but for local groups we only keep Dayton
LOCAL_GROUPS = {
    "USA Local - ABC",
    "USA Local - CBS",
    "USA Local - NBC",
    "USA Local - FOX",
    "USA Local - MISC",
    "USA Local Channels ( Full List )",
}


def is_dayton_channel(name: str) -> bool:
    """Check if channel name references Dayton (not Daytona) or a Dayton call sign."""
    upper = name.upper()
    # Match "DAYTON" but not "DAYTONA"
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
                # We have a complete channel (extinf + url)
                stream_url = line

                # Extract group-title
                group_match = re.search(r'group-title="([^"]*)"', extinf_line)
                group = group_match.group(1) if group_match else ""

                # Only keep USA groups
                if not group.startswith("USA"):
                    skipped += 1
                    extinf_line = None
                    continue

                # For local groups, only keep Dayton channels
                if group in LOCAL_GROUPS:
                    name_match = re.search(r'tvg-name="([^"]*)"', extinf_line)
                    ch_name = name_match.group(1) if name_match else ""

                    if not is_dayton_channel(ch_name):
                        skipped += 1
                        extinf_line = None
                        continue

                    # Relabel Dayton locals
                    new_name, ch_num = relabel_dayton(ch_name)
                    dayton_count += 1

                    # Rewrite the EXTINF line with proper label
                    extinf_line = re.sub(
                        r'tvg-name="[^"]*"',
                        f'tvg-name="{new_name}"',
                        extinf_line,
                    )
                    # Set group to "Dayton Local"
                    extinf_line = re.sub(
                        r'group-title="[^"]*"',
                        'group-title="Dayton Local"',
                        extinf_line,
                    )
                    # Add channel number
                    if ch_num and "tvg-chno=" not in extinf_line:
                        extinf_line = extinf_line.replace(
                            "tvg-name=",
                            f'tvg-chno="{ch_num}" tvg-name=',
                        )
                    # Update the display name at end of EXTINF line
                    extinf_line = re.sub(r',([^,]*)$', f',{new_name}', extinf_line)

                fout.write(extinf_line + "\n")
                fout.write(stream_url + "\n")
                kept += 1
                extinf_line = None
            elif line.startswith("#"):
                extinf_line = None

    print(f"Kept: {kept} channels ({dayton_count} Dayton locals)")
    print(f"Skipped: {skipped} non-US channels")


if __name__ == "__main__":
    main()
