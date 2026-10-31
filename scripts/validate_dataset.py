"""Run from repo root: uv run python scripts/validate_dataset.py [DATA_DIR] [--api URL] [--offset N] [--limit N] [-v]

Checks that the scenarios the UI is served trace to the organisers' CSVs. DATA_DIR holds their
airlines.csv, airports.csv and flights.csv (default data/); pass the original download folder to
also confirm the backend's copy is identical. Scenarios are read in-process, or from a running
server with --api. Fields the backend generates are listed in synthetic_fields and not compared.
Exit status: 0 all match, 1 a mismatch, 2 nothing mismatched but the backend has no dataset to check.
"""
import argparse
import csv
import hashlib
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))

# atc_negotiation/data.py generates these; the UI marks them Synthetic from synthetic_fields.
GENERATED = {"aircraft_category", "fuel_endurance_min", "connections", "runways", "gates",
             "crew_shift_ends_min", "turnaround_min", "disruption"}
# Names one leg of one flight on one day; flights.csv has no repeats of it.
ROW_KEY = ("YEAR", "MONTH", "DAY", "AIRLINE", "FLIGHT_NUMBER", "ORIGIN_AIRPORT", "DESTINATION_AIRPORT")


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()[:12]


def minutes(value):
    return int(float(value)) if value else 0


def clock(hhmm):
    hhmm = hhmm.zfill(4)
    return f"{hhmm[:2]}:{hhmm[2:]}"


def airport_info(row):
    """AirportInfo as the API serves it; None when airports.csv has no coordinates."""
    if not row or not row["LATITUDE"] or not row["LONGITUDE"]:
        return None
    return {"iata": row["IATA_CODE"], "name": row["AIRPORT"], "city": row["CITY"],
            "state": row["STATE"], "country": row["COUNTRY"],
            "latitude": float(row["LATITUDE"]), "longitude": float(row["LONGITUDE"])}


def row_key(scenario):
    source = {k: str(v) for k, v in (scenario.get("source") or {}).items()}
    key = tuple(source.get(c) for c in ROW_KEY)
    return None if None in key else key


def find_rows(path, keys):
    """One pass over flights.csv: the rows for the wanted keys, and the file's row count."""
    found = {key: [] for key in keys}
    total = 0
    with path.open(newline="") as f:
        for row in csv.DictReader(f):
            total += 1
            key = tuple(row[c] for c in ROW_KEY)
            if key in found:
                found[key].append(row)
    return found, total


def compare(s, flights, airports, airlines):
    """(flights.csv row or None, mismatches, fields skipped because the scenario declares them synthetic)."""
    problems, skipped = [], []
    declared = set(s.get("synthetic_fields") or [])

    def expect(field, got, want):
        if field in declared:
            skipped.append(field)
        elif got != want:
            if isinstance(got, dict) and isinstance(want, dict):
                got = {k: v for k, v in got.items() if v != want.get(k)}
                want = {k: want.get(k) for k in got}
            problems.append(f"{field}: scenario {got!r}, CSV {want!r}")

    source = {k: str(v) for k, v in (s.get("source") or {}).items()}
    key = row_key(s)
    row = None
    if source:
        matches = flights.get(key, []) if key else []
        if len(matches) != 1:
            problems.append(f"{len(matches)} flights.csv rows match source "
                            + "-".join(source.get(c, "?") for c in ROW_KEY))
        else:
            row = matches[0]
    if row:
        for column, value in source.items():
            if column not in row:
                problems.append(f"source.{column}: not a flights.csv column")
            elif value != row[column]:
                problems.append(f"source.{column}: scenario {value!r}, CSV {row[column]!r}")
        expect("flight", s["flight"], row["AIRLINE"] + row["FLIGHT_NUMBER"])
        expect("airline", s["airline"], row["AIRLINE"])
        expect("origin", s["origin"], row["ORIGIN_AIRPORT"])
        expect("destination", s["destination"], row["DESTINATION_AIRPORT"])
        expect("scheduled_arrival_hhmm", s["scheduled_arrival_hhmm"], clock(row["SCHEDULED_ARRIVAL"]))
        expect("weather_delay_min", s["weather_delay_min"], minutes(row["WEATHER_DELAY"]))
        expect("late_aircraft_delay_min", s["late_aircraft_delay_min"], minutes(row["LATE_AIRCRAFT_DELAY"]))
        # Not a column: the backend assumes a flight cannot arrive sooner than it departed late.
        expect("earliest_arrival_min", s["earliest_arrival_min"], max(0, minutes(row["DEPARTURE_DELAY"])))
    origin, destination, airline = ((row["ORIGIN_AIRPORT"], row["DESTINATION_AIRPORT"], row["AIRLINE"])
                                    if row else (s["origin"], s["destination"], s["airline"]))
    # A hand-written sample may omit labels; one that carries them must still match.
    for field, code in (("origin_info", origin), ("destination_info", destination)):
        if source or s.get(field):
            expect(field, s.get(field), airport_info(airports.get(code)))
    if source or s.get("airline_name"):
        expect("airline_name", s.get("airline_name"), airlines.get(airline))
    if source and GENERATED - declared:
        problems.append(f"synthetic_fields does not declare {sorted(GENERATED - declared)}, "
                        "so the UI shows them without a Synthetic mark")
    if not source and not declared:
        problems.append("no source row and no synthetic_fields entry saying it is hand-written")
    return row, problems, skipped


