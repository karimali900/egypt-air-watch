"""OpenSky Network live states client (free, no key). Anonymous: ~100 req/day.

State vector fields used: icao24, callsign, lon, lat, baro_altitude,
velocity, heading, squawk, spi, position time.
"""
import os
import time

import requests

API = "https://opensky-network.org/api/states/all"
UA = {"User-Agent": "egypt-air-watch/1.0 (research dashboard)"}


def _load_dotenv():
    try:
        from pathlib import Path
        for line in (Path(__file__).resolve().parents[2] / ".env").read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip("'\""))
    except Exception:
        pass


_load_dotenv()
_TOKEN = {"tok": "", "exp": 0.0}


def _auth():
    u, p = os.getenv("OPENSKY_USER", ""), os.getenv("OPENSKY_PASS", "")
    return (u, p) if u and p else None


def _bearer():
    """OAuth2 client-credentials token (OPENSKY_CLIENT_ID/SECRET). Cached."""
    import time as _t
    cid, sec = os.getenv("OPENSKY_CLIENT_ID", ""), os.getenv("OPENSKY_CLIENT_SECRET", "")
    if not (cid and sec):
        return ""
    if _TOKEN["tok"] and _TOKEN["exp"] > _t.time() + 60:
        return _TOKEN["tok"]
    try:
        r = requests.post(
            "https://auth.opensky-network.org/auth/realms/opensky-network/protocol/openid-connect/token",
            data={"grant_type": "client_credentials", "client_id": cid, "client_secret": sec},
            timeout=30)
        r.raise_for_status()
        d = r.json()
        _TOKEN["tok"] = d["access_token"]
        _TOKEN["exp"] = _t.time() + int(d.get("expires_in", 1800))
        return _TOKEN["tok"]
    except Exception as e:
        print(f"OpenSky OAuth failed: {type(e).__name__}: {str(e)[:120]}")
        return ""

FIELDS = ["icao24", "callsign", "origin", "time_position", "last_contact",
          "lon", "lat", "baro_alt", "on_ground", "velocity", "heading",
          "vertical_rate", "sensors", "geo_alt", "squawk", "spi", "pos_src"]


def fetch(bbox, timeout=30):
    """Return (server_time, [track dicts]) inside bbox. Empty list on failure."""
    lon_min, lat_min, lon_max, lat_max = bbox
    try:
        hdrs = dict(UA)
        tok = _bearer()
        if tok:
            hdrs["Authorization"] = f"Bearer {tok}"
        r = requests.get(API, params={"lamin": lat_min, "lomin": lon_min,
                                      "lamax": lat_max, "lomax": lon_max},
                         headers=hdrs, timeout=timeout,
                         auth=None if tok else _auth())
        if r.status_code == 429:
            print("OpenSky 429 rate-limited (anonymous quota) — backing off")
            return -429, []
        r.raise_for_status()
        d = r.json()
    except Exception as e:
        print(f"OpenSky fetch failed: {type(e).__name__}: {str(e)[:120]}")
        return int(time.time()), []
    out = []
    for s in d.get("states") or []:
        rec = dict(zip(FIELDS, s))
        if rec["lon"] is None or rec["lat"] is None:
            continue
        rec["callsign"] = (rec["callsign"] or "").strip()
        rec["snapshot"] = int(d.get("time", time.time()))
        out.append(rec)
    return int(d.get("time", time.time())), out
