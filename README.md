# vald-forcedecks-readiness-pipeline-v1

An automated neuromuscular readiness monitoring pipeline integrating the VALD ForceDecks API with Google Sheets. Built for daily athlete monitoring and weight room prescription guidance in collegiate strength & conditioning.

Pulls countermovement jump (CMJ) test data from the VALD Hub, computes rolling individual baselines, calculates percent deviations, assigns traffic light readiness flags, and writes results directly to a Google Sheets coaching dashboard — triggered by a single command or running continuously in watch mode during live testing sessions.

---

## Sample Output

```
============================================================
VALD ForceDecks Pipeline
Sport:  womens_lacrosse
Date:   2026-03-02
============================================================

Step 1: Pulling season history for baseline calculation...
  27 athletes found
  41 CMJ tests for womens_lacrosse
  Season records: 41 across 23 athletes

Step 2: Computing baselines, deviations, traffic lights...
  Done.

Step 3: Extracting today's dashboard snapshot...
  Athletes tested today: 20

============================================================
DASHBOARD SNAPSHOT
============================================================

🔴  Athlete A ⚠️  BASELINE ESTABLISHING
   🔴 Jump Height            -30.9%
   🔴 RSImod                 -42.9%
   🔴 Ecc. Braking RFD/BM    -51.5%
   🔴 Peak Power/BM          -26.0%
   🔴 Contraction Time       +17.8%
   ⚡ Flags: Jump Height (RED) -30.9%, RSImod (RED) -42.9%

🟡  Athlete B ⚠️  BASELINE ESTABLISHING
   🟡 Jump Height            -7.1%
   🔴 RSImod                 -14.8%
   🟡 Peak Power/BM          -9.5%
   🟡 Contraction Time       +6.2%
   ⚡ Flags: RSImod (RED) -14.8%, Peak Power/BM (YELLOW) -9.5%

🟢  Athlete C
   🟢 Jump Height            +11.0%
   🟢 RSImod                 +23.6%
   🟢 Ecc. Braking RFD/BM    +27.8%
   🟢 Peak Power/BM          +15.4%
   🟢 Contraction Time       -10.0%

============================================================
🔴 RED: 12   🟡 YELLOW: 0   🟢 GREEN: 8
============================================================

Writing to 'VALD_ForceDecks' tab...
  Rows written:  20
Writing to 'Prescription Dashboard' tab...
  Athletes updated:  20
✅ Google Sheets update complete.
```

---

## Architecture

```
VALD Hub (ForceDecks device)
        │
        ▼
VALD External APIs (OAuth2)
  ├── External Tenants API   →  group/sport filtering
  ├── External Profiles API  →  athlete name resolution
  └── ForceDecks API         →  CMJ trial data
        │
        ▼
vald_client.py
  ├── Profile map: ForceDecks athleteId → athlete name
  ├── CMJ test retrieval: detailed + trials endpoints
  └── Best trial selection (highest jump height, cold-first exclusion)
        │
        ▼
vald_metrics.py
  ├── Rolling baseline (4-window, shift=1, no data leakage)
  ├── Team mean fallback for <2 prior observations
  ├── Percent deviation calculation
  ├── Metric-level traffic light classification
  └── Overall readiness flag (hierarchy logic)
        │
        ▼
vald_sheets.py
  ├── VALD_ForceDecks tab  →  raw data archive (append, no duplicates)
  └── Prescription Dashboard tab  →  traffic light + flags (batch update)
```

---

## Monitored Metrics

Five CMJ metrics monitored per athlete per session:

| Metric | VALD Result ID | Unit | Flag Direction |
|---|---|---|---|
| Jump Height (Flight Time) | 6553613 | inches | decrease |
| RSI-modified | 6553698 | m/s | decrease |
| Eccentric Braking RFD / BM | 6553679 | N/s/kg | decrease |
| Peak Power / BM | 6553604 | W/kg | decrease |
| Contraction Time | 6553643 | ms | increase |

### Traffic Light Thresholds

| Metric | Yellow | Red |
|---|---|---|
| Jump Height | < −5% | < −10% |
| RSImod | < −7% | < −12% |
| Ecc. Braking RFD/BM | < −7% | < −12% |
| Peak Power/BM | < −6% | < −10% |
| Contraction Time | > +6% | > +10% |

### Overall Flag Hierarchy

| Condition | Overall Light |
|---|---|
| Any metric RED, or 2+ metrics YELLOW | 🔴 RED |
| Exactly 1 metric YELLOW | 🟡 YELLOW |
| All metrics GREEN | 🟢 GREEN |

---

## Baseline Logic

| Prior observations | Baseline used |
|---|---|
| 0–1 | Team mean (flagged ⚠️ ESTABLISHING) |
| 2–3 | Individual rolling mean (min_periods=2) |
| 4+ | Individual rolling mean (4-window) |

`shift(1)` applied before rolling calculation to prevent data leakage — baseline only uses observations prior to the current test date.

---

## Project Structure

