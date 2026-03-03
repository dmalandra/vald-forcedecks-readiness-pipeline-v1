# explore_forcedecks.py
import requests
import json
from datetime import datetime, timezone
from vald_auth import get_headers
from vald_config import TENANT_ID, GROUPS

FD_BASE = "https://prd-use-api-extforcedecks.valdperformance.com"
headers = get_headers()

# ── Step 1: Pull result definitions (metric ID → name mapping) ────────────────
print("=" * 60)
print("RESULT DEFINITIONS (metric ID → name)")
print("=" * 60)

r = requests.get(f"{FD_BASE}/resultdefinitions", headers=headers)
print(f"Status: {r.status_code}\n")

if r.status_code == 200:
    defs = r.json().get("resultDefinitions", [])
    print(f"Total result definitions: {len(defs)}\n")

    # Print all definitions so we can find our metric IDs
    for d in sorted(defs, key=lambda x: x["resultId"]):
        print(f"  ID {d['resultId']:4d}  |  {d.get('resultName',''):45s}  "
              f"|  {d.get('resultGroup',''):15s}  "
              f"|  {d.get('resultUnitName','')}")

# ── Step 2: Pull recent tests for Women's Lacrosse ────────────────────────────
print("\n" + "=" * 60)
print("RECENT TESTS — Women's Lacrosse")
print("=" * 60)

# ModifiedFromUtc: pull everything from start of 2025 season
modified_from = "2025-01-01T00:00:00Z"

r = requests.get(
    f"{FD_BASE}/tests",
    headers=headers,
    params={
        "TenantId":        TENANT_ID,
        "ModifiedFromUtc": modified_from,
    }
)
print(f"Status: {r.status_code}\n")

if r.status_code == 200:
    data   = r.json()
    tests  = data.get("tests", [])
    print(f"Total tests returned: {len(tests)}\n")

    if tests:
        # Show first 3 tests in full to understand structure
        print("First 3 tests (full structure):")
        for t in tests[:3]:
            print(json.dumps(t, indent=2))
            print()

elif r.status_code == 400:
    print(f"400 error: {r.text}")