"""SQLite track + alert store."""
import sqlite3
import time
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS positions(
  icao24 TEXT, callsign TEXT, snapshot INTEGER,
  lon REAL, lat REAL, baro_alt REAL, velocity REAL, heading REAL,
  squawk TEXT, on_ground INTEGER,
  PRIMARY KEY (icao24, snapshot));
CREATE TABLE IF NOT EXISTS tracks(
  icao24 TEXT PRIMARY KEY, callsign TEXT, first_seen INTEGER, last_seen INTEGER);
CREATE TABLE IF NOT EXISTS alerts(
  id INTEGER PRIMARY KEY AUTOINCREMENT, ts INTEGER, kind TEXT,
  icao24 TEXT, callsign TEXT, detail TEXT, seen INTEGER DEFAULT 0);
"""


def connect(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.executescript(SCHEMA)
    return con


def ingest(con, tracks, snapshot):
    cur = con.cursor()
    for t in tracks:
        cur.execute("INSERT OR IGNORE INTO positions VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (t["icao24"], t["callsign"], t["snapshot"], t["lon"], t["lat"],
                     t["baro_alt"], t["velocity"], t["heading"],
                     t["squawk"], 1 if t["on_ground"] else 0))
        cur.execute("SELECT first_seen FROM tracks WHERE icao24=?", (t["icao24"],))
        row = cur.fetchone()
        if row is None:
            cur.execute("INSERT INTO tracks VALUES (?,?,?,?)",
                        (t["icao24"], t["callsign"], snapshot, snapshot))
        else:
            cur.execute("UPDATE tracks SET last_seen=?, callsign=? WHERE icao24=?",
                        (snapshot, t["callsign"] or "", t["icao24"]))
    con.commit()


def add_alert(con, kind, track, detail):
    # de-dupe: same kind+icao within 30 min
    cur = con.cursor()
    cur.execute("SELECT id FROM alerts WHERE kind=? AND icao24=? AND ts>?",
                (kind, track["icao24"], int(time.time()) - 1800))
    if cur.fetchone():
        return False
    cur.execute("INSERT INTO alerts (ts, kind, icao24, callsign, detail) VALUES (?,?,?,?,?)",
                (int(time.time()), kind, track["icao24"], track.get("callsign", ""), detail))
    con.commit()
    return True


def latest_snapshot(con):
    cur = con.cursor()
    cur.execute("SELECT icao24, callsign, snapshot, lon, lat, baro_alt, velocity, heading, squawk, on_ground FROM positions WHERE snapshot=(SELECT MAX(snapshot) FROM positions)")
    cols = ["icao24", "callsign", "snapshot", "lon", "lat", "baro_alt", "velocity", "heading", "squawk", "on_ground"]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def recent_alerts(con, limit=50):
    cur = con.cursor()
    cur.execute("SELECT ts, kind, icao24, callsign, detail FROM alerts ORDER BY ts DESC LIMIT ?", (limit,))
    return [{"ts": r[0], "kind": r[1], "icao24": r[2], "callsign": r[3], "detail": r[4]} for r in cur.fetchall()]


def track_history(con, icao24, limit=500):
    cur = con.cursor()
    cur.execute("SELECT snapshot, lon, lat, baro_alt, velocity, heading FROM positions WHERE icao24=? ORDER BY snapshot DESC LIMIT ?", (icao24, limit))
    return [{"snapshot": r[0], "lon": r[1], "lat": r[2], "baro_alt": r[3], "velocity": r[4], "heading": r[5]} for r in cur.fetchall()]
