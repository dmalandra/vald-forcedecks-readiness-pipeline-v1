# vald_sheets.py
"""
Google Sheets Writer
---------------------
Writes VALD ForceDecks pipeline results to two destinations:

1. VALD_ForceDecks tab (raw data archive)
   - Creates tab if it doesn't exist
   - Appends one row per athlete per testing date
   - Never overwrites existing rows

2. Prescription Dashboard tab (direct coach-facing update)
   - Matches athlete by last name in column A (rows 11+)
   - Writes overall traffic light emoji → column I
   - Writes flagged metrics detail → column L
   - Leaves all formula-driven columns untouched
"""

import gspread
import pandas as pd
from datetime import datetime
from google.oauth2.service_account import Credentials
from vald_config import GOOGLE_SHEET_NAME, SERVICE_ACCOUNT_FILE
from vald_metrics import METRIC_CONFIG, GREEN, YELLOW, RED

# ── Constants ─────────────────────────────────────────────────────────────────
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

FORCEDECKS_TAB    = "VALD_ForceDecks"
DASHBOARD_TAB     = "Prescription Dashboard"
ATHLETE_COL       = 1          # Column A
CMJ_LIGHT_COL     = 9          # Column I
FLAGS_COL         = 14         # Column N
HEADER_ROW        = 10         # Headers in row 10
FIRST_ATHLETE_ROW = 11         # Data starts row 11
DATE_CELL         = "B1"       # Date selector cell

LIGHT_EMOJI = {
    GREEN:  "🟢",
    YELLOW: "🟡",
    RED:    "🔴",
}

# ── ForceDecks tab headers ────────────────────────────────────────────────────
FORCEDECKS_HEADERS = [
    "Date",
    "Athlete",
    "Jump Height (in)",
    "RSImod",
    "Ecc Braking RFD/BM",
    "Peak Power/BM",
    "Contraction Time (s)",
    "EDI/BM",
    "Overall Light",
    "Flagged Metrics",
    "Baseline Warning",
    "JH Dev%",
    "RSImod Dev%",
    "EccRFD Dev%",
    "PP Dev%",
    "CT Dev%",
    "Best Trial",
]


# ═════════════════════════════════════════════════════════════════════════════
# CONNECTION
# ═════════════════════════════════════════════════════════════════════════════

def get_client():
    """Authenticates and returns a gspread client."""
    creds = Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE,
        scopes=SCOPES
    )
    return gspread.authorize(creds)


def get_sheet():
    """Opens and returns the Google Sheet."""
    client = get_client()
    return client.open(GOOGLE_SHEET_NAME)


# ═════════════════════════════════════════════════════════════════════════════
# FORCEDECKS TAB — raw data archive
# ═════════════════════════════════════════════════════════════════════════════

def ensure_forcedecks_tab(sheet):
    """
    Creates the VALD_ForceDecks tab if it doesn't exist.
    Adds headers on first creation.

    Args:
        sheet: gspread Spreadsheet object

    Returns:
        gspread Worksheet object
    """
    try:
        ws = sheet.worksheet(FORCEDECKS_TAB)
        print(f"  Tab '{FORCEDECKS_TAB}' found.")
    except gspread.WorksheetNotFound:
        print(f"  Tab '{FORCEDECKS_TAB}' not found — creating...")
        ws = sheet.add_worksheet(
            title=FORCEDECKS_TAB,
            rows=1000,
            cols=len(FORCEDECKS_HEADERS)
        )
        ws.append_row(FORCEDECKS_HEADERS, value_input_option="RAW")
        print(f"  Tab created with headers.")

    return ws


def get_existing_forcedecks_records(ws):
    """
    Returns a set of (date, athlete_name) tuples already in the tab.
    Used to prevent duplicate rows on re-runs.

    Args:
        ws: VALD_ForceDecks worksheet

    Returns:
        set of (date_str, athlete_name) tuples
    """
    records = ws.get_all_records()
    return {
        (str(r.get("Date", "")), str(r.get("Athlete", "")))
        for r in records
    }


def write_forcedecks_tab(snapshot: pd.DataFrame, test_date: str):
    """
    Appends today's results to the VALD_ForceDecks archive tab.
    Skips rows that already exist (safe to re-run).

    Args:
        snapshot:  dashboard snapshot DataFrame from run_pipeline.py
        test_date: ISO date string e.g. "2026-03-02"
    """
    print(f"\nWriting to '{FORCEDECKS_TAB}' tab...")

    sheet    = get_sheet()
    ws       = ensure_forcedecks_tab(sheet)
    existing = get_existing_forcedecks_records(ws)

    rows_written  = 0
    rows_skipped  = 0

    for _, row in snapshot.iterrows():
        athlete_name = row.get("athlete_name", "")
        key          = (test_date, athlete_name)

        if key in existing:
            rows_skipped += 1
            continue

        # Format deviation values as percentages
        def dev(metric):
            val = row.get(f"{metric}_deviation")
            if pd.isna(val) or val is None:
                return ""
            return round(float(val), 2)

        new_row = [
            test_date,
            athlete_name,
            round(float(row["jump_height"]), 3) if pd.notna(row.get("jump_height")) else "",
            round(float(row["rsim"]), 3)         if pd.notna(row.get("rsim")) else "",
            round(float(row["ecc_braking_rfd_bm"]), 3) if pd.notna(row.get("ecc_braking_rfd_bm")) else "",
            round(float(row["peak_power_bm"]), 3) if pd.notna(row.get("peak_power_bm")) else "",
            round(float(row["contraction_time"]), 4) if pd.notna(row.get("contraction_time")) else "",
            round(float(row["ecc_decel_impulse_bm"]), 4) if pd.notna(row.get("ecc_decel_impulse_bm")) else "",
            row.get("overall_light", ""),
            row.get("flagged_metrics", ""),
            "YES" if row.get("baseline_warning") else "NO",
            dev("jump_height"),
            dev("rsim"),
            dev("ecc_braking_rfd_bm"),
            dev("peak_power_bm"),
            dev("contraction_time"),
            int(row["best_trial"]) if pd.notna(row.get("best_trial")) else "",
        ]

        ws.append_row(new_row, value_input_option="RAW")
        rows_written += 1

    print(f"  Rows written:  {rows_written}")
    print(f"  Rows skipped:  {rows_skipped} (already exist)")


