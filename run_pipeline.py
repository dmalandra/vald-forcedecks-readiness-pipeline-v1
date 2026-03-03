# run_pipeline.py
"""
VALD ForceDecks Pipeline — Master Runner
-----------------------------------------
Pulls CMJ data for a sport, computes baselines and traffic lights,
and outputs a dashboard-ready snapshot.

Usage:
    python3 run_pipeline.py                        # today's date, womens_lacrosse
    python3 run_pipeline.py --sport womens_lacrosse --date 2026-03-02
    python3 run_pipeline.py --season 2026-01-01 2026-03-02
"""

import argparse
import pandas as pd
from datetime import date

from vald_client  import get_cmj_results, get_cmj_season
from vald_metrics import process_cmj_data, get_dashboard_snapshot


# ── Defaults ──────────────────────────────────────────────────────────────────
DEFAULT_SPORT  = "womens_lacrosse"
SEASON_START   = "2026-01-01"


def run(sport_key: str,
        test_date: str,
        season_start: str = SEASON_START,
        verbose: bool = True) -> pd.DataFrame:
    """
    Full pipeline for a single testing day.

    Strategy:
        1. Pull full season history → build rolling baselines
        2. Isolate today's records → compute deviations + traffic lights
        3. Return dashboard snapshot

    Args:
        sport_key:    e.g. "womens_lacrosse"
        test_date:    ISO date string e.g. "2026-03-02"
        season_start: start of season for baseline history
        verbose:      print progress and results

    Returns:
        Dashboard snapshot DataFrame
    """
    if verbose:
        print("=" * 60)
        print(f"VALD ForceDecks Pipeline")
        print(f"Sport:  {sport_key}")
        print(f"Date:   {test_date}")
        print("=" * 60 + "\n")

    # ── Step 1: Pull full season history ──────────────────────────────────────
    if verbose:
        print("Step 1: Pulling season history for baseline calculation...")

    season_records = get_cmj_season(
        sport_key    = sport_key,
        season_start = season_start,
        season_end   = test_date,
    )

    if not season_records:
        print("No season data found. Cannot compute baselines.")
        return pd.DataFrame()

    df_season = pd.DataFrame(season_records)
    if verbose:
        print(f"  Season records: {len(df_season)} across "
              f"{df_season['athlete_name'].nunique()} athletes\n")

    # ── Step 2: Run metrics pipeline on full season ───────────────────────────
    if verbose:
        print("Step 2: Computing baselines, deviations, traffic lights...")

    df_processed = process_cmj_data(
        df_season,
        athlete_col = "athlete_id",
        date_col    = "date"
    )

    if verbose:
        print("  Done.\n")

    # ── Step 3: Extract today's snapshot ─────────────────────────────────────
    if verbose:
        print("Step 3: Extracting today's dashboard snapshot...")

    snapshot = get_dashboard_snapshot(df_processed, test_date=test_date)

    if verbose:
        print(f"  Athletes tested today: {len(snapshot)}\n")

    # ── Step 4: Print results ─────────────────────────────────────────────────
    if verbose:
        _print_snapshot(snapshot)

    # ── Step 5: Write to Google Sheets ────────────────────────────────────────
    if verbose:
        print("Step 5: Writing results to Google Sheets...")
    from vald_sheets import write_results
    write_results(snapshot, test_date)

    return snapshot


def _print_snapshot(snapshot: pd.DataFrame):
    """Prints a formatted dashboard snapshot to the terminal."""

    LIGHT_EMOJI = {
        "GREEN":  "🟢",
        "YELLOW": "🟡",
        "RED":    "🔴",
    }

    print("=" * 60)
    print("DASHBOARD SNAPSHOT")
    print("=" * 60)

    for _, row in snapshot.sort_values("overall_light",
                                        key=lambda x: x.map(
                                            {"RED": 0, "YELLOW": 1, "GREEN": 2}
                                        )).iterrows():

        light   = row.get("overall_light", "GREEN")
        emoji   = LIGHT_EMOJI.get(light, "⚪")
        name    = row.get("athlete_name", row.get("athlete_id", "Unknown"))
        warning = " ⚠️  BASELINE ESTABLISHING" if row.get("baseline_warning") else ""

        print(f"\n{emoji}  {name}{warning}")

        # Per-metric deviations
        from vald_metrics import METRIC_CONFIG
        for metric, config in METRIC_CONFIG.items():
            dev_col   = f"{metric}_deviation"
            light_col = f"{metric}_light"
            if dev_col in row and pd.notna(row[dev_col]):
                m_emoji = LIGHT_EMOJI.get(row.get(light_col, "GREEN"), "⚪")
                print(f"   {m_emoji} {config['label']:22s} "
                      f"{row[dev_col]:+.1f}%")

        # Flagged metrics
        flagged = row.get("flagged_metrics", "None")
        if flagged != "None":
            print(f"   ⚡ Flags: {flagged}")

    print("\n" + "=" * 60)

    # Summary counts
    from vald_metrics import GREEN, YELLOW, RED
    n_red    = (snapshot["overall_light"] == RED).sum()
    n_yellow = (snapshot["overall_light"] == YELLOW).sum()
    n_green  = (snapshot["overall_light"] == GREEN).sum()
    print(f"🔴 RED: {n_red}   🟡 YELLOW: {n_yellow}   🟢 GREEN: {n_green}")
    print("=" * 60 + "\n")


# ── CLI entry point ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="VALD ForceDecks readiness pipeline"
    )
    parser.add_argument(
        "--sport",
        default=DEFAULT_SPORT,
        help="Sport key e.g. womens_lacrosse (default: womens_lacrosse)"
    )
    parser.add_argument(
        "--date",
        default=str(date.today()),
        help="Test date ISO format e.g. 2026-03-02 (default: today)"
    )
    parser.add_argument(
        "--season-start",
        default=SEASON_START,
        help=f"Season start date (default: {SEASON_START})"
    )

    args = parser.parse_args()

    run(
        sport_key    = args.sport,
        test_date    = args.date,
        season_start = args.season_start,
    )