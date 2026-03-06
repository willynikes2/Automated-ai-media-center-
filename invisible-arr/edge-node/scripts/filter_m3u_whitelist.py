#!/usr/bin/env python3
"""Filter M3U to a curated whitelist — clean cable-like lineup.

Usage:
    python3 filter_m3u_whitelist.py input.m3u output.m3u

Keeps ONLY channels matching the Dayton master list + extras (Sunday Ticket,
NBA TV, HBO, adult ~10, PPV). Deduplicates by picking the best stream per
channel. Orders: Dayton locals first, then cable groups.
"""

import re
import sys
from collections import defaultdict

# ═══════════════════════════════════════════════════════════════
# EXACT CHANNEL WHITELIST
# Maps: normalized pattern -> (output_name, output_group)
# Matching is done with word-boundary-aware substring search.
# ═══════════════════════════════════════════════════════════════

WHITELIST: list[tuple[str, str, str]] = [
    # (match_pattern, display_name, group)
    # --- LOCAL (Dayton) ---
    ("WDTN 2 (NBC) Dayton", "WDTN 2 (NBC)", "Local"),
    ("WHIO 7 (CBS) Dayton", "WHIO 7 (CBS)", "Local"),
    ("WKEF 22 (ABC) Dayton", "WKEF 22 (ABC)", "Local"),
    ("WRGT 45 (FOX) Dayton", "WRGT 45 (FOX)", "Local"),
    ("WBDT 26 (CW) Dayton", "WBDT 26 (CW)", "Local"),

    # --- NEWS ---
    ("USA CNN", "CNN", "News"),
    ("USA Fox News", "Fox News", "News"),
    ("USA CNBC", "CNBC", "News"),
    ("USA CNBC World", "CNBC World", "News"),
    ("USA HLN", "HLN", "News"),
    ("USA NewsNation", "NewsNation", "News"),
    ("USA NEWSMAX", "Newsmax", "News"),
    ("USA Bloomberg", "Bloomberg", "News"),
    ("USA C-SPAN", "C-SPAN", "News"),
    ("USA C-SPAN 2", "C-SPAN 2", "News"),
    ("USA CHEDDAR NEWS", "Cheddar News", "News"),
    ("USA The Weather Channel", "The Weather Channel", "News"),
    ("USA WeatherNation", "WeatherNation", "News"),
    ("USA Fox Business", "Fox Business", "News"),
    ("USA BBC World News", "BBC World News", "News"),
    ("USA CNN INTERNATIONAL", "CNN International", "News"),

    # --- SPORTS ---
    ("USA ESPN HD", "ESPN", "Sports"),
    ("USA ESPN 2", "ESPN2", "Sports"),
    ("USA ESPN NEWS", "ESPNews", "Sports"),
    ("USA ESPN U HD", "ESPNU", "Sports"),
    ("USA ESPN SEC Network", "SEC Network", "Sports"),
    ("USA ACC Network", "ACC Network", "Sports"),
    ("USA FOX SPORTS 1", "FS1", "Sports"),
    ("USA FOX SPORTS 2", "FS2", "Sports"),
    ("USA CBS Sports Network", "CBS Sports Network", "Sports"),
    ("USA Big Ten Network", "Big Ten Network", "Sports"),
    ("USA NFL Network", "NFL Network", "Sports"),
    ("USA NFL Redzone", "NFL RedZone", "Sports"),
    ("USA NBA TV", "NBA TV", "Sports"),
    ("USA MLB Network", "MLB Network", "Sports"),
    ("USA NHL Network", "NHL Network", "Sports"),
    ("USA NBC GOLF", "Golf Channel", "Sports"),
    ("USA Tennis Channel", "Tennis Channel", "Sports"),
    ("USA Outdoor Channel", "Outdoor Channel", "Sports"),
    ("USA SPORTSMAN CHANNEL", "Sportsman Channel", "Sports"),
    ("USA FanDuel TV", "FanDuel TV", "Sports"),
    ("USA Bally Sports SP Ohio", "Bally Sports Ohio", "Sports"),
    ("USA Bally SportsTime Ohio", "Bally SportsTime Ohio", "Sports"),

    # --- ENTERTAINMENT ---
    ("USA AMC", "AMC", "Entertainment"),  # will match "USA AMC" but not "USA AMC +"
    ("USA A&E", "A&E", "Entertainment"),
    ("USA Bravo East", "Bravo", "Entertainment"),
    ("USA Comedy Central", "Comedy Central", "Entertainment"),
    ("USA E! Entertainment", "E!", "Entertainment"),
    ("USA Freeform", "Freeform", "Entertainment"),
    ("USA FXX East", "FXX", "Entertainment"),
    ("USA FX East UHD", "FX", "Entertainment"),
    ("USA FX", "FX", "Entertainment"),
    ("USA Hallmark Channel", "Hallmark Channel", "Entertainment"),
    ("USA Hallmark Movies", "Hallmark Movies & Mysteries", "Entertainment"),
    ("USA IFC", "IFC", "Entertainment"),
    ("USA INSP", "INSP", "Entertainment"),
    ("USA Lifetime East", "Lifetime", "Entertainment"),
    ("USA Lifetime Movie", "Lifetime Movies", "Entertainment"),
    ("USA Paramount East", "Paramount Network", "Entertainment"),
    ("USA POP TV", "Pop TV", "Entertainment"),
    ("USA Reelz", "Reelz", "Entertainment"),
    ("USA Sundance", "SundanceTV", "Entertainment"),
    ("USA Syfy East", "Syfy", "Entertainment"),
    ("USA TBS", "TBS", "Entertainment"),
    ("USA TNT East", "TNT", "Entertainment"),
    ("USA truTV East", "truTV", "Entertainment"),
    ("USA USA Network East", "USA Network", "Entertainment"),
    ("USA We TV", "WE tv", "Entertainment"),
    ("USA Ovation", "Ovation", "Entertainment"),
    ("USA Oprah Winfrey Network", "OWN", "Entertainment"),
    ("USA TV Land", "TV Land", "Entertainment"),

    # --- FACTUAL / DOCUMENTARY ---
    ("USA Animal Planet East", "Animal Planet", "Documentary"),
    ("USA Destination America", "Destination America", "Documentary"),
    ("USA DISCOVERY CHANNEL", "Discovery Channel", "Documentary"),
    ("USA Investigation Discovery East", "Investigation Discovery", "Documentary"),
    ("USA Motor Trend", "MotorTrend", "Documentary"),
    ("USA Nat Geo East", "National Geographic", "Documentary"),
    ("USA Nat Geo Wild East", "Nat Geo Wild", "Documentary"),
    ("USA Science Channel", "Science Channel", "Documentary"),
    ("USA Smithsonian Channel", "Smithsonian Channel", "Documentary"),
    ("USA History Channel", "History", "Documentary"),
    ("USA TLC East", "TLC", "Documentary"),

    # --- LIFESTYLE ---
    ("USA Cooking Channel", "Cooking Channel", "Lifestyle"),
    ("USA Food Network", "Food Network", "Lifestyle"),
    ("USA FYI", "FYI", "Lifestyle"),
    ("USA HGTV East", "HGTV", "Lifestyle"),
    ("USA Magnolia", "Magnolia Network", "Lifestyle"),
    ("USA TRAVEL CHANNEL", "Travel Channel", "Lifestyle"),

    # --- KIDS / FAMILY ---
    ("USA Cartoon Network East", "Cartoon Network", "Kids & Family"),
    ("USA Disney Channel East", "Disney Channel", "Kids & Family"),
    ("USA Disney Junior East", "Disney Junior", "Kids & Family"),
    ("USA Disney XD", "Disney XD", "Kids & Family"),
    ("USA Nickelodeon", "Nickelodeon", "Kids & Family"),
    ("USA Nick Jr East", "Nick Jr.", "Kids & Family"),
    ("USA Boomerang", "Boomerang", "Kids & Family"),

    # --- MUSIC ---
    ("USA BET East", "BET", "Music"),
    ("USA CMT UHD", "CMT", "Music"),
    ("USA MTV East UHD", "MTV", "Music"),
    ("USA MTV 2", "MTV2", "Music"),
    ("USA MTV Classic", "MTV Classic", "Music"),
    ("USA VH1 UHD", "VH1", "Music"),

    # --- MOVIES / PREMIUM ---
    ("USA HBO East", "HBO", "Movies & Premium"),
    ("USA HBO West", "HBO West", "Movies & Premium"),
    ("USA HBO Comedy", "HBO Comedy", "Movies & Premium"),
    ("USA HBO Drama", "HBO Drama", "Movies & Premium"),
    ("USA HBO Hits East", "HBO Hits", "Movies & Premium"),
    ("USA HBO Movies", "HBO Movies", "Movies & Premium"),
    ("USA Cinemax East", "Cinemax", "Movies & Premium"),
    ("USA Cinemax Action", "Cinemax Action", "Movies & Premium"),
    ("USA Cinemax Hits East", "Cinemax Hits", "Movies & Premium"),
    ("USA StarZ East", "Starz", "Movies & Premium"),
    ("USA Starz West", "Starz West", "Movies & Premium"),
    ("USA Starz Encore East", "Starz Encore", "Movies & Premium"),
    ("USA Showtime", "Showtime", "Movies & Premium"),
    ("USA Showtime 2", "Showtime 2", "Movies & Premium"),
    ("USA Showtime Extreme", "Showtime Extreme", "Movies & Premium"),
    ("USA Paramount+ with SHOWTIME (East)", "Paramount+ w/ Showtime", "Movies & Premium"),
    ("USA EPIX", "Epix", "Movies & Premium"),
    ("USA MGM+ UHD", "MGM+", "Movies & Premium"),
    ("USA TCM", "TCM", "Movies & Premium"),
    ("USA THE MOVIE CHANNEL", "The Movie Channel", "Movies & Premium"),
]