def client(api):
    if api:
        import httpx
        return httpx.Client(base_url=api, timeout=300)
    from fastapi.testclient import TestClient
    from atc_negotiation.api import app
    return TestClient(app)


def main():
    parser = argparse.ArgumentParser(description="Check served scenarios against the organisers' CSVs.")
    parser.add_argument("data_dir", nargs="?", type=Path, default=root / "data")
    parser.add_argument("--api", help="base URL of a running backend; default is in-process")
    parser.add_argument("--offset", type=int, default=0, help="first /dot/scenarios row to check")
    parser.add_argument("--limit", type=int, default=200, help="how many dataset scenarios to check")
    parser.add_argument("-v", "--verbose", action="store_true", help="list every scenario, not only failures")
    args = parser.parse_args()

    names = ("airlines", "airports", "flights")
    files = {name: args.data_dir / f"{name}.csv" for name in names}
    absent = [str(p) for p in files.values() if not p.exists()]
    if absent:
        sys.exit("missing " + ", ".join(absent))
    with files["airports"].open(newline="") as f:
        airports = {r["IATA_CODE"]: r for r in csv.DictReader(f)}
    with files["airlines"].open(newline="") as f:
        airlines = {r["IATA_CODE"]: r["AIRLINE"] for r in csv.DictReader(f)}

    http = client(args.api)
    try:
        http.get("/health").raise_for_status()
    except Exception as error:  # httpx is imported only with --api, so no narrower type to name
        sys.exit(f"cannot reach the backend: {error}")
    bundled = [http.get(f"/scenarios/{s['scenario_id']}").json() for s in http.get("/scenarios").json()]
    page = http.get("/dot/scenarios", params={"offset": args.offset, "limit": args.limit})
    if page.status_code != 404:
        page.raise_for_status()
    dataset = page.json() if page.status_code == 200 else None

    scenarios = bundled + (dataset or [])
    flights, total = find_rows(files["flights"], {k for s in scenarios if (k := row_key(s))})
    served = root / "data" / "flights.csv"
    print(f"reference  {args.data_dir}  flights.csv sha256 {sha256(files['flights'])} · {total:,} rows")
    if not args.api and served.exists() and served.resolve() != files["flights"].resolve():
        same = sha256(served) == sha256(files["flights"])
        print(f"backend    data/flights.csv is {'identical to' if same else 'DIFFERENT from'} the reference")

    def report(title, group, shown=20):
        print(f"\n{title}")
        results = [(s, *compare(s, flights, airports, airlines)) for s in group]
        failures = 0
        for s, row, problems, skipped in results:
            if problems:
                failures += 1
                if failures <= shown:
                    print(f"  FAIL {s['scenario_id']}")
                    for problem in problems:
                        print(f"         - {problem}")
            elif args.verbose or len(group) <= 10:
                if row:
                    note = f"{row['YEAR']}-{int(row['MONTH']):02d}-{int(row['DAY']):02d} {s['flight']} {s['origin']}->{s['destination']}"
                    if skipped:
                        note += f"  (declared synthetic, not compared: {', '.join(sorted(set(skipped)))})"
                    print(f"  ok   {s['scenario_id']:<40} {note}")
                else:
                    print(f"  --   {s['scenario_id']:<40} hand-written, not from the dataset")
        if failures > shown:
            print(f"  ... {failures - shown} more failures not shown")
        return results

    results = report(f"bundled scenarios ({len(bundled)})", bundled)
    if dataset is None:
        print("\ndataset scenarios: not checked, the backend has no flights.csv in data/ (/dot/scenarios returned 404)")
    else:
        rows = report(f"dataset scenarios (/dot/scenarios offset {args.offset}, {len(dataset)} returned)", dataset)
        results += rows
        matched = [row for _, row, problems, _ in rows if row and not problems]
        dates = sorted(f"{r['YEAR']}-{int(r['MONTH']):02d}-{int(r['DAY']):02d}" for r in matched)
        print(f"  {len(matched)} of {len(dataset)} match flights.csv, airports.csv and airlines.csv"
              + (f" · dates {dates[0]} to {dates[-1]}" if dates else ""))

    traced = sum(1 for _, row, problems, _ in results if row and not problems)
    handwritten = sum(1 for _, row, problems, _ in results if not row and not problems)
    failed = sum(1 for _, _, problems, _ in results if problems)
    print(f"\nresult: {traced} scenarios traced to the dataset, {failed} with mismatches, "
          f"{handwritten} hand-written (not from the dataset)")
    sys.exit(1 if failed else 2 if dataset is None else 0)


if __name__ == "__main__":
    main()
