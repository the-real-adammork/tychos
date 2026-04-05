#!/usr/bin/env python3
"""
Parse NASA Five Millennium Canon eclipse catalogs into JSON.

Fetches solar and lunar eclipse catalog pages from NASA's website,
strips HTML, extracts eclipse records by token position, and writes JSON.

Usage:
    python scripts/parse_nasa_eclipses.py

Output:
    tests/data/solar_eclipses.json
    tests/data/lunar_eclipses.json
"""

import json
import re
import urllib.request
from pathlib import Path

# --- Known valid values ---

MONTHS = {
    "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
    "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12,
}

SOLAR_TYPES = {
    "T": "total", "T+": "total", "T-": "total", "Tm": "total", "Ts": "total",
    "A": "annular", "A+": "annular", "A-": "annular", "An": "annular",
    "Am": "annular", "As": "annular",
    "P": "partial", "Pe": "partial", "Pb": "partial",
    "H": "hybrid", "H2": "hybrid", "H3": "hybrid", "Hm": "hybrid",
}

LUNAR_TYPES = {
    "T": "total", "T+": "total", "T-": "total",
    "P": "partial",
    "N": "penumbral", "Nx": "penumbral", "Ne": "penumbral", "Nb": "penumbral",
}

# Century pages to fetch
SOLAR_URLS = [
    "https://eclipse.gsfc.nasa.gov/SEcat5/SE1901-2000.html",
    "https://eclipse.gsfc.nasa.gov/SEcat5/SE2001-2100.html",
]

LUNAR_URLS = [
    "https://eclipse.gsfc.nasa.gov/LEcat5/LE1901-2000.html",
    "https://eclipse.gsfc.nasa.gov/LEcat5/LE2001-2100.html",
]


def strip_html(text):
    """Remove HTML tags."""
    return re.sub(r'<[^>]+>', '', text)


def date_to_julian_day_tt(year, month, day, hour, minute, second):
    """Convert calendar date to Julian Day (TT)."""
    if month <= 2:
        year -= 1
        month += 12
    A = int(year / 100)
    B = 2 - A + int(A / 4)
    jd = (int(365.25 * (year + 4716)) + int(30.6001 * (month + 1)) +
          day + B - 1524.5)
    jd += (hour + minute / 60.0 + second / 3600.0) / 24.0
    return jd


def parse_time(time_str):
    """Parse 'HH:MM:SS' into (hour, minute, second)."""
    parts = time_str.split(':')
    if len(parts) != 3:
        return None
    return int(parts[0]), int(parts[1]), int(parts[2])


def parse_solar_tokens(tokens):
    """Parse a solar eclipse record from whitespace-split tokens.

    Expected token layout:
        [0]  catalog_number   e.g. "09511"
        [1]  year             e.g. "2001"
        [2]  month            e.g. "Jun"
        [3]  day              e.g. "21"
        [4]  time             e.g. "12:04:46"
        [5]  delta_t          e.g. "64"
        [6]  luna_num         e.g. "18"
        [7]  saros_num        e.g. "127"
        [8]  eclipse_type     e.g. "T"
        [9]  qle              e.g. "-p"
        [10] gamma            e.g. "-0.5701"
        [11] magnitude        e.g. "1.0495"
        [12+] lat, long, alt, width, duration (variable)
    """
    if len(tokens) < 12:
        return None

    # Validate catalog number (5 digits)
    if not tokens[0].isdigit() or len(tokens[0]) != 5:
        return None

    # Year
    try:
        year = int(tokens[1])
    except ValueError:
        return None

    # Month
    month = MONTHS.get(tokens[2])
    if month is None:
        return None

    # Day
    try:
        day = int(tokens[3])
    except ValueError:
        return None

    # Time
    time = parse_time(tokens[4])
    if time is None:
        return None
    hour, minute, second = time

    # Eclipse type — must be in our enumerated set
    type_raw = tokens[8]
    if type_raw not in SOLAR_TYPES:
        print(f"  WARNING: unknown solar eclipse type '{type_raw}' in record {tokens[0]}, skipping")
        return None
    eclipse_type = SOLAR_TYPES[type_raw]

    # Magnitude
    try:
        magnitude = float(tokens[11])
    except ValueError:
        return None

    jd = date_to_julian_day_tt(year, month, day, hour, minute, second)
    date_str = f"{year:04d}-{month:02d}-{day:02d}T{hour:02d}:{minute:02d}:{second:02d}"

    return {
        "julian_day_tt": round(jd, 6),
        "date": date_str,
        "type": eclipse_type,
        "magnitude": magnitude,
    }


