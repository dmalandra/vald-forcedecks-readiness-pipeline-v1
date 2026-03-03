# probe_apis.py
import requests
import json
from vald_auth import get_headers

headers = get_headers()

apis = {
    "ForceDecks": "https://prd-use-api-extforcedecks.valdperformance.com",
    "Profiles":   "https://prd-use-api-externalprofile.valdperformance.com",
    "Tenants":    "https://prd-use-api-externaltenants.valdperformance.com",
}

for name, base in apis.items():
    print(f"\n{'='*60}")
    print(f"{name}: {base}")
    print('='*60)

    # Check version
    try:
        r = requests.get(f"{base}/version", headers=headers, timeout=5)
        print(f"Version: {r.status_code} — {r.text.strip()}")
    except Exception as e:
        print(f"Version: FAILED — {e}")

    # Pull OpenAPI spec
    try:
        r = requests.get(f"{base}/swagger/v1/swagger.json",
                         headers=headers, timeout=5)
        if r.status_code == 200:
            spec = r.json()
            print(f"Endpoints:")
            for path in spec["paths"].keys():
                # Show HTTP methods for each path
                methods = list(spec["paths"][path].keys())
                print(f"  {str(methods):20s}  {path}")
        else:
            print(f"Swagger: {r.status_code} — {r.text[:200]}")
    except Exception as e:
        print(f"Swagger: FAILED — {e}")