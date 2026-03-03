# probe_forcedecks.py
import requests
from vald_auth import get_headers
from vald_config import TENANT_ID

headers  = get_headers()
base     = "https://prd-use-api-extforcedecks.valdperformance.com"

# ── Find the Swagger/OpenAPI spec ─────────────────────────────────────────────
swagger_paths = [
    "/swagger/v1/swagger.json",
    "/swagger/v2/swagger.json",
    "/swagger/index.html",
    "/openapi/v1.json",
    "/openapi.json",
    "/api-docs",
    "/api-docs/v1",
    "/v1/swagger.json",
    "/v2/swagger.json",
]

print("Searching for ForceDecks API spec...\n")
for path in swagger_paths:
    r = requests.get(f"{base}{path}", headers=headers, timeout=5)
    print(f"{r.status_code}  →  {path}")
    if r.status_code == 200:
        print(f"         FOUND! First 300 chars: {r.text[:300]}\n")

# ── Try common data endpoint patterns ─────────────────────────────────────────
print("\nProbing data endpoints...\n")
endpoints = [
    f"/tests?TenantId={TENANT_ID}",
    f"/testresults?TenantId={TENANT_ID}",
    f"/forcedecks?TenantId={TENANT_ID}",
    f"/cmj?TenantId={TENANT_ID}",
    f"/results?TenantId={TENANT_ID}",
    f"/v1/tests?TenantId={TENANT_ID}",
    f"/v2/tests?TenantId={TENANT_ID}",
    f"/athlete/tests?TenantId={TENANT_ID}",
    f"/athletes?TenantId={TENANT_ID}",
    f"/v1/athletes?TenantId={TENANT_ID}",
]

for ep in endpoints:
    r = requests.get(f"{base}{ep}", headers=headers, timeout=5)
    print(f"{r.status_code}  →  {ep}")
    if r.status_code == 200:
        print(f"         {r.text[:300]}\n")