# --- KEEP-ALL GROUPS (don't dedup, keep every numbered feed) ---
KEEP_ALL_PATTERNS: list[tuple[str, str]] = [
    # (pattern_prefix, group)
    ("USA NFL Sunday 7", "NFL Sunday Ticket"),  # NFL Sunday 705-717
    ("USA NFL Monday Night", "NFL Sunday Ticket"),
    ("USA NFL Thursday Night", "NFL Sunday Ticket"),
    ("USA NFL Sunday Night", "NFL Sunday Ticket"),
    ("USA NBA 0", "NBA"),
    ("Pay Per View", "PPV"),
    ("USA PPV0", "PPV"),
    ("USA UFC Channel", "PPV"),
    ("USA UFC Fight Pass", "PPV"),
    ("USA WWE NETWORK", "PPV"),
    ("USA Cinema 0", "PPV"),  # Cinema 01-03 PPV only, not "Cinemax"
]

# Group display order
GROUP_ORDER = [
    "Local", "News", "Sports", "Entertainment", "Documentary",
    "Lifestyle", "Kids & Family", "Music", "Movies & Premium",
    "NFL Sunday Ticket", "NBA", "PPV",
]


def quality_score(name: str) -> int:
    """Higher score = better quality. Used for dedup."""
    upper = name.upper()
    score = 0
    if "UHD" in upper or "4K" in upper:
        score += 100
    elif "FHD" in upper:
        score += 80
    elif " HD" in upper:
        score += 60
    elif "LHD" in upper:
        score += 40
    elif "SD" in upper:
        score -= 50
    if "EAST" in upper:
        score += 10
    if "BACKUP" in upper or "(BACKUP)" in upper:
        score -= 30
    return score