# ═════════════════════════════════════════════════════════════════════════════
# PRESCRIPTION DASHBOARD TAB — direct coach-facing update
# ═════════════════════════════════════════════════════════════════════════════

def build_roster_map(ws):
    """
    Builds a dict mapping last name → row number from column A.
    Only reads from FIRST_ATHLETE_ROW onwards.

    Args:
        ws: Prescription Dashboard worksheet

    Returns:
        dict {"Clark": 11, "Durkin": 12, ...}
    """
    # Get all values in column A from row 11 onwards
    col_a = ws.col_values(ATHLETE_COL)
    roster_map = {}

    for i, name in enumerate(col_a):
        row_num = i + 1  # gspread is 1-indexed
        if row_num < FIRST_ATHLETE_ROW:
            continue
        name = name.strip()
        if name:
            roster_map[name] = row_num

    return roster_map


def extract_last_name(full_name: str) -> str:
    """
    Extracts last name from a full name string.
    Handles "First Last" and "First Middle Last" formats.

    Args:
        full_name: e.g. "Mackenzie Clark"

    Returns:
        "Clark"
    """
    parts = full_name.strip().split()
    return parts[-1] if parts else full_name


def write_dashboard(snapshot: pd.DataFrame, test_date: str):
    """
    Writes traffic light and flags directly to the Prescription Dashboard.

    For each athlete in today's snapshot:
        - Finds their row by matching last name to column A
        - Writes overall traffic light emoji to column I
        - Writes flagged metrics string to column L

    Args:
        snapshot:  dashboard snapshot DataFrame
        test_date: ISO date string e.g. "2026-03-02"
    """
    print(f"\nWriting to '{DASHBOARD_TAB}' tab...")

    sheet = get_sheet()

    try:
        ws = sheet.worksheet(DASHBOARD_TAB)
    except gspread.WorksheetNotFound:
        print(f"  ERROR: Tab '{DASHBOARD_TAB}' not found.")
        print(f"  Available tabs: {[w.title for w in sheet.worksheets()]}")
        return

    # Build roster map
    roster_map = build_roster_map(ws)
    print(f"  Roster athletes found: {len(roster_map)}")

    # Format date as M/D/YYYY to match existing sheet format
    from datetime import datetime
    date_obj    = datetime.strptime(test_date, "%Y-%m-%d")
    sheet_date  = f"{date_obj.month}/{date_obj.day}/{date_obj.year}"
    ws.update(DATE_CELL, [[sheet_date]])

    # Batch updates for efficiency — one API call instead of N
    updates = []
    matched   = 0
    unmatched = []

    for _, row in snapshot.iterrows():
        full_name = row.get("athlete_name", "")
        last_name = extract_last_name(full_name)

        if last_name not in roster_map:
            unmatched.append(full_name)
            continue

        row_num = roster_map[last_name]
        light   = row.get("overall_light", GREEN)
        emoji   = LIGHT_EMOJI.get(light, "🟢")
        flagged = row.get("flagged_metrics", "None")

        # Format flags for dashboard
        # e.g. "🔴 RSImod -9.6%, Ecc. Braking RFD/BM -9.1%"
        if flagged == "None":
            flag_str = ""
        else:
            flag_str = f"{emoji} {flagged}"

        # Column I — traffic light emoji
        updates.append({
            "range": gspread.utils.rowcol_to_a1(row_num, CMJ_LIGHT_COL),
            "values": [[emoji]]
        })

        # Column L — flagged metrics
        updates.append({
            "range": gspread.utils.rowcol_to_a1(row_num, FLAGS_COL),
            "values": [[flag_str]]
        })

        matched += 1

    # Execute all updates in one batch call
    if updates:
        ws.batch_update(updates, value_input_option="RAW")

    print(f"  Athletes updated:  {matched}")
    if unmatched:
        print(f"  Unmatched athletes: {unmatched}")
        print(f"  Check VALD name vs Sheet name for these athletes.")


# ═════════════════════════════════════════════════════════════════════════════
# MASTER WRITE FUNCTION
# ═════════════════════════════════════════════════════════════════════════════

def write_results(snapshot: pd.DataFrame, test_date: str):
    """
    Master function — writes to both tabs in sequence.

    Args:
        snapshot:  dashboard snapshot DataFrame from run_pipeline.py
        test_date: ISO date string e.g. "2026-03-02"
    """
    print("\n" + "=" * 60)
    print("WRITING TO GOOGLE SHEETS")
    print("=" * 60)

    write_forcedecks_tab(snapshot, test_date)
    write_dashboard(snapshot, test_date)

    print("\n✅ Google Sheets update complete.")