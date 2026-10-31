"""Build scenarios from the US DOT 2015 flight-delays CSV (Kaggle `flights.csv`).

The brief says: pick a row with WEATHER_DELAY > 15 or LATE_AIRCRAFT_DELAY > 20
and feed it to the agents. The DOT data has no fuel, gates, runways or
connections, so those are generated deterministically from the row (seeded
by flight and date) and listed in `Scenario.synthetic_fields`.
"""

from __future__ import annotations

import csv
import hashlib
import random
from functools import lru_cache
from pathlib import Path
from typing import Iterator

from .schemas import AirportInfo, AircraftCategory, Connection, Gate, Runway, RunwayArrival, Scenario

SYNTHETIC = ["aircraft_category", "fuel_endurance_min", "connections", "runways", "gates",
             "crew_shift_ends_min", "turnaround_min", "disruption"]

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


@lru_cache(maxsize=1)
def airports(csv_path: Path = DATA_DIR / "airports.csv") -> dict[str, AirportInfo]:
    if not csv_path.exists():
        return {}
    with csv_path.open(newline="") as f:
        return {r["IATA_CODE"]: AirportInfo(
            iata=r["IATA_CODE"], name=r["AIRPORT"], city=r["CITY"], state=r["STATE"], country=r["COUNTRY"],
            latitude=float(r["LATITUDE"]), longitude=float(r["LONGITUDE"]),
        ) for r in csv.DictReader(f) if r.get("LATITUDE") and r.get("LONGITUDE")}


@lru_cache(maxsize=1)
def airlines(csv_path: Path = DATA_DIR / "airlines.csv") -> dict[str, str]:
    if not csv_path.exists():
        return {}
    with csv_path.open(newline="") as f:
        return {r["IATA_CODE"]: r["AIRLINE"] for r in csv.DictReader(f)}


def _runway_pair(rng: random.Random) -> tuple[str, str]:
    """Two parallel runways on a plausible heading, e.g. ('09L', '09R'). Synthetic."""
    heading = rng.choice([4, 9, 13, 17, 22, 27, 31, 36])
    return f"{heading:02d}L", f"{heading:02d}R"


def _int(v: str) -> int:
    try:
        return int(float(v))
    except ValueError:
        return 0


def qualifying_rows(csv_path: Path, limit: int | None = None) -> Iterator[dict]:
    """Stream rows that meet the brief's disruption filter."""
    n = 0
    with csv_path.open(newline="") as f:
        for row in csv.DictReader(f):
            if _int(row.get("WEATHER_DELAY", "")) > 15 or _int(row.get("LATE_AIRCRAFT_DELAY", "")) > 20:
                yield row
                n += 1
                if limit is not None and n >= limit:
                    return


def scenario_from_row(row: dict) -> Scenario:
    flight = f"{row['AIRLINE']}{row['FLIGHT_NUMBER']}"
    date = f"{row['YEAR']}-{int(row['MONTH']):02d}-{int(row['DAY']):02d}"
    seed = int(hashlib.sha256(f"{flight}|{date}".encode()).hexdigest(), 16) % (2**32)
    rng = random.Random(seed)

    weather = _int(row.get("WEATHER_DELAY", ""))
    late_ac = _int(row.get("LATE_AIRCRAFT_DELAY", ""))
    dep_delay = max(0, _int(row.get("DEPARTURE_DELAY", "")))
    earliest = dep_delay  # inbound delay already baked in; it can't arrive earlier than this

    category = rng.choices(list(AircraftCategory), weights=[1, 6, 3])[0]
    sched = row.get("SCHEDULED_ARRIVAL", "0000").zfill(4)
    dest_info = airports().get(row["DESTINATION_AIRPORT"])
    dest_label = dest_info.name if dest_info else row["DESTINATION_AIRPORT"]
    left, right = _runway_pair(rng)

    if weather > 15:
        disruption = (f"Thunderstorms at {dest_label}: {weather} min weather delay logged. "
                      f"Runway {left} closed, arrival rate reduced.")
        runways = [
            Runway(name=left, open=False),
            Runway(name=right, arrivals=_traffic(rng, earliest, dense=True)),
        ]
    else:
        disruption = (f"Late inbound aircraft: {late_ac} min late-aircraft delay. "
                      f"Taxiway off {left} blocked by a towed aircraft.")
        runways = [
            Runway(name=left, taxiway_blocked=True, arrivals=_traffic(rng, earliest)),
            Runway(name=right, arrivals=_traffic(rng, earliest, dense=True)),
        ]

    gates = [
        Gate(name="A1", free_from_min=earliest + rng.randint(10, 40), free_until_min=earliest + 120),
        Gate(name="A4", free_from_min=earliest - 10, free_until_min=earliest + rng.randint(5, 25)),
        Gate(name="B7", free_from_min=earliest + rng.randint(40, 70), free_until_min=earliest + 200),
    ]
    connections = [
        Connection(passengers=rng.randint(8, 30), departs_min=earliest + rng.randint(45, 90)),
        Connection(passengers=rng.randint(4, 15), departs_min=earliest + rng.randint(90, 150)),
    ]

    return Scenario(
        scenario_id=f"{flight}-{date}",
        flight=flight, airline=row["AIRLINE"], airline_name=airlines().get(row["AIRLINE"]),
        origin=row["ORIGIN_AIRPORT"], destination=row["DESTINATION_AIRPORT"],
        origin_info=airports().get(row["ORIGIN_AIRPORT"]), destination_info=dest_info,
        scheduled_arrival_hhmm=f"{sched[:2]}:{sched[2:]}",
        disruption=disruption,
        weather_delay_min=weather, late_aircraft_delay_min=late_ac,
        earliest_arrival_min=earliest,
        aircraft_category=category,
        # Endurance above touchdown at earliest_arrival; 30 of it is final reserve,
        # so holding capacity is 40-80 min. Below ~60 almost nothing is feasible.
        fuel_endurance_min=rng.randint(70, 110),
        connections=connections,
        runways=runways, gates=gates,
        crew_shift_ends_min=earliest + rng.randint(30, 90),
        turnaround_min=45,
        max_arrival_min=earliest + 180,  # window is relative to when it can first arrive
        source={k: row[k] for k in ("YEAR", "MONTH", "DAY", "AIRLINE", "FLIGHT_NUMBER", "TAIL_NUMBER",
                                    "ORIGIN_AIRPORT", "DESTINATION_AIRPORT", "SCHEDULED_DEPARTURE",
                                    "DEPARTURE_DELAY", "SCHEDULED_ARRIVAL", "ARRIVAL_DELAY",
                                    "WEATHER_DELAY", "LATE_AIRCRAFT_DELAY") if k in row},
        synthetic_fields=SYNTHETIC,
    )


def _traffic(rng: random.Random, earliest: int, dense: bool = False) -> list[RunwayArrival]:
    # Dense = ~3 min spacing (180 s): insertable only where the wake table allows,
    # which is what makes the ATC agent's slot choice non-trivial.
    step = 3 if dense else 5
    out, t = [], earliest - 6
    while t < earliest + 30:
        out.append(RunwayArrival(time_min=t, category=rng.choices(list(AircraftCategory), weights=[1, 6, 3])[0]))
        t += step + rng.randint(0, 1)
    return out
