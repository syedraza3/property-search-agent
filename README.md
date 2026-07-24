# Property Search Agent 🏡

Searches Rightmove **every day at 9pm** for 3-bed houses with large gardens in:
- **New Malden** (KT3)
- **Worcester Park** (KT4)
- **Wallington** (SM6)
- **Harrow** (HA2)

Filters: under £550,000 | large garden keywords | new listings only (deduplicates week-on-week)

Notifies via **ntfy.sh** (push to phone).

---

## Setup

### 1. Fork / create a new private GitHub repo and push this folder

```bash
git init
git add .
git commit -m "Initial property agent"
gh repo create property-agent --private --push --source=.
```

### 2. Add GitHub Actions secrets

Go to **Settings → Secrets and variables → Actions → New repository secret**

| Secret name  | Value |
|---|---|
| `NTFY_TOPIC` | Your ntfy.sh topic name (e.g. `syed-property-alerts`) |

### 3. Test it manually

Go to **Actions → Property Search → Run workflow** to trigger immediately without waiting for the schedule.

---

## Notification: ntfy.sh

1. Install the **ntfy** app on your phone (iOS or Android)
2. Subscribe to your topic name (e.g. `syed-property-alerts`)
3. Set `NTFY_TOPIC=syed-property-alerts` in GitHub Actions secrets

Done — you'll get a push notification with the week's new listings.

---

## Customisation

In `agent.py`, you can adjust:

| Variable | Default | Description |
|---|---|---|
| `MAX_PRICE` | `550000` | Max budget |
| `MIN_BEDS` / `MAX_BEDS` | `3` / `5` | Bedroom count |
| `GARDEN_KEYWORDS` | (list) | What counts as a "large garden" |
| `AREAS` | KT3, KT4, SM6, HA2 | Add/remove outcode areas |

To add another area (e.g. Sutton, SM1):
```python
{"name": "Sutton", "outcode": "SM1"},
```

---

## How it works

1. Fetches each outcode's search page from Rightmove (e.g. `/property-for-sale/KT3.html`)
2. Parses the embedded search results (Next.js `__NEXT_DATA__` JSON)
3. Paginates through all results, filtering for beds, price, and property type
4. Filters for listings mentioning large garden keywords in features/summary
5. Deduplicates against a cached `sent_listings.json` (persisted via GitHub Actions cache)
6. Sends a digest of **new** listings only via ntfy.sh — no repeat spam
