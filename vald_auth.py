# vald_auth.py
import time
import requests
from vald_config import CLIENT_ID, CLIENT_SECRET, AUTH_URL

# ── Token cache — avoids requesting a new token on every API call ─────────────
_token_cache = {
    "access_token": None,
    "expires_at":   0       # Unix timestamp
}

def get_access_token():
    """
    Returns a valid Bearer token, requesting a new one only if the
    current token is missing or within 60 seconds of expiry.
    """
    now = time.time()

    if _token_cache["access_token"] and now < _token_cache["expires_at"] - 60:
        return _token_cache["access_token"]   # reuse cached token

    print("Requesting new VALD access token...")
    r = requests.post(
        AUTH_URL,
        data={
            "grant_type":    "client_credentials",
            "client_id":     CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "audience":      "vald-api-external",
        }
    )
    r.raise_for_status()
    data = r.json()

    _token_cache["access_token"] = data["access_token"]
    _token_cache["expires_at"]   = now + data["expires_in"]

    print("Token acquired successfully.")
    return _token_cache["access_token"]


def get_headers():
    """Returns the Authorization headers needed for every API call."""
    return {"Authorization": f"Bearer {get_access_token()}"}