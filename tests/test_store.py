"""Tests for airwatch.store (SQLite persistence)."""
import pytest

from airwatch import store


@pytest.fixture
def con(tmp_path):
    connection = store.connect(tmp_path / "airwatch.db")
    yield connection
    connection.close()


def make_track(**overrides):
    track = {
        "icao24": "abc123",
        "callsign": "MSR123",
        "snapshot": 100,
        "lon": 31.2,
        "lat": 30.1,
        "baro_alt": 10000.0,
        "velocity": 250.0,
        "heading": 90.0,
        "squawk": "1234",
        "on_ground": False,
    }
    track.update(overrides)
    return track


def make_fix(**overrides):
    fix = {
        "drone_id": "drone-1",
        "ts": 1_000_000,
        "lon": 31.2,
        "lat": 30.1,
        "alt_m": 120.0,
        "speed_ms": 5.0,
        "source": "remote-id",
        "detail": "test",
    }
    fix.update(overrides)
    return fix


# ---- connect / schema ----

def test_connect_creates_parent_dirs_and_schema(tmp_path):
    db = tmp_path / "nested" / "airwatch.db"
    con = store.connect(db)
    try:
        assert db.exists()
        tables = {
            row[0]
            for row in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        assert {"positions", "tracks", "alerts",
                "drone_positions", "drone_reports"} <= tables
    finally:
        con.close()


# ---- aircraft ingest ----

def test_ingest_inserts_position_and_track(con):
    store.ingest(con, [make_track()], snapshot=100)

    assert con.execute("SELECT COUNT(*) FROM positions").fetchone()[0] == 1
    row = con.execute(
        "SELECT icao24, callsign, first_seen, last_seen FROM tracks"
    ).fetchone()
    assert row == ("abc123", "MSR123", 100, 100)


def test_ingest_updates_last_seen_and_callsign(con):
    store.ingest(con, [make_track()], snapshot=100)
    store.ingest(con, [make_track(snapshot=200, callsign="MSR999")], snapshot=200)

    row = con.execute(
        "SELECT callsign, first_seen, last_seen FROM tracks"
    ).fetchone()
    assert row == ("MSR999", 100, 200)
    assert con.execute("SELECT COUNT(*) FROM positions").fetchone()[0] == 2


def test_ingest_is_idempotent_for_same_snapshot(con):
    store.ingest(con, [make_track()], snapshot=100)
    store.ingest(con, [make_track()], snapshot=100)

    assert con.execute("SELECT COUNT(*) FROM positions").fetchone()[0] == 1


def test_ingest_converts_on_ground_to_integer(con):
    store.ingest(con, [make_track(on_ground=True)], snapshot=100)

    assert con.execute("SELECT on_ground FROM positions").fetchone()[0] == 1


def test_ingest_handles_missing_callsign_on_insert(con):
    store.ingest(con, [make_track(callsign=None)], snapshot=100)

    assert con.execute("SELECT callsign FROM positions").fetchone()[0] is None
    assert con.execute("SELECT callsign FROM tracks").fetchone()[0] is None


def test_ingest_missing_callsign_becomes_empty_string_on_update(con):
    store.ingest(con, [make_track()], snapshot=100)
    store.ingest(con, [make_track(snapshot=200, callsign=None)], snapshot=200)

    assert con.execute("SELECT callsign FROM tracks").fetchone()[0] == ""


# ---- queries ----

def test_latest_snapshot_returns_only_newest_snapshot(con):
    store.ingest(con, [make_track()], snapshot=100)
    store.ingest(con, [make_track(snapshot=200, callsign="LATE1")], snapshot=200)

    rows = store.latest_snapshot(con)

    assert len(rows) == 1
    assert rows[0]["snapshot"] == 200
    assert rows[0]["callsign"] == "LATE1"


def test_latest_snapshot_empty_db(con):
    assert store.latest_snapshot(con) == []


def test_track_history_orders_newest_first(con):
    for snap in (100, 200, 300):
        store.ingest(con, [make_track(snapshot=snap)], snapshot=snap)

    rows = store.track_history(con, "abc123")

    assert [row["snapshot"] for row in rows] == [300, 200, 100]


def test_track_history_respects_limit(con):
    for snap in (100, 200, 300):
        store.ingest(con, [make_track(snapshot=snap)], snapshot=snap)

    rows = store.track_history(con, "abc123", limit=2)

    assert [row["snapshot"] for row in rows] == [300, 200]


def test_track_history_unknown_icao_returns_empty(con):
    assert store.track_history(con, "nope") == []


# ---- alerts ----

def test_add_alert_deduplicates_within_window(con, monkeypatch):
    monkeypatch.setattr(store.time, "time", lambda: 1_000_000)
    track = make_track()

    assert store.add_alert(con, "EMERGENCY", track, "squawk 7700") is True
    assert store.add_alert(con, "EMERGENCY", track, "duplicate") is False
    assert con.execute("SELECT COUNT(*) FROM alerts").fetchone()[0] == 1


def test_add_alert_allows_different_kind(con):
    track = make_track()

    assert store.add_alert(con, "EMERGENCY", track, "squawk 7700") is True
    assert store.add_alert(con, "LOW ALTITUDE", track, "low") is True


def test_add_alert_allows_after_cooldown(con, monkeypatch):
    now = [1_000_000]
    monkeypatch.setattr(store.time, "time", lambda: now[0])
    track = make_track()

    assert store.add_alert(con, "EMERGENCY", track, "first") is True
    now[0] += 1801
    assert store.add_alert(con, "EMERGENCY", track, "second") is True


def test_add_alert_uses_empty_callsign_when_missing(con):
    track = {"icao24": "abc123"}

    assert store.add_alert(con, "EMERGENCY", track, "no callsign") is True

    assert con.execute("SELECT callsign FROM alerts").fetchone()[0] == ""


def test_recent_alerts_newest_first_and_limited(con, monkeypatch):
    now = [1_000_000]
    monkeypatch.setattr(store.time, "time", lambda: now[0])
    track = make_track()

    for kind in ("EMERGENCY", "LOW ALTITUDE", "NEW ENTRANT"):
        now[0] += 10
        store.add_alert(con, kind, track, kind.lower())

    rows = store.recent_alerts(con, limit=2)

    assert [row["kind"] for row in rows] == ["NEW ENTRANT", "LOW ALTITUDE"]


def test_recent_alerts_empty_db(con):
    assert store.recent_alerts(con) == []


# ---- drones ----

def test_ingest_drones_deduplicates_same_drone_and_timestamp(con):
    fix = make_fix()

    store.ingest_drones(con, [fix])
    store.ingest_drones(con, [fix])

    assert con.execute("SELECT COUNT(*) FROM drone_positions").fetchone()[0] == 1


def test_latest_drones_filters_by_age(con, monkeypatch):
    now = 1_000_000
    monkeypatch.setattr(store.time, "time", lambda: now)
    store.ingest_drones(con, [
        make_fix(ts=now - 100),
        make_fix(ts=now - 1000),
    ])

    rows = store.latest_drones(con, max_age_s=900)

    assert len(rows) == 1
    assert rows[0]["ts"] == now - 100


def test_latest_drones_empty_db(con):
    assert store.latest_drones(con) == []


def test_add_and_read_drone_reports(con, monkeypatch):
    now = [1_000_000]
    monkeypatch.setattr(store.time, "time", lambda: now[0])

    store.add_drone_report(con, 31.2, 30.1, 120.0, "first", reporter="alice")
    now[0] += 10
    store.add_drone_report(con, 31.3, 30.2, 90.0, "second", reporter="bob")

    rows = store.recent_drone_reports(con, limit=10)

    assert [row["detail"] for row in rows] == ["second", "first"]
    assert rows[0]["reporter"] == "bob"
