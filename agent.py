"""
Property Search Agent
Searches Rightmove weekly for 3-bed houses with large gardens
in New Malden (KT3), Worcester Park (KT4), and Wallington (SM6)
under £500,000 and sends a digest via ntfy.sh
"""

import requests
import json
import os
import hashlib
import re
from datetime import datetime
from urllib.parse import urlencode

# ── Configuration ─────────────────────────────────────────────────────────────

AREAS = [
    {"name": "New Malden",    "outcode": "KT3"},
    {"name": "Worcester Park","outcode": "KT4"},
    {"name": "Wallington",    "outcode": "SM6"},
    {"name": "Harrow",    "outcode": "HA2"},
]

MAX_PRICE    = 550000
MIN_BEDS     = 3
MAX_BEDS     = 5

# Keywords that suggest a large garden in the listing description
GARDEN_KEYWORDS = [
    "200ft", "150ft", "100ft", "large garden", "huge garden",
    "extensive garden", "long garden", "south facing garden",
    "generous garden", "mature garden", "wrap around garden",
    "80ft", "90ft", "120ft", "130ft", "140ft", "160ft",
]

# ntfy.sh config (set NTFY_TOPIC in GitHub Actions secrets)
NTFY_TOPIC  = os.environ.get("NTFY_TOPIC", "your-topic-here")
NTFY_SERVER = "https://ntfy.sh"

# Seen listings cache file (persists between runs via GitHub Actions cache)
SEEN_FILE = "seen_listings.json"

# ── Rightmove Search ──────────────────────────────────────────────────────────

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}

def _search_url(outcode: str, index: int = 0) -> str:
    params = {
        "minBedrooms": MIN_BEDS,
        "maxBedrooms": MAX_BEDS,
        "maxPrice": MAX_PRICE,
        "propertyTypes": "detached,semi-detached,terraced",
        "numberOfPropertiesPerPage": 24,
        "radius": "0.0",
        "sortType": 2,
        "channel": "BUY",
        "currencyCode": "GBP",
        "index": index,
    }
    return f"https://www.rightmove.co.uk/property-for-sale/{outcode}.html?{urlencode(params)}"


def _parse_next_data(html: str) -> dict:
    match = re.search(
        r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
        html,
        re.S,
    )
    if not match:
        raise ValueError("Rightmove page did not include __NEXT_DATA__")
    return json.loads(match.group(1))


def fetch_listings(outcode: str) -> list[dict]:
    """Fetch matching properties for sale from Rightmove for a given outcode."""
    listings: list[dict] = []
    seen_ids: set[str] = set()
    index = 0

    while True:
        url = _search_url(outcode, index)
        try:
            r = requests.get(url, headers=HEADERS, timeout=20)
            r.raise_for_status()
            data = _parse_next_data(r.text)
            search_results = data["props"]["pageProps"]["searchResults"]
        except Exception as e:
            print(f"[ERROR] Failed to fetch listings for {outcode} at index {index}: {e}")
            return listings

        page_listings = search_results.get("properties", [])
        for listing in page_listings:
            lid = listing_id(listing)
            if lid in seen_ids:
                continue
            seen_ids.add(lid)
            listings.append(listing)

        pagination = search_results.get("pagination", {})
        next_index = pagination.get("next")
        if not next_index:
            break
        index = int(next_index)

    return listings


# ── Garden Detection ──────────────────────────────────────────────────────────

def has_large_garden(listing: dict) -> bool:
    """Return True if the listing description mentions a large garden."""
    features = listing.get("keyFeatures", [])
    feature_text = []
    for feature in features:
        if isinstance(feature, str):
            feature_text.append(feature)
        elif isinstance(feature, dict):
            feature_text.append(
                feature.get("description")
                or feature.get("htmlDescription")
                or ""
            )
    text = " ".join([
        listing.get("summary", ""),
        listing.get("displayAddress", ""),
        " ".join(feature_text),
    ]).lower()
    return any(kw.lower() in text for kw in GARDEN_KEYWORDS)


