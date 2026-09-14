#!/usr/bin/env python3
"""Export tracks/alerts: CSV always; KML for Google Earth.
Usage: python scripts/export.py [--icao ABC123] [--kml]"""
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from airwatch import store

ROOT = Path(__file__).resolve().parents[1]


def main():
    import pandas as pd
    cfg = yaml.safe_load(open(ROOT / "config" / "zones.yaml"))
    con = store.connect(ROOT / cfg.get("db", "data/tracks.db"))
    out = ROOT / "data"
    if "--icao" in sys.argv:
        icao = sys.argv[sys.argv.index("--icao") + 1].lower()
        hist = store.track_history(con, icao, 5000)
        df = pd.DataFrame(hist)
        p = out / f"track_{icao}.csv"
        df.to_csv(p, index=False)
        print(f"{len(df)} points -> {p}")
        if "--kml" in sys.argv:
            k = out / f"track_{icao}.kml"
            coords = " ".join(f"{r['lon']},{r['lat']},{r['baro_alt'] or 0}" for _, r in df.iloc[::-1].iterrows())
            k.write_text(f'<?xml version="1.0"?><kml xmlns="http://www.opengis.net/kml/2.2"><Document><name>{icao}</name><Placemark><LineString><coordinates>{coords}</coordinates></LineString></Placemark></Document></kml>')
            print(f"KML -> {k}")
    else:
        df = pd.DataFrame(store.latest_snapshot(con))
        p = out / "snapshot_latest.csv"
        df.to_csv(p, index=False)
        print(f"{len(df)} tracks -> {p}")
        al = pd.DataFrame(store.recent_alerts(con, 500))
        pa = out / "alerts.csv"
        al.to_csv(pa, index=False)
        print(f"{len(al)} alerts -> {pa}")


if __name__ == "__main__":
    main()