def main():
    if len(sys.argv) != 3:
        print(f"Usage: {sys.argv[0]} input.m3u output.m3u", file=sys.stderr)
        sys.exit(1)

    input_path, output_path = sys.argv[1], sys.argv[2]

    # Collect: key -> best (extinf, url, group, display_name)
    best_per_channel: dict[str, tuple[str, str, str, str, int]] = {}
    # key = display_name, value = (extinf, url, group, display_name, score)

    keep_all_entries: list[tuple[str, str, str]] = []
    # (extinf, url, group)

    with open(input_path, "r", errors="replace") as fin:
        extinf_line = None
        for line in fin:
            line = line.rstrip("\n\r")
            if line.startswith("#EXTM3U") or line.startswith("#EXT-X-SESSION-DATA"):
                continue
            if line.startswith("#EXTINF"):
                extinf_line = line
                continue

            if extinf_line and line and not line.startswith("#"):
                stream_url = line
                name_match = re.search(r'tvg-name="([^"]*)"', extinf_line)
                ch_name = name_match.group(1) if name_match else ""

                matched = False

                # Check exact whitelist FIRST (so Cinemax doesn't match "Cinema" PPV)
                for pattern, display_name, group in WHITELIST:
                    if ch_name == pattern or ch_name.startswith(pattern):
                        score = quality_score(ch_name)
                        existing = best_per_channel.get(display_name)
                        if existing is None or score > existing[4]:
                            best_per_channel[display_name] = (extinf_line, stream_url, group, display_name, score)
                        matched = True
                        break

                # Then check keep-all patterns (PPV, Sunday Ticket, NBA feeds)
                if not matched:
                    for pattern, group in KEEP_ALL_PATTERNS:
                        if ch_name.startswith(pattern) or ch_name.upper().startswith(pattern.upper()):
                            new_extinf = re.sub(r'group-title="[^"]*"', f'group-title="{group}"', extinf_line)
                            keep_all_entries.append((new_extinf, stream_url, group))
                            matched = True
                            break

                extinf_line = None
            elif line.startswith("#"):
                extinf_line = None

    # Build final list
    selected: list[tuple[str, str, str, str]] = []  # (extinf, url, group, sort_name)

    for display_name, (extinf, url, group, _, _) in best_per_channel.items():
        # Rewrite group-title and display name
        extinf = re.sub(r'group-title="[^"]*"', f'group-title="{group}"', extinf)
        # Rewrite the trailing display name after the last comma
        extinf = re.sub(r',([^,]*)$', f',{display_name}', extinf)
        selected.append((extinf, url, group, display_name))

    for extinf, url, group in keep_all_entries:
        name_match = re.search(r'tvg-name="([^"]*)"', extinf)
        sort_name = name_match.group(1) if name_match else ""
        selected.append((extinf, url, group, sort_name))

    # Sort by group order, then by name
    def sort_key(item):
        _, _, group, name = item
        try:
            g = GROUP_ORDER.index(group)
        except ValueError:
            g = 999
        return (g, name.lower())

    selected.sort(key=sort_key)

    # Write output
    with open(output_path, "w") as fout:
        fout.write("#EXTM3U\n")
        for extinf, url, _, _ in selected:
            fout.write(extinf + "\n")
            fout.write(url + "\n")

    # Summary
    group_counts: dict[str, int] = defaultdict(int)
    for _, _, group, _ in selected:
        group_counts[group] += 1

    print(f"\n{'='*50}")
    print(f"  CURATED LINEUP — Dayton OH (45402)")
    print(f"{'='*50}")
    print(f"  Total channels: {len(selected)}")
    print()
    for group in GROUP_ORDER:
        if group in group_counts:
            print(f"  {group:<25} {group_counts[group]:>5} channels")
    print(f"{'='*50}\n")


if __name__ == "__main__":
    main()
