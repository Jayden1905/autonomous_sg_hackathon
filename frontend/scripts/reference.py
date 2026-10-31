"""Run from repo root: uv run python frontend/scripts/reference.py [data_dir]. Default data_dir is data/.

Airline and airport labels for tooltips. Counts and delays cover only flights that meet the
brief's disruption filter, so they are not on-time performance.
"""
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(root))
from atc_negotiation.data import airlines, airports, qualifying_rows

data = Path(sys.argv[1]) if len(sys.argv) > 1 else root / "data"
departures = defaultdict(int)
arrival_delays = defaultdict(list)
airline_delays = defaultdict(list)
for row in qualifying_rows(data / "flights.csv"):
    delay = int(row["ARRIVAL_DELAY"])
    departures[row["ORIGIN_AIRPORT"]] += 1
    arrival_delays[row["DESTINATION_AIRPORT"]].append(delay)
    airline_delays[row["AIRLINE"]].append(delay)


def median(delays):
    return round(statistics.median(delays)) if delays else None


reference = {
    "generated_by": "frontend/scripts/reference.py",
    "source": "Organisers' airlines.csv, airports.csv and flights.csv (US DOT 2015). "
              "'disrupted' counts only flights that meet the brief's disruption filter.",
    "airlines": {
        code: {
            "iata": code,
            "name": name,
            "disrupted": {
                "flights": len(airline_delays[code]),
                "median_arrival_delay_min": median(airline_delays[code]),
            },
        }
        for code, name in sorted(airlines(data / "airlines.csv").items())
    },
    # Same rows as the API's AirportInfo: airports without coordinates are left out.
    "airports": {
        code: {
            **info.model_dump(mode="json"),
            "disrupted": {
                "departures": departures[code],
                "arrivals": len(arrival_delays[code]),
                "median_arrival_delay_min": median(arrival_delays[code]),
            },
        }
        for code, info in sorted(airports(data / "airports.csv").items())
    },
}
(root / "frontend/src/workspace/reference.json").write_text(
    json.dumps(reference, indent=2, ensure_ascii=False) + "\n"
)
