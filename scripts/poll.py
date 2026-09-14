#!/usr/bin/env python3
"""Poll OpenSky for Egypt bbox -> SQLite + alerts. Loop or --once.

Usage: conda run -n petro python scripts/poll.py [--once]
Runs forever every poll_seconds (respect OpenSky anonymous limits: keep >=10s).
"""
import sys
import time
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from airwatch import opensky, store, alerts

ROOT = Path(__file__).resolve().parents[1]


def _status(state, tracks=0, detail=""):
    import json
    try:
        (ROOT / "data" / "feed_status.json").write_text(json.dumps({
            "ts": int(time.time()), "state": state,
            "tracks": tracks, "detail": detail[:160]}))
    except Exception:
        pass


def one_cycle(cfg, con):
    snap, tracks = opensky.fetch(cfg["bbox"])
    if snap == -429:
        _status("ratelimit", 0, "HTTP 429 — anonymous quota exhausted, backing off")
        return "ratelimit"  # caller backs off; nothing stored
    known = {r["icao24"] for r in store.latest_snapshot(con)} if False else set()
    # known = tracks seen in any earlier snapshot
    cur = con.cursor()
    cur.execute("SELECT icao24 FROM tracks")
    known = {r[0] for r in cur.fetchall()}
    store.ingest(con, tracks, snap)
    n_alerts = 0
    for kind, t, detail in alerts.evaluate(tracks, known, cfg):
        if store.add_alert(con, kind, t, detail):
            n_alerts += 1
            print(f"ALERT {kind} {t.get('callsign') or t['icao24']} {detail}", flush=True)
    _status("ok" if tracks else "empty", len(tracks), f"snapshot {snap}")
    print(f"snapshot {snap}: {len(tracks)} tracks, {n_alerts} new alerts", flush=True)


def main():
    cfg = yaml.safe_load(open(ROOT / "config" / "zones.yaml"))
    con = store.connect(ROOT / cfg.get("db", "data/tracks.db"))
    if "--once" in sys.argv:
        one_cycle(cfg, con)
        return
    interval = int(cfg.get("poll_seconds", 300))
    import os as _os
    if _os.getenv("OPENSKY_USER"):
        print("OpenSky account auth ON (4000 req/day)")
    else:
        print("Anonymous mode: keep interval >=300s or create a free OpenSky account "
              "and set OPENSKY_USER/OPENSKY_PASS")
    print(f"polling every {interval}s — Ctrl+C to stop")
    backoff = 0
    while True:
        try:
            res = one_cycle(cfg, con)
            backoff = 900 if res == "ratelimit" else 0
        except Exception as e:
            _status("error", 0, f"{type(e).__name__}: {str(e)[:120]}")
            print(f"cycle failed: {type(e).__name__}: {str(e)[:150]}", flush=True)
        time.sleep(interval + backoff)


if __name__ == "__main__":
    main()
