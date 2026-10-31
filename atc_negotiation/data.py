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

from .schemas import AirportCapacity, AirportInfo, AircraftCategory, Connection, Gate, Runway, RunwayArrival, Scenario
from .semantic import default_engine

# Thresholds come from the semantic model, like every number in rules.py.
_filter = default_engine().rule_params("data.disruption_filter")
WEATHER_DELAY_GT: int = int(_filter.get("weather_delay_gt", 15))
LATE_AIRCRAFT_DELAY_GT: int = int(_filter.get("late_aircraft_delay_gt", 20))
TURNAROUND_MIN: int = int(default_engine().rule_params("ground.turnaround").get("value", 45))

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
def airport_capacity(csv_path: Path = DATA_DIR / "airport_capacity.csv") -> dict[str, dict]:
    """Organisers' workbook, sheet airport_capacity, exported to CSV. Synthetic planning limits."""
    if not csv_path.exists():
        return {}
    with csv_path.open(newline="") as f:
        return {r["IATA_CODE"]: r for r in csv.DictReader(f)}


def capacity_for(iata: str) -> AirportCapacity | None:
    cap = airport_capacity().get(iata)
    if not cap:
        return None
    return AirportCapacity(
        size_class=cap["size_class"], active_runways=int(cap["active_runways"]), gates=int(cap["gates"]),
        max_runway_ops_per_hour=int(cap["max_runway_ops_per_hour"]),
        min_turnaround_min=int(cap["min_turnaround_min"]),
        spare_gates_at_any_time=int(cap["spare_gates_at_any_time"]))


def turnaround_for(iata: str) -> int:
    cap = airport_capacity().get(iata)
    return int(cap["min_turnaround_min"]) if cap and cap.get("min_turnaround_min") else TURNAROUND_MIN


# Organisers' workbook: assumed spare fuel on arrival is 45 min of holding above final reserve.
SPARE_HOLDING_MIN: int = int(default_engine().rule_params("pilot.final_reserve_fuel").get("spare_holding_on_arrival_min", 45))
FINAL_RESERVE_MIN: int = int(default_engine().rule_params("pilot.final_reserve_fuel").get("value", 30))


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
            if (_int(row.get("WEATHER_DELAY", "")) > WEATHER_DELAY_GT
                    or _int(row.get("LATE_AIRCRAFT_DELAY", "")) > LATE_AIRCRAFT_DELAY_GT):
                yield row
                n += 1
                if limit is not None and n >= limit:
                    return


def scenario_id(row: dict) -> str:
    """Unique per qualifying row: flight number, date and route, e.g. AA341-2015-01-01-AUS-DFW."""
    return (f"{row['AIRLINE']}{row['FLIGHT_NUMBER']}-{row['YEAR']}-{int(row['MONTH']):02d}-"
            f"{int(row['DAY']):02d}-{row['ORIGIN_AIRPORT']}-{row['DESTINATION_AIRPORT']}")


def legacy_scenario_id(row: dict) -> str:
    """The id before the route was added. Not unique; traces written before then still carry it."""
    return f"{row['AIRLINE']}{row['FLIGHT_NUMBER']}-{row['YEAR']}-{int(row['MONTH']):02d}-{int(row['DAY']):02d}"


