# vald_config.py
import os
from dotenv import load_dotenv

load_dotenv()  # reads your .env file automatically

# ── Credentials ───────────────────────────────────────────────────────────────
CLIENT_ID     = os.getenv("VALD_CLIENT_ID")
CLIENT_SECRET = os.getenv("VALD_CLIENT_SECRET")
TENANT_ID     = os.getenv("VALD_TENANT_ID")
GOOGLE_SHEET_NAME = os.getenv("GOOGLE_SHEET_NAME")
SERVICE_ACCOUNT_FILE = os.getenv("SERVICE_ACCOUNT_FILE")

# ── URLs ──────────────────────────────────────────────────────────────────────
AUTH_URL       = "https://auth.prd.vald.com/oauth/token"
BASE_URL       = "https://prd-use-api-externaltenants.valdperformance.com"
FORCEDECKS_URL = "https://prd-use-api-extforcedecks.valdperformance.com"
PROFILES_URL   = "https://prd-use-api-externalprofile.valdperformance.com"

# ── ForceDecks Result IDs (confirmed from live trials data) ───────────────────
RESULT_IDS = {
    "jump_height":          6553613,   # Jump Height (Flight Time) in Inches
    "rsim":                 6553698,   # RSI-modified — m/s
    "ecc_braking_rfd_bm":  6553679,   # Eccentric Braking RFD / BM — N/s/kg
    "peak_power_bm":        6553604,   # Peak Power / BM — W/kg
    "contraction_time":     6553643,   # Contraction Time — ms
}

# ── Bonus: store EDI for seasonal analysis (not in traffic light) ─────────────
RESULT_IDS_SECONDARY = {
    "ecc_decel_impulse_bm": 6553730,   # Eccentric Deceleration Impulse / BM
}

# ── Reverse lookup ────────────────────────────────────────────────────────────
RESULT_ID_TO_METRIC = {v: k for k, v in RESULT_IDS.items()}

# ── Group IDs ─────────────────────────────────────────────────────────────────
GROUPS = {
    "womens_lacrosse": "b1bf664f-8f0f-4ed8-8cfc-9412e5255aa9",
    "mens_ice_hockey": "ff91e5dc-7426-47ae-bac8-38e660d09403",
    "field_hockey":    "f07af387-e499-4929-bfe4-065b62b06019",
    "mens_soccer":     "b4ae6de0-772b-409f-9c44-514c6cc3c0e3",
}

# ── Category IDs ──────────────────────────────────────────────────────────────
CATEGORIES = {
    "au_sports":     "f64b25b7-09ae-47f7-9466-d00c452e7bdd",
    "uncategorised": "d9f8952e-53ca-4d0f-90dd-b615d92c55b9",
}