"""Alert rules over one snapshot."""
import math


def _km(lon1, lat1, lon2, lat2):
    dx = (lon1 - lon2) * 111.32 * math.cos(math.radians((lat1 + lat2) / 2))
    dy = (lat1 - lat2) * 110.57
    return math.hypot(dx, dy)


def evaluate(tracks, known_icao, cfg):
    """Yield (kind, track, detail). known_icao = set seen before this snapshot."""
    rules = cfg.get("alerts", {})
    emg = set(rules.get("emergency_squawks", []))
    low_m = float(rules.get("low_altitude_m", 3000))
    ap_rad = float(rules.get("airport_radius_km", 25))
    airports = cfg.get("airports", [])
    out = []
    for t in tracks:
        sq = (t.get("squawk") or "").strip()
        if sq in emg:
            out.append(("EMERGENCY", t, f"squawk {sq}"))
        if rules.get("new_entrant") and t["icao24"] not in known_icao:
            out.append(("NEW ENTRANT", t, f"first seen {t.get('callsign', '') or t['icao24']}"))
        alt = t.get("baro_alt")
        if alt is not None and not t.get("on_ground") and alt < low_m:
            near = min([_km(t["lon"], t["lat"], a["lon"], a["lat"]) for a in airports], default=1e9)
            if near > ap_rad:
                out.append(("LOW ALTITUDE", t, f"{alt:.0f} m, {near:.0f} km from nearest airport"))
    return out
