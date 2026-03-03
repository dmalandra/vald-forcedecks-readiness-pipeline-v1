# vald_client.py
"""
VALD API Client
---------------
Handles all data retrieval from the three VALD APIs:
    - Tenants API:    groups, categories
    - Profiles API:   athlete name → profileId mapping
    - ForceDecks API: CMJ test results

Data pull strategy:
    - Uses /v2019q3/teams/{teamId}/tests/detailed/{dateFrom}/{dateTo}
    - Extracts trial results and parses target result IDs
    - Selects best jump trial (highest jump height)
    - Optionally excludes first trial if >15% below best
"""

import requests
from datetime import datetime, timezone, timedelta
from vald_auth import get_headers
from vald_config import (
    BASE_URL, FORCEDECKS_URL, PROFILES_URL,
    TENANT_ID, GROUPS, RESULT_IDS, RESULT_ID_TO_METRIC,
    RESULT_IDS_SECONDARY
)

# ── Constants ─────────────────────────────────────────────────────────────────
TEAM_ID = TENANT_ID   # ForceDecks v2019q3 uses tenantId as teamId


# ═════════════════════════════════════════════════════════════════════════════
# ORGANISATIONAL ENDPOINTS
# ═════════════════════════════════════════════════════════════════════════════

def get_groups():
    """Returns all groups (teams/sports) in the tenant."""
    r = requests.get(
        f"{BASE_URL}/groups",
        headers=get_headers(),
        params={"TenantId": TENANT_ID}
    )
    r.raise_for_status()
    return r.json()["groups"]


def get_categories():
    """Returns all categories."""
    r = requests.get(
        f"{BASE_URL}/categories",
        headers=get_headers(),
        params={"TenantId": TENANT_ID}
    )
    r.raise_for_status()
    return r.json()["categories"]


# ═════════════════════════════════════════════════════════════════════════════
# PROFILES — athlete name → profileId mapping
# ═════════════════════════════════════════════════════════════════════════════

def get_profiles(group_id=None):
    """
    Returns all athlete profiles, optionally filtered by group.

    Args:
        group_id: optional VALD group UUID to filter by sport

    Returns:
        List of profile dicts with id, givenName, familyName, name
    """
    params = {"TenantId": TENANT_ID}
    if group_id:
        params["GroupId"] = group_id

    r = requests.get(
        f"{PROFILES_URL}/profiles",
        headers=get_headers(),
        params=params
    )
    r.raise_for_status()
    return r.json().get("profiles", [])


def build_profile_map(group_id=None):
    """
    Builds a lookup dict: ForceDecks athleteId → full name.
    Uses the ForceDecks athletes endpoint which has the correct IDs
    that match what appears in test records.

    For group filtering, cross-references with the Profiles API
    since ForceDecks athletes endpoint doesn't support group filtering.

    Args:
        group_id: optional VALD group UUID to filter by sport

    Returns:
        dict {forcedecks_athlete_id: "First Last"}
    """
    # Get all ForceDecks athletes (has correct IDs + names)
    r = requests.get(
        f"{FORCEDECKS_URL}/v2019q3/teams/{TEAM_ID}/athletes",
        headers=get_headers()
    )
    r.raise_for_status()
    fd_athletes = r.json()

    # Build FD id → name map
    fd_map = {
        a.get("id"): a.get("name", "").strip()
        for a in fd_athletes
        if a.get("id")
    }

    # If no group filter, return all
    if not group_id:
        return fd_map

    # Get Profiles API IDs for this group (hubId = profileId)
    r2 = requests.get(
        f"{PROFILES_URL}/profiles",
        headers=get_headers(),
        params={"TenantId": TENANT_ID, "GroupId": group_id}
    )
    r2.raise_for_status()
    group_profile_ids = {
        p.get("profileId")
        for p in r2.json().get("profiles", [])
    }

    # ForceDecks hubId matches Profiles API profileId
    # Filter FD athletes to only those in this group
    r3 = requests.get(
        f"{FORCEDECKS_URL}/v2019q3/teams/{TEAM_ID}/athletes",
        headers=get_headers()
    )
    fd_athletes_full = r3.json()

    filtered_map = {
        a.get("id"): a.get("name", "").strip()
        for a in fd_athletes_full
        if a.get("hubId") in group_profile_ids and a.get("id")
    }

    return filtered_map


# ═════════════════════════════════════════════════════════════════════════════
# TRIAL PARSING
# ═════════════════════════════════════════════════════════════════════════════