def parse_lunar_tokens(tokens):
    """Parse a lunar eclipse record from whitespace-split tokens.

    Expected token layout:
        [0]  catalog_number   e.g. "09651"
        [1]  year             e.g. "2001"
        [2]  month            e.g. "Jan"
        [3]  day              e.g. "09"
        [4]  time             e.g. "20:21:40"
        [5]  delta_t          e.g. "64"
        [6]  luna_num         e.g. "12"
        [7]  saros_num        e.g. "134"
        [8]  eclipse_type     e.g. "T" or "T+" or "P" or "N"
        [9]  qse              e.g. "p-"
        [10] gamma            e.g. "0.3720"
        [11] pen_magnitude    e.g. "2.1618"
        [12] um_magnitude     e.g. "1.1889"
        [13+] durations, lat, long (variable)
    """
    if len(tokens) < 13:
        return None

    # Validate catalog number
    if not tokens[0].isdigit() or len(tokens[0]) != 5:
        return None

    # Year
    try:
        year = int(tokens[1])
    except ValueError:
        return None

    # Month
    month = MONTHS.get(tokens[2])
    if month is None:
        return None

    # Day
    try:
        day = int(tokens[3])
    except ValueError:
        return None

    # Time
    time = parse_time(tokens[4])
    if time is None:
        return None
    hour, minute, second = time

    # Eclipse type
    type_raw = tokens[8]
    if type_raw not in LUNAR_TYPES:
        print(f"  WARNING: unknown lunar eclipse type '{type_raw}' in record {tokens[0]}, skipping")
        return None
    eclipse_type = LUNAR_TYPES[type_raw]

    # Penumbral magnitude
    try:
        magnitude = float(tokens[11])
    except ValueError:
        return None

    jd = date_to_julian_day_tt(year, month, day, hour, minute, second)
    date_str = f"{year:04d}-{month:02d}-{day:02d}T{hour:02d}:{minute:02d}:{second:02d}"

    return {
        "julian_day_tt": round(jd, 6),
        "date": date_str,
        "type": eclipse_type,
        "magnitude": magnitude,
    }


def fetch_and_parse(urls, token_parser):
    """Fetch catalog pages and parse all eclipse records."""
    results = []
    for url in urls:
        print(f"Fetching: {url}")
        data = urllib.request.urlopen(url).read().decode('utf-8', errors='replace')
        pres = re.findall(r'<pre>(.*?)</pre>', data, re.DOTALL)
        for pre in pres:
            text = strip_html(pre)
            for line in text.split('\n'):
                line = line.strip()
                if not line:
                    continue
                tokens = line.split()
                record = token_parser(tokens)
                if record:
                    results.append(record)
    return results


def main():
    repo_root = Path(__file__).resolve().parent.parent
    out_dir = repo_root / "tests" / "data"
    out_dir.mkdir(parents=True, exist_ok=True)

    # Solar eclipses
    solar = fetch_and_parse(SOLAR_URLS, parse_solar_tokens)
    solar.sort(key=lambda x: x["julian_day_tt"])
    out_path = out_dir / "solar_eclipses.json"
    with open(out_path, "w") as f:
        json.dump(solar, f, indent=2)
        f.write("\n")
    print(f"Solar: {len(solar)} eclipses -> {out_path}")

    # Lunar eclipses
    lunar = fetch_and_parse(LUNAR_URLS, parse_lunar_tokens)
    lunar.sort(key=lambda x: x["julian_day_tt"])
    out_path = out_dir / "lunar_eclipses.json"
    with open(out_path, "w") as f:
        json.dump(lunar, f, indent=2)
        f.write("\n")
    print(f"Lunar: {len(lunar)} eclipses -> {out_path}")


if __name__ == "__main__":
    main()
