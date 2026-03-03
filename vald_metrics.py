# vald_metrics.py
"""
ForceDecks CMJ Metrics Module
------------------------------
Computes rolling baselines, percent deviations, metric-level traffic lights,
and overall readiness flags for each athlete on a given testing day.

Metrics monitored:
    - Jump height          (decrease = concerning)
    - RSImod               (decrease = concerning)
    - Ecc. braking RFD/BM  (decrease = concerning)
    - Peak Power/BM        (decrease = concerning)
    - Contraction time     (increase = concerning)

Baseline logic:
    - 0-1 prior observations → team mean (temporary, flagged with warning)
    - 2-3 prior observations → individual rolling mean (min_periods=2)
    - 4+  prior observations → individual rolling mean (4-window)

Traffic light thresholds (D3-calibrated, less conservative):
    Metric                  Yellow      Red         Direction
    Jump height             < -5%       < -10%      decrease
    RSImod                  < -7%       < -12%      decrease
    Ecc. braking RFD/BM     < -7%       < -12%      decrease
    Peak Power/BM           < -6%       < -10%      decrease
    Contraction time        > +6%       > +10%      increase

Overall traffic light hierarchy:
    RED    → any single metric RED, OR two or more metrics YELLOW
    YELLOW → exactly one metric YELLOW, all others GREEN
    GREEN  → all metrics GREEN
"""

import pandas as pd
import numpy as np
from typing import Optional

# ── Metric configuration ──────────────────────────────────────────────────────
# Each entry defines thresholds and direction for one ForceDecks metric.
# direction: "decrease" = flag when value drops below baseline
#            "increase" = flag when value rises above baseline

METRIC_CONFIG = {
    "jump_height": {
        "label":     "Jump Height",
        "direction": "decrease",
        "yellow":    -5.0,
        "red":       -10.0,
    },
    "rsim": {
        "label":     "RSImod",
        "direction": "decrease",
        "yellow":    -7.0,
        "red":       -12.0,
    },
    "ecc_braking_rfd_bm": {
        "label":     "Ecc. Braking RFD/BM",
        "direction": "decrease",
        "yellow":    -7.0,
        "red":       -12.0,
    },
    "peak_power_bm": {
        "label":     "Peak Power/BM",
        "direction": "decrease",
        "yellow":    -6.0,
        "red":       -10.0,
    },
    "contraction_time": {
        "label":     "Contraction Time",
        "direction": "increase",
        "yellow":    6.0,
        "red":       10.0,
    },
}
# ── Traffic light constants ───────────────────────────────────────────────────
GREEN  = "GREEN"
YELLOW = "YELLOW"
RED    = "RED"
BASELINE_ESTABLISHING = "ESTABLISHING"


# ═════════════════════════════════════════════════════════════════════════════
# BASELINE CALCULATION
# ═════════════════════════════════════════════════════════════════════════════

def compute_rolling_baselines(df: pd.DataFrame,
                               athlete_col: str = "athlete_id",
                               date_col: str = "date",
                               window: int = 4,
                               min_periods: int = 2) -> pd.DataFrame:
    """
    Computes a rolling individual baseline for each metric per athlete.
    Uses shift(1) to ensure no data leakage — baseline only uses
    observations PRIOR to the current test.

    Adds columns:
        {metric}_baseline       → rolling mean of prior observations
        {metric}_team_baseline  → team mean for that testing week (fallback)
        {metric}_baseline_type  → "individual" or "team"

    Args:
        df:          DataFrame with one row per athlete per test date
        athlete_col: column name for athlete identifier
        date_col:    column name for test date
        window:      rolling window size (default 4)
        min_periods: minimum prior observations for individual baseline (default 2)

    Returns:
        df with baseline columns added
    """
    df = df.sort_values([athlete_col, date_col]).copy()
    df[date_col] = pd.to_datetime(df[date_col])

    for metric in METRIC_CONFIG:
        if metric not in df.columns:
            continue

        # Individual rolling baseline (shift=1 prevents leakage)
        df[f"{metric}_baseline"] = (
            df.groupby(athlete_col)[metric]
            .transform(lambda x: x.shift(1)
                                  .rolling(window=window, min_periods=min_periods)
                                  .mean())
        )

        # Team mean baseline per testing date (fallback for new athletes)
        df[f"{metric}_team_baseline"] = (
            df.groupby(date_col)[metric]
            .transform("mean")
        )

        # Count prior observations per athlete to determine baseline type
        df[f"{metric}_prior_count"] = (
            df.groupby(athlete_col)[metric]
            .transform(lambda x: x.shift(1).expanding().count())
            .fillna(0)
        )

        # Assign which baseline to use
        df[f"{metric}_baseline_type"] = np.where(
            df[f"{metric}_prior_count"] >= min_periods,
            "individual",
            "team"
        )

        # Use team baseline where individual isn't available yet
        df[f"{metric}_baseline"] = np.where(
            df[f"{metric}_baseline_type"] == "individual",
            df[f"{metric}_baseline"],
            df[f"{metric}_team_baseline"]
        )

    return df


