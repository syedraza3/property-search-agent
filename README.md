# Property Search Agent 🏡

Searches Rightmove **every Monday at 8am** for 3-bed houses with large gardens in:
- **New Malden** (KT3)
- **Worcester Park** (KT4)
- **Wallington** (SM6)

Filters: under £500,000 | large garden keywords | new listings only (deduplicates week-on-week)

Notifies via **ntfy.sh** (push to phone) or **email**.

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
| `NOTIFY_VIA` | `ntfy` or `email` |
| `NTFY_TOPIC` | Your ntfy.sh topic name (e.g. `syed-property-alerts`) |
| `EMAIL_FROM` | Your Gmail address (only if using email) |
| `EMAIL_TO`   | Where to send the digest |
| `EMAIL_PASS` | Gmail **App Password** (not your main password) |

### 3. Test it manually

Go to **Actions → Weekly Property Search → Run workflow** to trigger immediately without waiting for Monday.

---

## Notification: ntfy.sh (recommended)

1. Install the **ntfy** app on your phone (iOS or Android)
2. Subscribe to your topic name (e.g. `syed-property-alerts`)
3. Set `NOTIFY_VIA=ntfy` and `NTFY_TOPIC=syed-property-alerts`

Done — you'll get a push notification with the week's new listings.

---

## Customisation

In `agent.py`, you can adjust:

| Variable | Default | Description |
|---|---|---|
| `MAX_PRICE` | `500000` | Max budget |
| `MIN_BEDS` / `MAX_BEDS` | `3` | Bedroom count |
| `GARDEN_KEYWORDS` | (list) | What counts as a "large garden" |
| `AREAS` | KT3, KT4, SM6 | Add/remove outcode areas |

To add another area (e.g. Sutton, SM1):
```python
{"name": "Sutton", "outcode": "SM1"},
```

---

## How it works

1. Resolves each outcode to a Rightmove location ID via their type-ahead API
2. Queries Rightmove's internal search API (same endpoint the website uses)
3. Filters for listings mentioning large garden keywords in features/summary
4. Deduplicates against a cached `seen_listings.json` (persisted via GitHub Actions cache)
5. Sends a digest of **new** listings only — no repeat spam
