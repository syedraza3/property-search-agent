"""
Property Search Agent
Searches Rightmove weekly for 3-bed houses with large gardens
in New Malden (KT3), Worcester Park (KT4), and Wallington (SM6)
under £500,000 and sends a digest via email or ntfy.sh
"""

import requests
import json
import os
import smtplib
import hashlib
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from bs4 import BeautifulSoup

# ── Configuration ─────────────────────────────────────────────────────────────

AREAS = [
    {"name": "New Malden",    "outcode": "KT3"},
    {"name": "Worcester Park","outcode": "KT4"},
    {"name": "Wallington",    "outcode": "SM6"},
]

MAX_PRICE    = 500000
MIN_BEDS     = 3
MAX_BEDS     = 3

# Keywords that suggest a large garden in the listing description
GARDEN_KEYWORDS = [
    "200ft", "150ft", "100ft", "large garden", "huge garden",
    "extensive garden", "long garden", "south facing garden",
    "generous garden", "mature garden", "wrap around garden",
    "80ft", "90ft", "120ft", "130ft", "140ft", "160ft",
]

# Notification method: "email" or "ntfy"
NOTIFY_VIA = os.environ.get("NOTIFY_VIA", "ntfy")  # set in GitHub Actions secrets

# ntfy.sh config (set NTFY_TOPIC in GitHub Actions secrets)
NTFY_TOPIC  = os.environ.get("NTFY_TOPIC", "your-topic-here")
NTFY_SERVER = "https://ntfy.sh"

# Email config (only needed if NOTIFY_VIA=email)
EMAIL_FROM    = os.environ.get("EMAIL_FROM", "")
EMAIL_TO      = os.environ.get("EMAIL_TO", "")
EMAIL_PASS    = os.environ.get("EMAIL_PASS", "")
SMTP_HOST     = "smtp.gmail.com"
SMTP_PORT     = 587

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

def rightmove_location_id(outcode: str) -> str | None:
    """Resolve an outcode to a Rightmove location identifier."""
    url = "https://www.rightmove.co.uk/typeAhead/uknostreet/suggest"
    params = {"term": outcode, "maxResults": 5}
    try:
        r = requests.get(url, params=params, headers=HEADERS, timeout=10)
        data = r.json()
        for item in data.get("typeAheadLocations", []):
            if item.get("locationType") == "OUTCODE":
                return item["locationIdentifier"]
    except Exception as e:
        print(f"[WARN] Could not resolve location ID for {outcode}: {e}")
    return None


def fetch_listings(outcode: str) -> list[dict]:
    """Fetch 3-bed houses for sale under £500k from Rightmove for a given outcode."""
    location_id = rightmove_location_id(outcode)
    if not location_id:
        print(f"[WARN] Skipping {outcode} — could not resolve location.")
        return []

    url = "https://www.rightmove.co.uk/api/_search"
    params = {
        "locationIdentifier": location_id,
        "minBedrooms": MIN_BEDS,
        "maxBedrooms": MAX_BEDS,
        "maxPrice": MAX_PRICE,
        "propertyTypes": "detached,semi-detached,terraced",
        "mustHave": "",
        "dontShow": "retirement,sharedOwnership",
        "furnishTypes": "",
        "keywords": "",
        "sortType": "2",        # newest first
        "index": 0,
        "propertySubType": "",
        "numberOfPropertiesPerPage": 48,
        "radius": "0.0",
        "channel": "BUY",
        "currencyCode": "GBP",
        "isFetching": "false",
    }

    try:
        r = requests.get(url, params=params, headers=HEADERS, timeout=15)
        data = r.json()
        return data.get("properties", [])
    except Exception as e:
        print(f"[ERROR] Failed to fetch listings for {outcode}: {e}")
        return []


# ── Garden Detection ──────────────────────────────────────────────────────────

def has_large_garden(listing: dict) -> bool:
    """Return True if the listing description mentions a large garden."""
    text = " ".join([
        listing.get("summary", ""),
        listing.get("displayAddress", ""),
        " ".join(listing.get("keyFeatures", [])),
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
    garden_features = [f for f in features if any(
        kw.lower() in f.lower() for kw in GARDEN_KEYWORDS
    )]

    lines = [
        f"🏡 {address} ({area_name})",
        f"   {beds} bed {prop_type} — {price}",
    ]
    if garden_features:
        lines.append(f"   🌿 {' | '.join(garden_features[:2])}")
    if added:
        lines.append(f"   📅 Listed: {added}")
    lines.append(f"   🔗 {url}")
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


def send_email(subject: str, body: str):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = EMAIL_FROM
    msg["To"]      = EMAIL_TO
    msg.attach(MIMEText(body, "plain"))
    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as s:
            s.starttls()
            s.login(EMAIL_FROM, EMAIL_PASS)
            s.sendmail(EMAIL_FROM, EMAIL_TO, msg.as_string())
        print("[OK] Email sent.")
    except Exception as e:
        print(f"[ERROR] Email send failed: {e}")


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
    title    = f"🏡 Property Digest — {date_str} ({len(new_listings)} new listings)"
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

    if NOTIFY_VIA == "email":
        send_email(title, body)
    elif NOTIFY_VIA == "ntfy":
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
