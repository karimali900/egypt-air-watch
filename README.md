# ✈️ Egypt Air Watch — real-time airborne picture

Live ADS-B tracks over Egypt via OpenSky Network (free, no key, ~15 s
refresh) + SQLite history + alert rules + bilingual dashboard.

> Honest scope: this is cooperative surveillance (aircraft broadcast their
> own positions). It is NOT radar — non-cooperative objects need primary
> radar or an RTL-SDR 1090 MHz receiver (see Stage 2 below).

## Auth (recommended — raises you above the tiny anonymous quota)
1. Register free at opensky-network.org → My OpenSky → create an **API client**
2. Save it as `.env` (git-ignored, never commit):
```
OPENSKY_CLIENT_ID=your-client-id
OPENSKY_CLIENT_SECRET=your-secret
```
Without this the app still works anonymously until the daily quota runs out.

## Run (uses the `petro` env)
```bash
conda run -n petro pip install -r requirements.txt  # pyyaml if missing
conda run -n petro python scripts/poll.py            # terminal 1: live ingest
conda run -n petro streamlit run dashboard/app.py --server.port 8504 --server.address 0.0.0.0 --server.headless true  # terminal 2
```
Open http://localhost:8504

## Files
- `config/zones.yaml` — Egypt bbox, airports, alert thresholds
- `src/airwatch/` — `opensky.py` (live API), `store.py` (SQLite), `alerts.py` (rules)
- `scripts/poll.py` — ingest loop (`--once` for a single snapshot)
- `scripts/export.py` — CSV + KML (`--icao ABC123 --kml` for one track)
- `dashboard/app.py` — EN/AR map + table + alerts, auto-refresh

## Alerts
Emergency squawks (7500/7600/7700), new entrants, low altitude outside
airport radius. Tune in `config/zones.yaml`.

## Stage 2 — true local radar (optional hardware, ~$30)
RTL-SDR dongle + `dump1090` receives 1090 MHz directly off your roof —
real-time, internet-independent. The `store.py` schema already fits
dump1090 JSON; only a `dump1090.py` fetcher is needed. Ask to add it.