def listing_id(listing: dict) -> str:
    return str(listing.get("id", hashlib.md5(
        listing.get("propertyUrl", "").encode()
    ).hexdigest()))


# ── Seen Cache ────────────────────────────────────────────────────────────────

def load_seen() -> set:
    if os.path.exists(SEEN_FILE):
        with open(SEEN_FILE) as f:
            return set(json.load(f))
    return set()


def save_seen(seen: set):
    with open(SEEN_FILE, "w") as f:
        json.dump(list(seen), f)


# ── Notification ──────────────────────────────────────────────────────────────

def format_listing(listing: dict, area_name: str) -> str:
    price    = f"£{listing.get('price', {}).get('amount', 0):,}"
    address  = listing.get("displayAddress", "Unknown address")
    url      = f"https://www.rightmove.co.uk{listing.get('propertyUrl', '')}"
    beds     = listing.get("bedrooms", "?")
    prop_type = listing.get("propertySubType", listing.get("propertyTypeFullDescription", ""))
    added    = listing.get("listingUpdate", {}).get("listingUpdateDate", "")[:10]
    features = listing.get("keyFeatures", [])
    garden_features = []
    for feature in features:
        text = ""
        if isinstance(feature, str):
            text = feature
        elif isinstance(feature, dict):
            text = feature.get("description") or feature.get("htmlDescription") or ""
        if text and any(kw.lower() in text.lower() for kw in GARDEN_KEYWORDS):
            garden_features.append(text)

    lines = [
        f"   {address} ({area_name})",
        f"   {beds} bed {prop_type} — {price}",
    ]
    if garden_features:
        lines.append(f"    {' | '.join(garden_features[:2])}")
    if added:
        lines.append(f"     Listed: {added}")
    lines.append(f"     {url}")
    return "\n".join(lines)


def send_ntfy(message: str, title: str):
    try:
        requests.post(
            f"{NTFY_SERVER}/{NTFY_TOPIC}",
            data=message.encode("utf-8"),
            headers={
                "Title": title,
                "Priority": "default",
                "Tags": "house,garden",
            },
            timeout=10,
        )
        print("[OK] ntfy notification sent.")
    except Exception as e:
        print(f"[ERROR] ntfy send failed: {e}")


# ── Main ──────────────────────────────────────────────────────────────────────

def run():
    print(f"\n{'='*60}")
    print(f"Property Agent — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*60}\n")

    seen = load_seen()
    new_listings = []

    for area in AREAS:
        print(f"Searching {area['name']} ({area['outcode']})...")
        listings = fetch_listings(area["outcode"])
        print(f"  Found {len(listings)} total listings")

        for listing in listings:
            lid = listing_id(listing)
            if lid in seen:
                continue
            if has_large_garden(listing):
                new_listings.append((listing, area["name"]))
                seen.add(lid)

        print(f"  {sum(1 for l, _ in new_listings if _ == area['name'])} new large-garden hits")

    save_seen(seen)

    if not new_listings:
        print("\nNo new large-garden listings found this week.")
        return

    # Build digest
    date_str = datetime.now().strftime("%d %b %Y")
    title    = f" Property Digest — {date_str} ({len(new_listings)} new listings)"
    header   = (
        f"New 3-bed houses with large gardens | Under £500k\n"
        f"Areas: New Malden, Worcester Park, Wallington (SM6)\n"
        f"{'─'*50}\n\n"
    )
    body = header + "\n\n".join(
        format_listing(l, area) for l, area in new_listings
    )

    print(f"\n{title}\n")
    print(body)

    # ntfy has a 4096 char limit — chunk if needed
    chunks = [new_listings[i:i+5] for i in range(0, len(new_listings), 5)]
    for i, chunk in enumerate(chunks, 1):
        chunk_body = header + "\n\n".join(
            format_listing(l, area) for l, area in chunk
        )
        chunk_title = f"{title} (part {i}/{len(chunks)})" if len(chunks) > 1 else title
        send_ntfy(chunk_body, chunk_title)


if __name__ == "__main__":
    run()