def parse_trial_metrics(trial):
    """
    Extracts target metric values from a single trial's results array.

    Args:
        trial: trial dict from ForceDecks API

    Returns:
        dict {metric_key: value} for all result IDs found in RESULT_IDS
        Also includes secondary metrics from RESULT_IDS_SECONDARY
    """
    all_target_ids = {**RESULT_IDS, **RESULT_IDS_SECONDARY}
    id_to_key      = {v: k for k, v in all_target_ids.items()}
    metrics        = {}

    for result in trial.get("results", []):
        rid = result.get("resultId")
        if rid in id_to_key:
            metrics[id_to_key[rid]] = result.get("value")

    return metrics


def select_best_trial(trials, exclude_cold_first=True, cold_threshold=0.15):
    """
    Selects the best trial from a list based on highest jump height.

    Args:
        trials:            list of trial dicts from ForceDecks API
        exclude_cold_first: if True, excludes trial 1 if it's more than
                            cold_threshold below the best trial
        cold_threshold:    fraction below best that triggers exclusion (0.15 = 15%)

    Returns:
        dict of parsed metrics from the best trial, or {} if no valid trials
    """
    if not trials:
        return {}

    jump_height_id = RESULT_IDS.get("jump_height")

    # Parse all trials
    parsed = []
    for trial in trials:
        metrics = parse_trial_metrics(trial)
        jh      = metrics.get("jump_height")
        parsed.append((jh, metrics))

    # Find best jump height across all trials
    valid      = [(jh, m) for jh, m in parsed if jh is not None]
    if not valid:
        return {}

    best_jh    = max(jh for jh, _ in valid)

    # Optionally exclude cold first trial
    if exclude_cold_first and len(valid) > 1:
        first_jh = valid[0][0]
        if first_jh < best_jh * (1 - cold_threshold):
            valid = valid[1:]   # drop first trial

    # Return metrics from the trial with the highest jump height
    best_metrics = max(valid, key=lambda x: x[0])[1]
    return best_metrics


# ═════════════════════════════════════════════════════════════════════════════
# FORCEDECKS DATA PULL
# ═════════════════════════════════════════════════════════════════════════════

def get_cmj_tests(date_from, date_to):
    """
    Pulls all detailed CMJ tests across the entire tenant for a date range.

    Args:
        date_from: ISO datetime string e.g. "2026-01-06T00:00:00Z"
        date_to:   ISO datetime string e.g. "2026-01-06T23:59:59Z"

    Returns:
        List of raw test dicts (testType == "CMJ" only)
    """
    r = requests.get(
        f"{FORCEDECKS_URL}/v2019q3/teams/{TEAM_ID}/tests/detailed"
        f"/{date_from}/{date_to}",
        headers=get_headers()
    )
    r.raise_for_status()
    data = r.json()
    return [t for t in data if t.get("testType") == "CMJ"]