def scenario_from_row(row: dict) -> Scenario:
    flight = f"{row['AIRLINE']}{row['FLIGHT_NUMBER']}"
    date = f"{row['YEAR']}-{int(row['MONTH']):02d}-{int(row['DAY']):02d}"
    # The seed stays on flight|date so the synthetic fields of every row are unchanged; only the id
    # gains the route, because one flight number can fly several legs a day.
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
    cap = capacity_for(row["DESTINATION_AIRPORT"])
    n_runways = cap.active_runways if cap else 2
    # Spacing on a busy runway, from the workbook's movements per hour spread over its runways.
    # The draws below keep the seeded sequence unchanged; only the step they feed is new.
    per_runway = (cap.max_runway_ops_per_hour / n_runways) if cap else 20
    step = max(2, round(60 / per_runway)) if cap else None

    if weather > WEATHER_DELAY_GT:
        disruption = (f"Thunderstorms at {dest_label}: {weather} min weather delay logged. "
                      f"Runway {left} closed, arrival rate reduced.")
        runways = [
            Runway(name=left, open=False),
            Runway(name=right, arrivals=_traffic(rng, earliest, dense=True, step=step)),
        ]
    else:
        disruption = (f"Late inbound aircraft: {late_ac} min late-aircraft delay. "
                      f"Taxiway off {left} blocked by a towed aircraft.")
        runways = [
            Runway(name=left, taxiway_blocked=True, arrivals=_traffic(rng, earliest, step=step)),
            Runway(name=right, arrivals=_traffic(rng, earliest, dense=True, step=step)),
        ]
    heading = int(left[:2])
    opposite = f"{(heading + 18 - 1) % 36 + 1:02d}"
    extra = [f"{heading:02d}C", f"{opposite}L", f"{opposite}R"]
    if n_runways >= 3:
        runways.append(Runway(name=extra[0], open=weather <= WEATHER_DELAY_GT,
                              arrivals=_traffic(rng_extra(seed, 1), earliest, dense=True, step=step)))
    if n_runways >= 4:
        # A crosswind pair is out of use for arrivals in this wind; listed so the airport is whole.
        runways.append(Runway(name=extra[1], open=False))
    if n_runways == 1:
        runways = [r for r in runways if r.name == right]
        runways[0].name = left
        disruption = disruption.replace(f"Runway {left} closed, arrival rate reduced.",
                                        "Arrival rate reduced on its only runway.").replace(
            f"Taxiway off {left} blocked by a towed aircraft.", "Taxiway blocked by a towed aircraft.")
    gates = [
        Gate(name="A1", free_from_min=earliest + rng.randint(10, 40), free_until_min=earliest + 120),
        Gate(name="A4", free_from_min=earliest - 10, free_until_min=earliest + rng.randint(5, 25)),
        Gate(name="B7", free_from_min=earliest + rng.randint(40, 70), free_until_min=earliest + 200),
    ]
    # The workbook's spare gates at any time (2 or 3) are the only ones ground can offer.
    if cap:
        gates = gates[:cap.spare_gates_at_any_time]
    connections = [
        Connection(passengers=rng.randint(8, 30), departs_min=earliest + rng.randint(45, 90)),
        Connection(passengers=rng.randint(4, 15), departs_min=earliest + rng.randint(90, 150)),
    ]

    return Scenario(
        scenario_id=scenario_id(row),
        flight=flight, airline=row["AIRLINE"], airline_name=airlines().get(row["AIRLINE"]),
        origin=row["ORIGIN_AIRPORT"], destination=row["DESTINATION_AIRPORT"],
        origin_info=airports().get(row["ORIGIN_AIRPORT"]), destination_info=dest_info,
        destination_capacity=cap,
        scheduled_arrival_hhmm=f"{sched[:2]}:{sched[2:]}",
        disruption=disruption,
        weather_delay_min=weather, late_aircraft_delay_min=late_ac,
        earliest_arrival_min=earliest,
        aircraft_category=category,
        # Endurance above touchdown at earliest_arrival; 30 of it is final reserve,
        # so holding capacity is 40-80 min. Below ~60 almost nothing is feasible.
        # Organisers' workbook: 45 min of holding above the 30 min final reserve. The draw is kept so the
        # seeded sequence, and every other synthetic value, stays as it was.
        fuel_endurance_min=(rng.randint(70, 110), FINAL_RESERVE_MIN + SPARE_HOLDING_MIN)[1],
        connections=connections,
        runways=runways, gates=gates,
        crew_shift_ends_min=earliest + rng.randint(30, 90),
        turnaround_min=turnaround_for(row["DESTINATION_AIRPORT"]),
        max_arrival_min=earliest + 180,  # window is relative to when it can first arrive
        source={k: row[k] for k in ("YEAR", "MONTH", "DAY", "AIRLINE", "FLIGHT_NUMBER", "TAIL_NUMBER",
                                    "ORIGIN_AIRPORT", "DESTINATION_AIRPORT", "SCHEDULED_DEPARTURE",
                                    "DEPARTURE_DELAY", "SCHEDULED_ARRIVAL", "ARRIVAL_DELAY",
                                    "WEATHER_DELAY", "LATE_AIRCRAFT_DELAY") if k in row},
        synthetic_fields=SYNTHETIC,
    )


def rng_extra(seed: int, n: int) -> random.Random:
    """A separate stream for runways added from the workbook, so the original draws are untouched."""
    return random.Random(seed * 31 + n)


def _traffic(rng: random.Random, earliest: int, dense: bool = False, step: int | None = None) -> list[RunwayArrival]:
    # Dense = ~3 min spacing (180 s): insertable only where the wake table allows,
    # which is what makes the ATC agent's slot choice non-trivial. With the workbook, a busy
    # runway's spacing comes from its movements per hour instead.
    step = step if step is not None else (3 if dense else 5)
    out, t = [], earliest - 6
    while t < earliest + 30:
        out.append(RunwayArrival(time_min=t, category=rng.choices(list(AircraftCategory), weights=[1, 6, 3])[0]))
        t += step + rng.randint(0, 1)
    return out
