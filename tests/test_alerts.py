"""Tests for airwatch.alerts (rule evaluation)."""
from airwatch import alerts


BASE_CFG = {
    "alerts": {
        "emergency_squawks": ["7500", "7600", "7700"],
        "low_altitude_m": 3000,
        "airport_radius_km": 25,
        "new_entrant": False,
    },
    "airports": [{"code": "CAI", "lon": 31.4, "lat": 30.1}],
}


def make_track(**overrides):
    track = {
        "icao24": "abc123",
        "callsign": "MSR123",
        "lon": 31.4,
        "lat": 30.1,
        "baro_alt": 10000.0,
        "velocity": 250.0,
        "heading": 90.0,
        "squawk": "1234",
        "on_ground": False,
    }
    track.update(overrides)
    return track


def kinds(cfg=BASE_CFG, tracks=None, known_icao=frozenset()):
    return [kind for kind, _, _ in alerts.evaluate(tracks or [], known_icao, cfg)]


# ---- emergency squawks ----

def test_emergency_squawk_triggers_alert():
    assert "EMERGENCY" in kinds(tracks=[make_track(squawk="7700")])


def test_normal_squawk_does_not_trigger_emergency():
    assert "EMERGENCY" not in kinds(tracks=[make_track(squawk="1234")])


def test_missing_or_blank_squawk_is_safe():
    assert kinds(tracks=[make_track(squawk=None)]) == []
    assert kinds(tracks=[make_track(squawk="   ")]) == []


def test_squawk_is_stripped_before_matching():
    assert "EMERGENCY" in kinds(tracks=[make_track(squawk=" 7700 ")])


# ---- new entrants ----

def test_new_entrant_triggers_when_unknown():
    cfg = {**BASE_CFG, "alerts": {**BASE_CFG["alerts"], "new_entrant": True}}

    assert "NEW ENTRANT" in kinds(cfg=cfg, tracks=[make_track()])


def test_new_entrant_ignored_for_known_aircraft():
    cfg = {**BASE_CFG, "alerts": {**BASE_CFG["alerts"], "new_entrant": True}}

    assert "NEW ENTRANT" not in kinds(
        cfg=cfg, tracks=[make_track()], known_icao={"abc123"}
    )


def test_new_entrant_disabled_by_config():
    assert "NEW ENTRANT" not in kinds(tracks=[make_track()])


def test_new_entrant_detail_falls_back_to_icao_when_no_callsign():
    cfg = {**BASE_CFG, "alerts": {**BASE_CFG["alerts"], "new_entrant": True}}

    results = alerts.evaluate(
        [make_track(callsign="")], known_icao=set(), cfg=cfg
    )

    detail = next(detail for kind, _, detail in results if kind == "NEW ENTRANT")
    assert "abc123" in detail


# ---- low altitude ----

def test_low_altitude_far_from_airport_triggers():
    track = make_track(lon=33.0, lat=30.1, baro_alt=1000.0)

    assert "LOW ALTITUDE" in kinds(tracks=[track])


def test_low_altitude_near_airport_is_ignored():
    track = make_track(lon=31.4, lat=30.1, baro_alt=1000.0)

    assert "LOW ALTITUDE" not in kinds(tracks=[track])


def test_on_ground_aircraft_is_ignored():
    track = make_track(lon=33.0, lat=30.1, baro_alt=0.0, on_ground=True)

    assert "LOW ALTITUDE" not in kinds(tracks=[track])


def test_aircraft_above_threshold_is_ignored():
    track = make_track(lon=33.0, lat=30.1, baro_alt=5000.0)

    assert "LOW ALTITUDE" not in kinds(tracks=[track])


def test_missing_altitude_is_safe():
    track = make_track(lon=33.0, lat=30.1, baro_alt=None)

    assert kinds(tracks=[track]) == []


def test_no_airports_does_not_crash():
    cfg = {**BASE_CFG, "airports": []}
    track = make_track(lon=33.0, lat=30.1, baro_alt=1000.0)

    assert "LOW ALTITUDE" not in kinds(cfg=cfg, tracks=[track])


def test_multiple_rules_can_fire_for_one_track():
    cfg = {**BASE_CFG, "alerts": {**BASE_CFG["alerts"], "new_entrant": True}}
    track = make_track(lon=33.0, lat=30.1, baro_alt=1000.0, squawk="7700")

    assert set(kinds(cfg=cfg, tracks=[track])) == {
        "EMERGENCY",
        "NEW ENTRANT",
        "LOW ALTITUDE",
    }


# ---- drone rules ----

DRONE_CFG = {
    "drones": {"nofly_radius_km": 8.0, "max_alt_m": 500.0},
    "airports": [{"code": "CAI", "lon": 31.4, "lat": 30.1}],
}


def make_fix(**overrides):
    fix = {
        "drone_id": "drone-1",
        "lon": 31.4,
        "lat": 30.1,
        "alt_m": 120.0,
        "source": "remote-id",
    }
    fix.update(overrides)
    return fix


def test_drone_near_airport_below_max_altitude_alerts():
    results = alerts.evaluate_drones([make_fix()], DRONE_CFG)

    assert len(results) == 1
    kind, pseudo, detail = results[0]
    assert kind == "DRONE NEAR AIRPORT"
    assert pseudo["icao24"] == "drone-1"
    assert "CAI" in detail


def test_drone_above_max_altitude_is_ignored():
    assert alerts.evaluate_drones([make_fix(alt_m=600.0)], DRONE_CFG) == []


def test_drone_far_from_airport_is_ignored():
    assert alerts.evaluate_drones([make_fix(lon=33.0)], DRONE_CFG) == []


def test_drone_with_no_airports_is_ignored():
    cfg = {**DRONE_CFG, "airports": []}

    assert alerts.evaluate_drones([make_fix()], cfg) == []


def test_malformed_drone_fix_is_skipped():
    assert alerts.evaluate_drones([{"drone_id": "broken"}], DRONE_CFG) == []
