# Preference-Aware Flight Booking

A NanoAgent plugin (`nanoagent.plugin/v0001`): a traveller says in plain words where and when they are
flying and how much three things matter to them, a window or aisle seat, a daytime or red-eye departure,
and a nonstop or connecting flight, as weights that add up to 100. An agent books the one-way flight and
seat with the highest score on that day's flights, at the lowest fare among those that reach it, and a
deterministic verifier checks the booking against the same rules.

There is no company policy here: the objective is the traveller's own weighted preferences. A long nonstop
may be slower than a connection, a red-eye may be cheaper, and the wanted seat may be open only on a flight
that meets less of what matters; the weights decide.

**Simulated fares and schedules.** Airports and airline names are real; every flight, fare, schedule and
open seat is synthetic, made by the plugin (see *The simulated flights* below). Airline names are used for
realism only: nothing here is a real fare, timetable or seat map.

## Tools

| Tool | Does | Code |
|---|---|---|
| `booking_requirements` | What a booking request must give, field by field with examples (read from the contract), what the date, the weights and each preference mean, the airports to choose from, and an example request, as of today. Definitions only: nothing on how to choose | `src/plugin/requirements.py`, `src/plugin/guide.py` |
| `get_trip` | Begins a booking run for a trip request: the trip as booked today (traveller, airports with country, booking date, travel date, and the three preferences with their weights) and its `run_id` | `src/plugin/trip.py` |
| `search_flights` | The one-way offers on a route on a day (today or later): airline, flight numbers, local departure and arrival, stops, total minutes, `DAY` or `RED_EYE`, the seat types still open and the fare | `src/plugin/search.py` |
| `solve_booking` | The answer key: the trip as booked today, its offers, the best score, the lowest fare reaching it and every correct offer and seat. NanoAgent runs it before the agent, out of its sight; it is never one of the agent's tools | `src/plugin/solve.py` |

### Tasks

| Task | Does | Runner |
|---|---|---|
| `booking-requirements` | Shows what to tell us to book a flight (topic `ALL`, `FIELDS` or `AIRPORTS`) | `tool`, with `booking_requirements` |
| `search-flights` | Shows the offers on a route and day | `tool`, with `search_flights` |
| `preference-aware-flight-booking` | Books the flight and seat that best fit the traveller's weighted preferences | `agent`, with `get_trip` and `search_flights`; reference `solve_booking` |

The booking task's input is the trip request, which the chat fills from plain words such as "book Maya Chen
from Chicago O'Hare to London Heathrow on Dec 3; a window seat matters 20, a red-eye 30 and a nonstop 50":
`traveller_name`, `origin` and `destination` (airport codes from the list), `travel_date` (the local date
where the flight leaves), `seat_preference` (`WINDOW` or `AISLE`) and `seat_weight`, `time_preference`
(`DAY` or `RED_EYE`) and `time_weight`, `stops_preference` (`NONSTOP` or `CONNECTING`) and `stops_weight`.
Each weight is a whole number from 0 to 100 and the three add up to exactly 100; any other sum, a negative
weight, the same airport twice or an unknown airport is refused. The booking date is today (UTC), read when
the answer key is pinned and recorded in the run's receipt; requests travelling before today or more than 330
days ahead are refused, and so is a route no airline flies.

The agent's path is three tool calls: `get_trip` with the request, `search_flights` with the trip's route
and travel date, then `submit`. It submits `run_id`, `offer_id` and `seat` (`WINDOW`, `AISLE` or `MIDDLE`).

### The rules (the task's instructions state them exactly)

A booking is one offer and one seat type open on it. Its **score** is the sum of:

- `seat_weight` if the seat is the one wanted (`MIDDLE` never is);
- `time_weight` if the offer's `time_of_day` is the one wanted: `DAY` when the first flight leaves from 06:00
  to 20:55 local time at the origin, `RED_EYE` from 21:00 to 23:55;
- `stops_weight` if `NONSTOP` is wanted and the offer has 0 stops, or `CONNECTING` and it has 1 or more.

| Rule | Exact rule |
|---|---|
| P1 | The booking reaches the highest score of any offer and open seat on the day's offers |
| P2 | Among the offers that can reach that score, the lowest fare; an exact fare tie accepts any of them, with any open seat that reaches the score |

Fare is not part of the score and there is no fare cap; total time and the airline do not count.

### The simulated flights

`src/plugin/world.py` (the same file as `verifier/world.py`) makes the offers on a route and day from a
SHA-256 stream keyed by the route and the day only, so a search gives the same offers on every machine and on
any booking date, and the verifier rebuilds every search the agent made. Its model, every constant of which
is a modelling choice, not data:

- **Airports:** 68 large airports in the U.S. and abroad, from OurAirports (public domain), fetched
  2026-11-02, with their standard-time UTC offsets (no daylight saving). Segment times are UTC; each offer
  also gives its departure and arrival in local time.
