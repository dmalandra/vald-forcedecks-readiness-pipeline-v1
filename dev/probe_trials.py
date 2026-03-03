# probe_trials.py
import requests
import json
from vald_auth import get_headers
from vald_config import TENANT_ID, FORCEDECKS_URL, RESULT_IDS, RESULT_ID_TO_METRIC, GROUPS

FD_BASE  = FORCEDECKS_URL
headers  = get_headers()

# ── Step 1: Pull CMJ tests only ───────────────────────────────────────────────
print("Fetching CMJ tests since Jan 2025...\n")

r = requests.get(
    f"{FD_BASE}/tests",
    headers=headers,
    params={
        "TenantId":        TENANT_ID,
        "ModifiedFromUtc": "2025-01-01T00:00:00Z",
    }
)

tests     = r.json().get("tests", [])
cmj_tests = [t for t in tests if t.get("testType") == "CMJ"]
print(f"Total tests: {len(tests)}  |  CMJ tests: {len(cmj_tests)}\n")

if not cmj_tests:
    print("No CMJ tests found. Check date range or testType filter.")
    exit()

# ── Step 2: Check parameter field on CMJ tests ───────────────────────────────
print("Checking parameter field on first 3 CMJ tests:")
for t in cmj_tests[:3]:
    param    = t.get("parameter")
    ext      = t.get("extendedParameters", [])
    notes    = t.get("notes", "")
    print(f"  testId: {t['testId']}")
    print(f"  profileId: {t['profileId']}")
    print(f"  recordedDateUtc: {t['recordedDateUtc']}")
    print(f"  parameter: {param}")
    print(f"  extendedParameters count: {len(ext)}")
    if ext:
        print(f"  extendedParameters: {json.dumps(ext, indent=4)}")
    print()

# ── Step 3: Try trials endpoint for first CMJ test ───────────────────────────
# Note: trials endpoint uses the old v2019q3 path and needs teamId
# We need to find the correct teamId — try with the Women's Lacrosse group ID
# as teamId (they may be the same concept in the old API)

LACROSSE_GROUP_ID = GROUPS["womens_lacrosse"]
first_cmj         = cmj_tests[0]
test_id           = first_cmj["testId"]

print(f"\nFetching trials for testId: {test_id}")
print(f"Using teamId (groupId): {LACROSSE_GROUP_ID}\n")

r2 = requests.get(
    f"{FD_BASE}/v2019q3/teams/{LACROSSE_GROUP_ID}/tests/{test_id}/trials",
    headers=headers
)
print(f"Trials status: {r2.status_code}")

if r2.status_code == 200:
    trials = r2.json()
    print(f"Trials returned: {len(trials)}\n")
    for trial in trials[:2]:
        print(json.dumps(trial, indent=2))
elif r2.status_code in [400, 404]:
    print(f"Response: {r2.text[:500]}")

# ── Step 4: Also try fetching all tests for lacrosse team via old endpoint ────
print(f"\n\nTrying old team tests endpoint for lacrosse group...")
from datetime import datetime, timezone
modified_from = "2025-01-01T00:00:00Z"

r3 = requests.get(
    f"{FD_BASE}/v2019q3/teams/{LACROSSE_GROUP_ID}/tests/1",
    headers=headers,
    params={"modifiedFrom": modified_from}
)
print(f"Status: {r3.status_code}")
if r3.status_code == 200:
    data = r3.json()
    items = data.get("items", [])
    print(f"Tests returned: {len(items)}")
    if items:
        print("\nFirst test structure:")
        print(json.dumps(items[0], indent=2))
else:
    print(f"Response: {r3.text[:300]}")