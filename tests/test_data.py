from pathlib import Path

import pytest

from atc_negotiation import data

FLIGHTS = Path(__file__).parent.parent / "data" / "flights.csv"
needs_data = pytest.mark.skipif(not FLIGHTS.exists(), reason="run `make data` first")


def test_lookups_degrade_to_empty_without_files(tmp_path):
    assert data.airports(tmp_path / "missing.csv") == {}
    assert data.airlines(tmp_path / "missing.csv") == {}


@needs_data
def test_scenario_is_enriched_from_reference_csvs():
    row = next(data.qualifying_rows(FLIGHTS, limit=1))
    s = data.scenario_from_row(row)
    assert s.airline_name and s.airline_name != s.airline
    assert s.origin_info and s.origin_info.iata == s.origin
    assert s.destination_info and s.destination_info.iata == s.destination
    assert -180 <= s.destination_info.longitude <= 180


@needs_data
def test_weather_disruption_names_the_destination_airport():
    row = next(r for r in data.qualifying_rows(FLIGHTS, limit=2000) if data._int(r["WEATHER_DELAY"]) > 15)
    s = data.scenario_from_row(row)
    assert s.destination_info and s.destination_info.name in s.disruption


@needs_data
def test_runways_vary_by_scenario_and_are_deterministic():
    rows = list(data.qualifying_rows(FLIGHTS, limit=40))
    names = {tuple(r.name for r in data.scenario_from_row(row).runways) for row in rows}
    assert len(names) > 1
    a, b = data.scenario_from_row(rows[0]), data.scenario_from_row(rows[0])
    assert a == b


def test_scenario_id_carries_route():
    row = {"AIRLINE": "AA", "FLIGHT_NUMBER": "341", "YEAR": "2015", "MONTH": "1", "DAY": "1",
           "ORIGIN_AIRPORT": "AUS", "DESTINATION_AIRPORT": "DFW"}
    assert data.scenario_id(row) == "AA341-2015-01-01-AUS-DFW"
    assert data.legacy_scenario_id(row) == "AA341-2015-01-01"


@needs_data
def test_scenario_ids_are_unique_across_every_qualifying_row():
    """One flight number flies several legs a day; flight-date alone collided on ~105k rows."""
    seen: set[str] = set()
    for row in data.qualifying_rows(FLIGHTS):
        sid = data.scenario_id(row)
        assert sid not in seen, sid
        seen.add(sid)


@needs_data
def test_synthetic_fields_still_seeded_by_flight_and_date():
    """Adding the route to the id must not change any generated value (batch traces stay valid)."""
    import hashlib
    import random
    row = next(data.qualifying_rows(FLIGHTS, limit=1))
    seeds = []
    real = random.Random

    def spy(seed=None):
        seeds.append(seed)
        return real(seed)

    random.Random = spy
    try:
        data.scenario_from_row(row)
    finally:
        random.Random = real
    flight = f"{row['AIRLINE']}{row['FLIGHT_NUMBER']}"
    date = data.legacy_scenario_id(row)[len(flight) + 1:]
    assert seeds == [int(hashlib.sha256(f"{flight}|{date}".encode()).hexdigest(), 16) % (2**32)]