# ═════════════════════════════════════════════════════════════════════════════
# DEVIATION CALCULATION
# ═════════════════════════════════════════════════════════════════════════════

def compute_deviations(df: pd.DataFrame) -> pd.DataFrame:
    """
    Computes percent deviation from baseline for each metric.

    Formula: (observed - baseline) / baseline * 100

    Adds columns:
        {metric}_deviation  → percent deviation from baseline

    Args:
        df: DataFrame with baseline columns already computed

    Returns:
        df with deviation columns added
    """
    for metric in METRIC_CONFIG:
        if f"{metric}_baseline" not in df.columns:
            continue

        df[f"{metric}_deviation"] = (
            (df[metric] - df[f"{metric}_baseline"])
            / df[f"{metric}_baseline"] * 100
        )

    return df


# ═════════════════════════════════════════════════════════════════════════════
# TRAFFIC LIGHT LOGIC
# ═════════════════════════════════════════════════════════════════════════════

def classify_metric(deviation: float, config: dict) -> str:
    """
    Assigns a traffic light colour to a single metric deviation.

    Args:
        deviation: percent deviation from baseline
        config:    metric config dict with direction, yellow, red thresholds

    Returns:
        "GREEN", "YELLOW", or "RED"
    """
    if pd.isna(deviation):
        return GREEN  # no data = don't penalise

    if config["direction"] == "decrease":
        if deviation <= config["red"]:
            return RED
        elif deviation <= config["yellow"]:
            return YELLOW
        else:
            return GREEN

    else:  # "increase" direction (contraction time)
        if deviation >= config["red"]:
            return RED
        elif deviation >= config["yellow"]:
            return YELLOW
        else:
            return GREEN


def classify_overall(metric_lights: dict) -> str:
    """
    Assigns overall traffic light using hierarchy rule:
        RED    → any metric RED, OR 2+ metrics YELLOW
        YELLOW → exactly 1 metric YELLOW
        GREEN  → all metrics GREEN

    Args:
        metric_lights: dict of {metric_key: "GREEN"/"YELLOW"/"RED"}

    Returns:
        "GREEN", "YELLOW", or "RED"
    """
    lights = list(metric_lights.values())
    n_red    = lights.count(RED)
    n_yellow = lights.count(YELLOW)

    if n_red >= 1 or n_yellow >= 2:
        return RED
    elif n_yellow == 1:
        return YELLOW
    else:
        return GREEN


def compute_traffic_lights(df: pd.DataFrame) -> pd.DataFrame:
    """
    Applies metric-level and overall traffic light classification to every row.

    Adds columns:
        {metric}_light      → per-metric traffic light
        overall_light       → overall readiness traffic light
        baseline_warning    → True if any metric is using team baseline
        flagged_metrics     → comma-separated list of concerning metrics

    Args:
        df: DataFrame with deviation columns already computed

    Returns:
        df with traffic light columns added
    """
    metric_light_cols = []

    for metric, config in METRIC_CONFIG.items():
        dev_col   = f"{metric}_deviation"
        light_col = f"{metric}_light"

        if dev_col not in df.columns:
            df[light_col] = GREEN
        else:
            df[light_col] = df[dev_col].apply(
                lambda d: classify_metric(d, config)
            )

        metric_light_cols.append(light_col)

    # Overall traffic light
    def _overall(row):
        lights = {col.replace("_light", ""): row[col]
                  for col in metric_light_cols}
        return classify_overall(lights)

    df["overall_light"] = df.apply(_overall, axis=1)

    # Baseline warning flag — True if ANY metric is using team baseline
    type_cols = [f"{m}_baseline_type" for m in METRIC_CONFIG
                 if f"{m}_baseline_type" in df.columns]
    if type_cols:
        df["baseline_warning"] = df[type_cols].apply(
            lambda row: any(v == "team" for v in row), axis=1
        )
    else:
        df["baseline_warning"] = False

    # Flagged metrics — list of metrics in YELLOW or RED
    def _flagged(row):
        flags = []
        for metric, config in METRIC_CONFIG.items():
            light_col = f"{metric}_light"
            if light_col in row and row[light_col] in [YELLOW, RED]:
                flags.append(
                    f"{config['label']} ({row[light_col]}) "
                    f"{row.get(f'{metric}_deviation', 0):+.1f}%"
                )
        return ", ".join(flags) if flags else "None"

    df["flagged_metrics"] = df.apply(_flagged, axis=1)

    return df


