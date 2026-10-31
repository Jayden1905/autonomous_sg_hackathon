# Sources behind the semantic model

Every number an agent is told, and every number `rules.py` enforces, traces to
one of these. Passage ids match `model.yaml`. Retrieved 31 Oct 2026.

## From the organisers

| Passage | Where |
|---|---|
| `brief:c2:*` | *Autonomous SG 2026, Airbus Track* PDF, Challenge 2, pages 2–3. Text extracted verbatim. |
| schema layer | `data/flights.csv`, `airports.csv`, `airlines.csv` from the Challenge 2 zip. Profiled by `atc semantic profile`; the result is `schema.yaml`. |

The brief gives the row filter (`WEATHER_DELAY > 15` or `LATE_AIRCRAFT_DELAY > 20`),
the three agents' responsibilities, the 3-turn limit and the "what to avoid" list. It
gives no operational numbers, so those come from the regulations below.

## Regulations and standards

| Passage | Used for | Primary reference | Checked against |
|---|---|---|---|
| `icao:4444:5.8.2` | Wake separation, time-based arrival minima (H→M 2 min, H/M→L 3 min, J→L 4 min) | ICAO Doc 4444 PANS-ATM §5.8.2 | [Wikipedia: Wake turbulence category](https://en.wikipedia.org/wiki/Wake_turbulence_category), [code7700](https://code7700.com/wake_turbulence.htm), [UK CAA AIC P 083/2020](https://nats-uk.ead-it.com/cms-nats/export/sites/default/en/Publications/Aeronautical-Information-Circulars-AICs/pink-aics/EG_Circ_2020_P_083_en.pdf) |
| `icao:4444:8.7.3` | Distance minima used to derive the H→H (4 NM) and default radar (3 NM) time gaps at 150 kt | ICAO Doc 4444 §8.7.3 | same as above; [ICAO APAC capacity workshop (FAA)](https://www.icao.int/sites/default/files/APAC/Meetings/2025/2025%20Capacity%20Assessment%20WS/Day%202/SP-05-Model-to-determine-Airport-Capacity-FAA.pdf) |
| `icao:wtc` | Wake category definitions by MTOM | ICAO Doc 4444, Amendment 9 | [Wikipedia](https://en.wikipedia.org/wiki/Wake_turbulence_category) |
| `easa:cat.op.mpa.181` | Final reserve fuel: 30 min turbine at holding speed, 1,500 ft | EASA AMC/GM to Part-CAT, CAT.OP.MPA.181(c)(5)(ii); mirrors ICAO Annex 6 Part I 4.3.6.3 | [EASA AMC/GM Part-CAT](https://www.easa.europa.eu/en/downloads/136239/en), [Bristol Groundschool summary](https://www.bristol.gs/new-easa-fuel-policy-effective-30th-october-2022/), [FAA vs EASA comparison](https://migflug.com/afterburner/airline-fuel-reserves-faa-easa-contingency-final-reserve/) |
| `bts:delay-causes` | The five delay-cause columns' meanings | 14 CFR 234.4; BTS reporting guidance | [BTS: Understanding the reporting of causes](https://www.bts.gov/topics/airlines-and-airports/understanding-reporting-causes-flight-delays-and-cancellations), [BTS: Airline on-time performance](https://www.bts.gov/explore-topics-and-geography/topics/airline-time-performance-and-causes-flight-delays), [Nov 2002 final rule](https://www.bts.gov/archive/publications/federal_register/2002/bts_20021125) |
| `bts:on-time` | 15-minute on-time threshold | BTS | same |
| `iata:mct` | Default minimum connect time 35 min; US hub range 30–55 | IATA PSC Resolution 765; OAG MCT data | [Travel Vient 2026 MCT survey](https://travelvient.com/blog/tightest-connections-2026/), [Navan glossary](https://navan.com/resources/glossary/what-is-minimum-connection-time), [OMAAT on AA MCTs](https://onemileatatime.com/insights/american-airlines-minimum-connection-time/) |
| `airbus:turnaround` | Planning turnaround 45 min | Airbus A320 ground-ops figures; IATA Ground Operations Manual | [Simple Flying](https://simpleflying.com/narrowbody-turnaround-times-time-differences-guide/), [Aileron Air](https://www.aileronair.com/blog/aircraft-turnaround-time-aviation/) |

## Impact estimates (`atc impact`)

| Figure | Used for | Status | Source |
|---|---|---|---|
| Recorded `ARRIVAL_DELAY` and `DEPARTURE_DELAY` per flight | The before/after baseline | measured (DOT 2015) | `data/flights.csv` |
| 40 kg/min holding fuel burn, A320 family | Fuel-in-hold estimate | estimate, planning rule of thumb; actual 30–40 kg/min | [BB711 A320 fuel-flow rules of thumb](https://blackbox711.com/docs/site/rules-of-thumb/fuel-flow-a320/), [Airliners.net line-pilot figures](https://www.airliners.net/forum/viewtopic.php?t=1440797), [Airbus *Getting to Grips with Fuel Economy*](https://ansperformance.eu/library/airbus-fuel-economy.pdf) |
| Human coordination time per irregular flight | Decision-time comparison | **not quantified**: no per-flight figure found in the literature searched (MIT FTL 1995 AOCC study, Castro TAP AOCC study, FAA TRACON comms report give workload and message counts, not minutes per disruption) | [Grandeau, MIT FTL R95-2](https://dspace.mit.edu/bitstream/handle/1721.1/68117/FTL_R_1995_02.pdf), [Castro, The Airline Operations Control Problem](https://www.researchgate.net/publication/295092665_The_Airline_Operations_Control_Problem) |

The comparison is against what actually happened to the same flight on the same day. Only
post-departure delay is comparable (a flight cannot arrive before its recorded departure delay).

## Honest limits

- The wake table is time-based ICAO minima, not RECAT-EU or FAA Order 7110.126 groups.
  Real ORD uses RECAT; our gaps are therefore conservative.
- H→H (96 s) and the 72 s default are derived, not published, time values: 4 NM and 3 NM
  at an assumed 150 kt approach speed. Flagged in `atc.wake_separation.params.note`.
- Final reserve is modelled as minutes of endurance. No alternate, contingency or
  additional fuel; no fuel-flow model.
- MCT and turnaround are industry-typical values, not the specific airport's or airline's.
  Secondary sources were used because OAG and IATA data are paywalled.
- The DOT data carries no fuel, runway, gate, connection or crew information. Those
  scenario fields are generated and are listed as `synthetic: true` in the model, and every
  `Scenario` payload repeats the list in `synthetic_fields`.
- The ICAO and EASA documents themselves are paywalled or very large PDFs; the passages
  quote the figures as reproduced by the secondary sources listed, which agree with each other.
