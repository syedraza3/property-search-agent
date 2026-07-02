"""
M&S Price Checker
Fetches the current price of the M&S Skinny Fit 360 Flex Stretch Jeans
and sends an ntfy.sh notification if the price has changed since the last run.
"""

import json
import os
import re
import sys
from datetime import datetime, timezone

import requests

# ── Configuration ─────────────────────────────────────────────────────────────

PRODUCT_URL = (
    "https://www.marksandspencer.com/skinny-fit-360-flex-stretch-jeans"
    "/p/clp60685466?color=BLUE%2FBLACK"
)
PRODUCT_NAME = "M&S Skinny Fit 360 Flex Stretch Jeans (Blue/Black)"

NTFY_TOPIC  = os.environ.get("NTFY_TOPIC", "your-topic-here")
NTFY_SERVER = "https://ntfy.sh"

PRICE_CACHE_FILE = "last_price.json"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-GB,en;q=0.9",
}

# ── Price Fetching ────────────────────────────────────────────────────────────

def fetch_price() -> tuple[str, str] | None:
    """
    Returns (price_str, currency) e.g. ("49.00", "GBP"), or None on failure.
    Parses the structured data embedded in the page as application/ld+json.
    """
    try:
        r = requests.get(PRODUCT_URL, headers=HEADERS, timeout=20)
        r.raise_for_status()
    except Exception as e:
        print(f"[ERROR] Could not fetch page: {e}")
        return None

    # Find all application/ld+json blocks and look for the Product schema
    scripts = re.findall(
        r'<script type="application/ld\+json"[^>]*>(.*?)</script>',
        r.text,
        re.S,
    )
    for raw in scripts:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if data.get("@type") != "Product":
            continue
        spec = (
            data.get("offers", {})
                .get("priceSpecification", {})
        )
        price = spec.get("price") or spec.get("minPrice")
        currency = spec.get("priceCurrency", "GBP")
        if price:
            return str(price), currency

    print("[ERROR] Could not find Product price in page JSON-LD.")
    return None


# ── Price Cache ───────────────────────────────────────────────────────────────

def load_last_price() -> dict | None:
    if os.path.exists(PRICE_CACHE_FILE):
        with open(PRICE_CACHE_FILE) as f:
            return json.load(f)
    return None


def save_price(price: str, currency: str):
    with open(PRICE_CACHE_FILE, "w") as f:
        json.dump(
            {
                "price": price,
                "currency": currency,
                "checked_at": datetime.now(timezone.utc).isoformat(),
            },
            f,
        )


# ── Notification ──────────────────────────────────────────────────────────────

def format_currency(price: str, currency: str) -> str:
    symbols = {"GBP": "£", "EUR": "€", "USD": "$"}
    symbol = symbols.get(currency, currency + " ")
    return f"{symbol}{float(price):.2f}"


def send_ntfy(title: str, message: str):
    ascii_title = title.encode("ascii", "ignore").decode().strip()
    try:
        requests.post(
            f"{NTFY_SERVER}/{NTFY_TOPIC}",
            data=message.encode("utf-8"),
            headers={
                "Title": ascii_title,
                "Priority": "high",
                "Tags": "shopping,jeans",
            },
            timeout=10,
        )
        print("[OK] ntfy notification sent.")
    except Exception as e:
        print(f"[ERROR] ntfy send failed: {e}")


# ── Main ──────────────────────────────────────────────────────────────────────

def run():
    print(f"\n{'='*60}")
    print(f"M&S Price Checker — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')} UTC")
    print(f"{'='*60}\n")

    result = fetch_price()
    if result is None:
        print("Price check failed — skipping.")
        sys.exit(1)

    current_price, currency = result
    current_display = format_currency(current_price, currency)
    print(f"Current price: {current_display}")

    last = load_last_price()
    save_price(current_price, currency)

    if last is None:
        print("No previous price on record — saving baseline.")
        print(f"Baseline set: {current_display}")
        return

    last_price = last["price"]
    last_display = format_currency(last_price, currency)
    print(f"Previous price: {last_display}")

    if current_price == last_price:
        print("Price unchanged — no notification sent.")
        return

    # Price has changed
    try:
        diff = float(current_price) - float(last_price)
    except ValueError:
        diff = 0

    direction = "dropped" if diff < 0 else "increased"
    change = format_currency(str(abs(diff)), currency)

    title = f"M&S price {direction}: {current_display}"
    message = (
        f"{PRODUCT_NAME}\n"
        f"Price {direction} by {change}\n"
        f"{last_display} -> {current_display}\n"
        f"{PRODUCT_URL}"
    )

    print(f"\n*** PRICE CHANGE DETECTED ***")
    print(message)
    send_ntfy(title, message)


if __name__ == "__main__":
    run()