# ═════════════════════════════════════════════════════════════════════════════
# MASTER PIPELINE FUNCTION
# ═════════════════════════════════════════════════════════════════════════════

def process_cmj_data(df: pd.DataFrame,
                      athlete_col: str = "athlete_id",
                      date_col: str = "date") -> pd.DataFrame:
    """
    Master function — runs the full metrics pipeline in one call.

    Steps:
        1. Compute rolling baselines (individual or team fallback)
        2. Compute percent deviations
        3. Assign metric-level traffic lights
        4. Assign overall traffic light
        5. Flag concerning metrics

    Args:
        df:          DataFrame with one row per athlete per test date,
                     containing raw ForceDecks metric columns
        athlete_col: column name for athlete identifier
        date_col:    column name for test date

    Returns:
        Fully processed DataFrame ready for dashboard output
    """
    df = compute_rolling_baselines(df, athlete_col, date_col)
    df = compute_deviations(df)
    df = compute_traffic_lights(df)
    return df


def get_dashboard_snapshot(df: pd.DataFrame,
                            test_date: Optional[str] = None) -> pd.DataFrame:
    """
    Returns a clean dashboard-ready snapshot for a single testing date.
    Selects only the columns a strength coach needs to see.

    Args:
        df:        Fully processed DataFrame from process_cmj_data()
        test_date: ISO date string e.g. "2025-04-07"
                   If None, uses the most recent date in the data.

    Returns:
        Filtered DataFrame with one row per athlete, key columns only
    """
    if test_date is None:
        test_date = df["date"].max()

    snapshot = df[df["date"] == pd.to_datetime(test_date)].copy()

    # Build output column list
    base_cols = ["athlete_id", "athlete_name", "date", "weight_kg",
                 "overall_light", "baseline_warning", "flagged_metrics",
                 "best_trial", "ecc_decel_impulse_bm"]

    metric_cols = []
    for metric, config in METRIC_CONFIG.items():
        dev_col   = f"{metric}_deviation"
        light_col = f"{metric}_light"
        type_col  = f"{metric}_baseline_type"
        if metric in snapshot.columns:
            metric_cols.append(metric)        # raw value
        if dev_col in snapshot.columns:
            metric_cols.extend([dev_col, light_col, type_col])

    # Always include these columns if present regardless of metric config
    always_include = ["athlete_id", "athlete_name", "date", "weight_kg",
                      "overall_light", "baseline_warning", "flagged_metrics",
                      "best_trial", "ecc_decel_impulse_bm"]

    output_cols = [c for c in always_include + metric_cols
                   if c in snapshot.columns]

    return snapshot[output_cols].reset_index(drop=True)

    return snapshot[output_cols].reset_index(drop=True)


# ═════════════════════════════════════════════════════════════════════════════
# QUICK TEST WITH SYNTHETIC DATA
# ═════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import numpy as np

    np.random.seed(42)
    n_athletes = 5
    n_weeks    = 8

    # Simulate a season of ForceDecks data
    records = []
    for athlete_id in range(1, n_athletes + 1):
        for week in range(n_weeks):
            records.append({
                "athlete_id":            f"Athlete_{athlete_id:02d}",
                "date":                  pd.Timestamp("2025-01-06")
                                         + pd.Timedelta(weeks=week),
                "jump_height":           np.random.normal(22, 2),
                "rsim":                  np.random.normal(0.45, 0.05),
                "ecc_braking_rfd_bm":    np.random.normal(180, 15),
                "peak_power_bm":         np.random.normal(1400, 120),
                "contraction_time":      np.random.normal(680, 40),
            })

    # Inject a fatigued athlete on the last testing day
    records[-1]["jump_height"]           *= 0.85   # -15% → RED
    records[-1]["contraction_time"]      *= 1.12   # +12% → RED
    records[-2]["rsim"]                  *= 0.91   # -9%  → YELLOW

    df_raw = pd.DataFrame(records)

    # Run pipeline
    df_processed = process_cmj_data(df_raw)

    # Show latest snapshot
    snapshot = get_dashboard_snapshot(df_processed)

    print("=== Dashboard Snapshot — Most Recent Testing Day ===\n")
    print(snapshot[["athlete_id", "overall_light",
                     "baseline_warning", "flagged_metrics"]].to_string(index=False))

    print("\n=== Detailed Deviations ===\n")
    dev_cols = ["athlete_id"] + [f"{m}_deviation" for m in METRIC_CONFIG
                                  if f"{m}_deviation" in df_processed.columns]
    print(snapshot[dev_cols].round(2).to_string(index=False))