```
vald_pipeline/
├── run_pipeline.py        # Master runner — single entry point
├── vald_client.py         # VALD API data retrieval
├── vald_metrics.py        # Baseline, deviation, traffic light logic
├── vald_sheets.py         # Google Sheets writer
├── vald_auth.py           # OAuth2 token management with caching
├── vald_config.py         # Constants, result IDs, group mappings
├── .env                   # Credentials (not committed)
├── service_account.json   # Google service account (not committed)
├── .gitignore
└── dev/                   # API discovery and diagnostic scripts
    ├── probe_apis.py
    ├── probe_forcedecks.py
    ├── probe_trials.py
    └── explore_forcedecks.py
```

---

## Setup

### Requirements

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install requests pandas numpy gspread google-auth python-dotenv
```

### Environment Variables

Create a `.env` file in the project root:

```
CLIENT_ID=your_vald_client_id
CLIENT_SECRET=your_vald_client_secret
TENANT_ID=your_vald_tenant_id
GOOGLE_SHEET_NAME=Your Sheet Name Here
SERVICE_ACCOUNT_FILE=service_account.json
```

### Google Sheets

1. Create a Google Cloud project and enable the Sheets and Drive APIs
2. Create a service account and download the JSON key as `service_account.json`
3. Share your Google Sheet with the service account email (Editor access)

### VALD API Access

Requires VALD client credentials with access to:
- External Tenants API
- External Profiles API
- ForceDecks API (v2019q3 team endpoints)

Contact your VALD client success manager to obtain credentials.

---

## Usage

```bash
# Run for today's date (default sport: womens_lacrosse)
python3 run_pipeline.py

# Run for a specific date
python3 run_pipeline.py --date 2026-03-02

# Run for a specific sport
python3 run_pipeline.py --sport womens_lacrosse --date 2026-03-02

# Run with custom season start for baseline history
python3 run_pipeline.py --date 2026-03-02 --season-start 2026-01-01

# Watch mode — runs continuously during live testing sessions
# Checks for new tests every 3 minutes and updates Sheets automatically
python3 run_pipeline.py --watch

# Watch mode with custom polling interval (minutes)
python3 run_pipeline.py --watch --interval 2
```

---

## Automation

### Watch Mode (testing days)

The recommended approach on testing days. Start watch mode before athletes begin testing and leave it running. The pipeline polls for new CMJ tests on a set interval, updates the Google Sheet when new data appears, and skips duplicate records on re-runs.

```bash
python3 run_pipeline.py --watch
```

Typical latency from test completion to dashboard update:
- VALD device → cloud sync: ~1–2 minutes
- Pipeline polling interval: 3 minutes (default)
- **Total: data visible within ~5 minutes of test completion**

Stop with `Ctrl+C` when testing is complete.

### Cron (scheduled daily runs)

For non-testing days or automated daily checks:

```bash
crontab -e
```

```
0 9 * * 1-5 cd /path/to/vald_pipeline && .venv/bin/python3 run_pipeline.py
```

### GitHub Actions (cloud)

See `.github/workflows/daily_pipeline.yml` for scheduled cloud execution independent of local machine availability.

---

## Google Sheets Output

### VALD_ForceDecks Tab (archive)

One row per athlete per testing date. Appends new rows on each run — safe to re-run, duplicates are skipped automatically. Columns:

`Date | Athlete | Jump Height (in) | RSImod | Ecc Braking RFD/BM | Peak Power/BM | Contraction Time (s) | EDI/BM | Overall Light | Flagged Metrics | Baseline Warning | JH Dev% | RSImod Dev% | EccRFD Dev% | PP Dev% | CT Dev% | Best Trial`

### Prescription Dashboard Tab (coach-facing)

Writes directly to the existing coaching dashboard on each run:

| Column | Content |
|---|---|
| I | Overall traffic light emoji (🟢 🟡 🔴) |
| L | Flagged metrics with deviation percentages |
| B1 | Date selector updated to test date (M/D/YYYY format) |

All formula-driven columns (EWMA sRPE, Wellness %, Game Proximity, Weight Room Prescription) are left untouched. The traffic light in column I feeds into the Weight Room Prescription formula in column K, which uses a flag hierarchy of ForceDecks status → wellness → EWMA load → session load to generate velocity-based training recommendations calibrated to RepOne VBT zones.

---

## Key Technical Notes

**ID system mismatch:** VALD's ForceDecks API and Profiles API use different athlete ID systems. ForceDecks `athleteId` matches the `id` field in the ForceDecks athletes endpoint, while the Profiles API uses a separate `profileId`. The bridge is `hubId` in ForceDecks athletes, which equals `profileId` in the Profiles API. Profile map is built from the ForceDecks athletes endpoint to ensure correct ID matching against test records.

**Trials endpoint:** The detailed tests endpoint (`/v2019q3/teams/{teamId}/tests/detailed/{dateFrom}/{dateTo}`) embeds trial structure but returns empty `results` arrays. Metric values require a separate call to `/v2019q3/teams/{teamId}/tests/{testId}/trials` per test.

**Date format:** The pipeline writes dates to the Google Sheet in M/D/YYYY format to maintain compatibility with existing DATEVALUE() formula references in the dashboard.

---

## Roadmap

- **v2** — Retrospective analysis notebook: seasonal trend analysis, metric correlation, load-readiness relationships across full season data
- **v3** — Multi-sport database + Streamlit/Plotly dashboard: PostgreSQL backend, all sports feeding a single pipeline, interactive web frontend

---

## Author

Dustin Malandra
Performance Scientist / Strength & Conditioning Coach