def get_cmj_results(sport_key, date_from=None, date_to=None,
                     exclude_cold_first=True):
    """
    Master function — pulls CMJ tests for a sport and returns a clean
    DataFrame-ready list of records with athlete names and parsed metrics.

    Args:
        sport_key:          e.g. "womens_lacrosse"
        date_from:          ISO date string e.g. "2026-01-06"
                            defaults to today
        date_to:            ISO date string e.g. "2026-01-06"
                            defaults to today
        exclude_cold_first: exclude cold first trial if >15% below best

    Returns:
        List of dicts, one per athlete per test session:
        {
            "athlete_id":   profileId,
            "athlete_name": "First Last",
            "date":         date string,
            "weight_kg":    float,
            "jump_height":  float (inches),
            "rsim":         float,
            "ecc_braking_rfd_bm": float,
            "peak_power_bm": float,
            "contraction_time": float,
            "ecc_decel_impulse_bm": float (secondary),
            "best_trial":   int (1-indexed)
        }
    """
    # Default to today
    if date_from is None:
        date_from = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if date_to is None:
        date_to = date_from

    date_from_utc = f"{date_from}T00:00:00Z"
    date_to_utc   = f"{date_to}T23:59:59Z"

    # Get group ID for this sport
    group_id = GROUPS.get(sport_key)
    if not group_id:
        raise ValueError(f"Unknown sport key '{sport_key}'. "
                         f"Available: {list(GROUPS.keys())}")

    # Build profile map for athlete name lookup
    print(f"Building profile map for {sport_key}...")
    profile_map = build_profile_map(group_id)
    print(f"  {len(profile_map)} athletes found\n")

    # Pull CMJ tests
    print(f"Pulling CMJ tests {date_from} → {date_to}...")
    all_cmj = get_cmj_tests(date_from_utc, date_to_utc)
    print(f"  {len(all_cmj)} total CMJ tests in tenant\n")

    # Filter to athletes in this sport's group
    sport_profile_ids = set(profile_map.keys())
    sport_cmj         = [t for t in all_cmj
                         if t.get("profileId") in sport_profile_ids
                         or t.get("athleteId") in sport_profile_ids]
    print(f"  {len(sport_cmj)} CMJ tests for {sport_key}\n")

    # Parse each test
    records = []
    for test in sport_cmj:
        profile_id   = test.get("profileId") or test.get("athleteId")
        athlete_name = profile_map.get(profile_id, f"Unknown ({profile_id})")
        recorded_utc = test.get("recordedUTC", "")
        date_str     = recorded_utc[:10] if recorded_utc else date_from
        weight_kg    = test.get("weight")
        test_id      = test.get("id")

        # Always fetch trials from separate endpoint
        # The detailed endpoint embeds trial structure but strips metric values
        r = requests.get(
            f"{FORCEDECKS_URL}/v2019q3/teams/{TEAM_ID}/tests/{test_id}/trials",
            headers=get_headers()
        )
        trials = r.json() if r.status_code == 200 else []

        # Select best trial
        best_metrics = select_best_trial(
            trials,
            exclude_cold_first=exclude_cold_first
        )

        if not best_metrics:
            print(f"  WARNING: No valid trials for {athlete_name} on {date_str}")
            continue

        # Find which trial index was selected
        best_jh    = best_metrics.get("jump_height")
        best_trial = 1
        for i, trial in enumerate(trials):
            m = parse_trial_metrics(trial)
            if m.get("jump_height") == best_jh:
                best_trial = i + 1
                break

        record = {
            "athlete_id":           profile_id,
            "athlete_name":         athlete_name,
            "date":                 date_str,
            "weight_kg":            weight_kg,
            "jump_height":          best_metrics.get("jump_height"),
            "rsim":                 best_metrics.get("rsim"),
            "ecc_braking_rfd_bm":  best_metrics.get("ecc_braking_rfd_bm"),
            "peak_power_bm":        best_metrics.get("peak_power_bm"),
            "contraction_time":     best_metrics.get("contraction_time"),
            "ecc_decel_impulse_bm": best_metrics.get("ecc_decel_impulse_bm"),
            "best_trial":           best_trial,
        }
        records.append(record)
    print(f"Parsed {len(records)} athlete records successfully.")
    return records

def get_cmj_season(sport_key, season_start, season_end,
                    exclude_cold_first=True):
    """
    Pulls the full season of CMJ data for a sport.
    Useful for building rolling baselines and retrospective analysis.

    Args:
        sport_key:    e.g. "womens_lacrosse"
        season_start: ISO date string e.g. "2026-01-01"
        season_end:   ISO date string e.g. "2026-04-30"

    Returns:
        Same format as get_cmj_results() but across entire season
    """
    return get_cmj_results(
        sport_key,
        date_from=season_start,
        date_to=season_end,
        exclude_cold_first=exclude_cold_first
    )


# ═════════════════════════════════════════════════════════════════════════════
# QUICK TEST
# ═════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":

    print("=" * 60)
    print("Testing VALD client — known good test Feb 25")
    print("=" * 60 + "\n")

    # Add womens_soccer temporarily to GROUPS for this test
    from vald_config import GROUPS
    GROUPS["womens_soccer"] = "fd5edad9-1293-4276-844f-d44107b47d3b"

    records = get_cmj_results(
        sport_key = "womens_soccer",
        date_from = "2026-02-25",
        date_to   = "2026-02-25",
    )

    print(f"\nResults: {len(records)} records")
    for r in records:
        print(f"\n  {r['athlete_name']:25s}  {r['date']}")
        print(f"    Jump Height:        {r['jump_height']:.2f} in"
              if r['jump_height'] else "    Jump Height:        —")
        print(f"    RSImod:             {r['rsim']:.3f}"
              if r['rsim'] else "    RSImod:             —")
        print(f"    Ecc Braking RFD/BM: {r['ecc_braking_rfd_bm']:.2f}"
              if r['ecc_braking_rfd_bm'] else "    Ecc Braking RFD/BM: —")
        print(f"    Peak Power/BM:      {r['peak_power_bm']:.2f}"
              if r['peak_power_bm'] else "    Peak Power/BM:      —")
        print(f"    Contraction Time:   {r['contraction_time']:.4f} s"
              if r['contraction_time'] else "    Contraction Time:   —")
        print(f"    Best Trial:         {r['best_trial']}")