"""Building values the way NanoAgent's sandbox does, and running the tools and verifier like the host."""

from __future__ import annotations

import hashlib
import tempfile
from contextlib import contextmanager
from pathlib import Path

from slimconfig import build_output, plain_output

import verifier
import verifier.world
from contract import TASKS, TOOLS, AirportCode, Offer, SearchInput, SolveOutput, Task, Tool, TripInput
from plugin import get_trip, search_flights, solve_booking, world
from plugin.rules import date_of, day_number, minute_number, time_of_day

BOOK = Task.BOOK_FLIGHT.value
CODES = [member.value for member in AirportCode]
SPLITS = [(20, 30, 50), (30, 30, 40), (10, 20, 70), (34, 33, 33), (0, 40, 60), (100, 0, 0), (0, 100, 0),
          (0, 0, 100), (50, 50, 0), (45, 10, 45), (25, 60, 15), (60, 25, 15)]


def request(**changes) -> TripInput:
    """A trip request: by default Maya Chen flying ORD-LHR on 2026-12-03, a window (20), a red-eye (30) and a
    nonstop (50)."""
    value = {
        "traveller_name": "Maya Chen", "origin": "ORD", "destination": "LHR", "travel_date": "2026-12-03",
        "seat_preference": "WINDOW", "seat_weight": 20, "time_preference": "RED_EYE", "time_weight": 30,
        "stops_preference": "NONSTOP", "stops_weight": 50,
    } | changes
    return build_output(value, TripInput)


def requests(count: int, salt: str = "requests"):
    """Up to ``count`` varied trip requests with flights that day, chosen by SHA-256 so they are the same on
    every machine: any route, a day 0 to 60 days after today, every preference, and weights from a fixed list
    of splits (0 and 100 among them) or drawn at random."""
    for index in range(count):
        digest = hashlib.sha256(f"{salt}:{index}".encode()).digest()
        origin, destination = CODES[digest[0] % len(CODES)], CODES[digest[1] % len(CODES)]
        if origin == destination:
            continue
        if digest[2] % 2:
            weights = SPLITS[digest[3] % len(SPLITS)]
        else:
            first = digest[3] % 101
            second = digest[4] % (101 - first)
            weights = (first, second, 100 - first - second)
            weights = tuple(weights[(i + digest[5]) % 3] for i in range(3))
        value = request(
            origin=origin, destination=destination, travel_date=date_of(day_number("2026-11-05") + digest[6] % 60),
            seat_preference="WINDOW" if digest[7] % 2 else "AISLE", seat_weight=weights[0],
            time_preference="DAY" if digest[8] % 2 else "RED_EYE", time_weight=weights[1],
            stops_preference="NONSTOP" if digest[9] % 2 else "CONNECTING", stops_weight=weights[2],
        )
        if verifier.verify_input("get_trip", value)["valid"]:
            yield value


def booking(run_id: str, offer_id: str, seat: str) -> dict:
    return {"run_id": run_id, "offer_id": offer_id, "seat": seat}


def judge(arguments: TripInput, output: dict, reference: SolveOutput | None, workspace: Path) -> dict:
    """verify_task on plain values built into their contract classes, as the sandbox does."""
    given, made = TASKS[Task.BOOK_FLIGHT]
    key = None if reference is None else build_output(plain_output(reference), SolveOutput)
    return verifier.verify_task(BOOK, build_output(plain_output(arguments), given), build_output(output, made), key,
                                str(workspace))


class Run:
    """One booking run: the answer key pinned in a scratch folder, then get_trip and a search in the workspace."""

    def __init__(self, value: TripInput, root: Path, *, search: bool = True) -> None:
        self.request = value
        self.workspace = root / "workspace"
        self.workspace.mkdir(parents=True, exist_ok=True)
        scratch = root / "scratch"
        scratch.mkdir(parents=True, exist_ok=True)
        self.key = solve_booking(value, scratch)
        started = get_trip(value, self.workspace)
        self.run_id = started.run_id
        self.trip = started.trip
        self.offers = []
        if search:
            self.offers = self.search().offers

    def search(self, travel_date: str | None = None, *, origin=None, destination=None):
        trip = self.trip
        return search_flights(
            SearchInput(self.run_id, AirportCode(origin or trip.origin.code),
                        AirportCode(destination or trip.destination.code), travel_date or trip.travel_date),
            self.workspace,
        )

    def gold(self) -> dict:
        first = self.key.correct_bookings[0]
        return booking(self.run_id, first.offer_id, first.seat.value)

    def judge(self, output: dict) -> dict:
        return judge(self.request, output, self.key, self.workspace)


def key_for(value: TripInput):
    """The answer key of a request, pinned in a throwaway folder."""
    with tempfile.TemporaryDirectory() as folder:
        return solve_booking(value, Path(folder))


def failed(verdict: dict) -> list[str]:
    return [entry["id"] for entry in verdict["details"]["checks"] if entry["ok"] is False]


def tool_input(tool: str, value: dict) -> dict:
    return verifier.verify_input(tool, build_output(value, TOOLS[Tool(tool)][0]))


@contextmanager
def hand_built(days: dict, origin: str = "ORD", destination: str = "LHR"):
    """The world replaced, in the tools and the verifier alike, by hand-built offers on one route:
    {date: [plain offers]}, and nothing on any other route or day. Used for exact boundaries real schedules
    rarely hit."""
    built = {day_number(date): tuple(build_output(o, Offer) for o in offers) for date, offers in days.items()}

    def built_day(o, d, day):
        return built.get(day, ()) if (o, d) == (origin, destination) else ()

    saved = world.built_day, verifier.world.built_day
    world.built_day = verifier.world.built_day = built_day
    try:
        yield
    finally:
        world.built_day, verifier.world.built_day = saved


def offer(number: int, depart_local: str, fare: int, seats: tuple = ("WINDOW", "AISLE", "MIDDLE"), *,
          minutes: tuple = (480,), origin: str = "ORD", destination: str = "LHR", origin_offset: int = -360,
          destination_offset: int = 0, carrier: str = "American Airlines", date: str = "2026-12-03") -> dict:
    """A plain hand-built offer leaving at ``depart_local`` (HH:MM local time at the origin on ``date``): a
    nonstop, or through a hub when ``minutes`` has two values, with a 90-minute connection. Its time of day is
    the rules' own."""
    points = [origin, *["BOS"][: len(minutes) - 1], destination]
    start = minute_number(f"{date} {depart_local}") - origin_offset
    segments = []
    for index, air in enumerate(minutes):
        segments.append({
            "origin": points[index], "destination": points[index + 1], "flight_number": f"AA {100 * number + index}",
            "depart": world.time_text(start), "arrive": world.time_text(start + air), "air_minutes": air,
        })
        start += air + 90
    first, last = minute_number(segments[0]["depart"]), minute_number(segments[-1]["arrive"])
    local = world.time_text(first + origin_offset)
    return {
        "offer_id": f"{date.replace('-', '')}-{number:02d}", "carrier": carrier, "stops": len(minutes) - 1,
        "depart_local": local, "arrive_local": world.time_text(last + destination_offset),
        "total_minutes": last - first, "time_of_day": time_of_day(local).value, "open_seats": list(seats),
        "fare_cents": fare, "segments": segments,
    }