- **Airlines:** 29 real airlines, each with its country, hubs among the 68 airports and longest nonstop. An
  airline sells a nonstop when one end is its hub, and connections through its own hubs that add at most 35%
  distance; a domestic trip is sold only by that country's airlines, and no airline flies a leg inside
  another country. Flight numbers (e.g. `DL 1482`) are stable per airline, leg and daily frequency.
- **Schedule:** up to 10 itineraries a day (up to 6 nonstop), with at most one connection. First flights
  leave 06:00-20:55 local time, or 21:00-23:55 (a red-eye) with a 12% chance each; every route of 1,500 km or
  more has at least one red-eye a day. A flight's scheduled minutes are 20 + the distance at 760-900 km/h
  + 0-30 minutes of padding; 30% of nonstops fly an older or smaller aircraft on a padded schedule (640-720
  km/h + 30-75 minutes), so a connection through a hub on the way is often quicker. Connections take 45 to 180
  minutes (60 at least between countries), the shorter more often. A day itinerary never leaves its hub from
  00:00 to 04:55 local time; a red-eye may, as it continues overnight.
- **Open seats:** each offer has at least one of `WINDOW`, `AISLE`, `MIDDLE` open: all three (30%), two of
  them (34%), only a window or only an aisle (16%), or only middle seats (20%).
- **Fares:** one economy fare per offer: $50 + 30 x km^0.85 cents, times 0.80-1.35 by day; nonstops 1.00-1.25x,
  connections 0.75-0.95x, low-cost airlines 0.88x, red-eyes 0.80-0.95x, and 5-20% more for day departures at
  07-10 or 16-20 local time.

Over every route on one day, about 83% of the flown routes have both nonstops and connections, 93% have both
day and red-eye departures, about 40% of the mixed routes have a nonstop slower than a connection, and the
largest search is under 6,000 characters (the tests check every route). Exact boundaries (a departure at
21:00 against 20:55, fares a cent apart or exactly tied, two 30s against a 40) are checked with hand-built
offers, which replace the world in the tools and the verifier alike.

## Layout

It has the standard plugin layout, which NanoAgent requires:

```text
.
├── nanoagent.yaml   # manifest: id, runtime, permissions (no network), tools, tasks and their instructions
├── contract.py      # each tool's and task's typed input and output: slimconfig Output classes and Enums
├── README.md
├── LICENSE
├── pyproject.toml
├── uv.lock
├── .gitignore
├── .env             # needed environment variable names (none)
├── src/plugin/      # the MCP server (__main__.py, IMPLEMENTATIONS) and the tools
│   ├── world.py     # airports, airlines and the simulated offers; the same file as verifier/world.py
│   ├── rules.py     # requests, the time of day, the score and rules P1-P2 as exact integer code; the same file as verifier/rules.py
│   ├── guide.py     # what a booking request must give; the same file as verifier/guide.py
│   └── receipts.py  # each run's receipts in the workspace: runs/<run id>/trip.json, search-<n>.json
├── tests/           # rules, world, requirements, verifier, scripted cases (tests/cases/*.json), MCP server
├── ui/              # renderers.js / renderers.css: the requirements, the offers table, the booking with its score and checks
├── product/         # product.yaml and icon.svg
└── verifier/        # the deterministic verifier: one module per tool and booking.py for the task
```

The verdict of the booking task is a list of named checks, each with `ok`, `expected`, `actual` and a
message naming the offer, the seat and the rule:

- integrity gates: `answer-key` (the pinned key is this request's, booked on the day it was pinned, with the
  route's offers, and follows the rules), `this-run` (the submitted run was begun by `get_trip` for this
  request, on the same booking date, after the key was pinned), `searched`, `receipts-match` (every search
  receipt equals the route's offers for its query, rebuilt by the verifier), `offer-seen` (the booked offer
  was in this run's search results for the trip's route and travel date);
- rules: `seat-open`, `best-score` (expected: the best score and an example booking reaching it; actual: the
  booking's score, preference by preference), `lowest-fare-among-best`.

The verdict is valid, scoring 1, only when every check holds; any failed check scores 0. Checks after a
failed one are "not checked". Expected values come from the verifier's own copy of the rules applied to the
pinned trip and offers. The verdict's details also hold the booked offer's points per preference, which the
result card shows.

## Develop and run

```bash
uv sync --extra dev
uv run pytest
uv run ruff check .
```

The tests freeze today at 2026-11-05, so they pass on any day. `uv run pytest` replays the scripted cases
in `tests/cases/` (gold, wrong, missing, malformed, tampered and boundary runs) through the real tools and
verifier, checks the answer key against an independent reading of the rules for 350+ varied requests, judges
every offer and seat of 60 varied searches, and checks the simulated world's plausibility, determinism and
size on every route.

NanoAgent passes the folder the plugin may write to as `NANOAGENT_WORKSPACE`; the tools write only
their receipts there, under `runs/`. To check the plugin with NanoAgent from its checkout:

```bash
uv run nanoagent plugin inspect <path to this plugin>
```
