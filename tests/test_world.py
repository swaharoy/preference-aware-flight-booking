"""The simulated world: real airports and airlines flying plausible routes several times a day, synthetic but
realistic fares, schedules and open seats, the same on every machine, small enough for the hosted model on
every route, and an answer key that agrees with an independent reading of the rules."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import pytest
from helpers import CODES, requests
from oracle import booking_answer
from slimconfig import plain_output

from contract import AirportCode, SearchInput
from plugin import receipts, search_flights, solve_booking, world
from plugin.rules import SEAT_ORDER, date_of, day_number, minute_number, time_of_day

DAY = day_number("2026-12-03")
GOLDEN = {
    ("ORD", "LHR"): "40fb006ed5e8726a",
    ("JFK", "LAX"): "0b372f14d746a645",
    ("ATL", "ORD"): "c9981f6a777ec083",
    ("BNA", "LHR"): "7f195bafdf9afb75",
    ("SFO", "SIN"): "856b10fb9819ebb8",
    ("LHR", "CDG"): "7be3605de3623b72",
}
ROUTES = [(a, b) for a in CODES for b in CODES if a != b]
US_AIRLINES = {row[1] for row in world.AIRLINES if row[2] == "US"}
FLIGHT_NUMBER = re.compile(r"^[A-Z0-9]{2} [1-9]\d{0,3}$")
LARGEST_SEARCH_CHARS = 30_000  # one day's search must stay well inside the hosted model's 65,536-token budget


def digest(offers) -> str:
    text = json.dumps([plain_output(o) for o in offers], sort_keys=True)
    return hashlib.sha256(text.encode()).hexdigest()[:16]


@pytest.mark.parametrize("route", sorted(GOLDEN))
def test_a_route_and_day_make_the_same_flights_everywhere(route) -> None:
    assert digest(world.built_day(*route, DAY)) == GOLDEN[route]


def test_the_airports_are_the_contract_codes() -> None:
    assert [row[0] for row in world.AIRPORTS] == [member.value for member in AirportCode]
    assert len(world.AIRPORTS) == 68
    assert all(-720 <= row[7] <= 720 and row[7] % 30 == 0 for row in world.AIRPORTS)
    countries = {row[3] for row in world.AIRPORTS}
    assert "US" in countries and len(countries) > 20, "US and international airports"


def test_the_airlines_are_real_names_with_hubs_among_the_airports() -> None:
    assert "Delta Air Lines" in US_AIRLINES and "British Airways" not in US_AIRLINES
    for code, _name, _country, kind, reach, hubs, _cabins in world.AIRLINES:
        assert re.fullmatch(r"[A-Z0-9]{2}", code) and kind in ("us", "low", "intl") and reach > 0
        assert hubs and all(world.is_airport(hub) for hub in hubs), code


def local_minute(time: str, code: str) -> int:
    return minute_number(time) + world.utc_offset(code)


def test_flights_are_well_formed_and_plausible() -> None:
    airline_of = {row[1]: row for row in world.AIRLINES}
    for origin, destination in ROUTES[::5]:
        domestic = world.country(origin) == world.country(destination) == "US"
        for day in (DAY, DAY + 40):
            offers = world.built_day(origin, destination, day)
            stamp = date_of(day).replace("-", "")
            assert [o.offer_id for o in offers] == [f"{stamp}-{n:02d}" for n in range(1, len(offers) + 1)]
            assert len(offers) <= world.MOST_ITINERARIES
            assert [minute_number(o.segments[0].depart) for o in offers] == sorted(
                minute_number(o.segments[0].depart) for o in offers), "by departure"
            for offer in offers:
                first, last = offer.segments[0], offer.segments[-1]
                local = local_minute(first.depart, origin)
                assert local // 1440 == day and 6 * 60 <= local % 1440 <= 23 * 60 + 55, "leaves on the day"
                assert offer.depart_local == world.time_text(local)
                assert offer.arrive_local == world.time_text(local_minute(last.arrive, destination))
                assert offer.total_minutes == minute_number(last.arrive) - minute_number(first.depart)
                assert offer.time_of_day is time_of_day(offer.depart_local)
                assert offer.open_seats and offer.open_seats == [s for s in SEAT_ORDER if s in offer.open_seats]
                assert first.origin == origin and last.destination == destination
                assert offer.stops == len(offer.segments) - 1 <= 1
                for one, two in zip(offer.segments, offer.segments[1:]):
                    assert one.destination == two.origin
                    gap = minute_number(two.depart) - minute_number(one.arrive)
                    low = 60 if world.country(one.origin) != world.country(one.destination) else 45
                    assert low <= gap <= 180
                    if offer.time_of_day.value == "DAY":
                        assert local_minute(two.depart, two.origin) % 1440 >= 5 * 60, "no night connection by day"
                airline = airline_of[offer.carrier]
                if domestic:
                    assert offer.carrier in US_AIRLINES
                for segment in offer.segments:
                    assert FLIGHT_NUMBER.fullmatch(segment.flight_number)
                    assert segment.flight_number.startswith(airline[0] + " ")
                    assert minute_number(segment.arrive) - minute_number(segment.depart) == segment.air_minutes > 0
                    inside = world.country(segment.origin) == world.country(segment.destination)
                    assert not inside or world.country(segment.origin) == airline[2], "no cabotage"
                if offer.stops:
                    assert offer.segments[0].destination in airline[5], "connects at the airline's hub"
                assert offer.fare_cents > 0


def test_every_route_holds_the_choices_the_task_is_about() -> None:
    """On one day, over every route: a mix of nonstops and connections, red-eyes where the route is long,
    varied open seats, nonstops slower than a connection, and varied fares."""
    counts = dict.fromkeys(("flown", "mixed", "red-eye and day", "only middle", "one of window or aisle",
                            "slow nonstop", "distinct fares", "long", "long with a red-eye"), 0)
    for origin, destination in ROUTES:
        offers = world.built_day(origin, destination, DAY)
        if not offers:
            continue
        counts["flown"] += 1
        nonstops = [o for o in offers if o.stops == 0]
        connections = [o for o in offers if o.stops]
        kinds = {o.time_of_day.value for o in offers}
        counts["mixed"] += bool(nonstops and connections)
        counts["red-eye and day"] += kinds == {"DAY", "RED_EYE"}
        counts["only middle"] += any([s.value for s in o.open_seats] == ["MIDDLE"] for o in offers)
        counts["one of window or aisle"] += any(len(o.open_seats) == 1 and o.open_seats[0].value != "MIDDLE"
                                                 for o in offers)
        counts["slow nonstop"] += any(n.total_minutes > c.total_minutes for n in nonstops for c in connections)
        counts["distinct fares"] += len({o.fare_cents for o in offers}) > 1
        if world.distance_km(origin, destination) >= world.RED_EYE_KM:
            counts["long"] += 1
            counts["long with a red-eye"] += "RED_EYE" in kinds
    flown = counts["flown"]
    assert flown >= 0.98 * len(ROUTES)
    assert counts["long with a red-eye"] == counts["long"], "every long route has a red-eye"
    assert counts["mixed"] >= 0.75 * flown
    assert counts["red-eye and day"] >= 0.85 * flown
    assert counts["only middle"] >= 0.6 * flown and counts["one of window or aisle"] >= 0.5 * flown
    assert counts["slow nonstop"] >= 0.3 * counts["mixed"], "a long nonstop against a quicker connection, often"
    assert counts["distinct fares"] >= 0.95 * flown


def test_every_search_fits_the_hosted_context() -> None:
    largest = 0
    for origin, destination in ROUTES:
        offers = world.day_offers(origin, destination, DAY)
        found = {"run_id": "0123456789ab", "note": world.NOTE, "offers": [plain_output(o) for o in offers]}
        largest = max(largest, len(json.dumps(found)))
    assert largest <= LARGEST_SEARCH_CHARS, largest


def test_offers_do_not_depend_on_the_booking_date(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    query = SearchInput("", AirportCode.JFK, AirportCode.LAX, "2026-12-20")
    early = search_flights(query, tmp_path)
    monkeypatch.setattr(receipts, "CLOCK", lambda: "2026-12-19 08:00:00.000000")
    assert plain_output(search_flights(query, tmp_path)) == plain_output(early)


def test_unknown_or_equal_airports_are_refused() -> None:
    with pytest.raises(ValueError):
        world.day_offers("XXX", "LHR", DAY)
    with pytest.raises(ValueError):
        world.day_offers("BOS", "BOS", DAY)


def test_the_answer_key_agrees_with_an_independent_reading_for_400_requests(tmp_path: Path) -> None:
    outcomes = set()
    count = 0
    for value in requests(450, "oracle"):
        key = solve_booking(value, tmp_path)
        accepted = {(b.offer_id, b.seat.value) for b in key.correct_bookings}
        assert accepted == booking_answer(key.trip, key.offers), plain_output(value)
        cheapest = min(o.fare_cents for o in key.offers)
        outcomes.add(("perfect" if key.best_score == 100 else "compromise",
                      "cheapest" if key.lowest_best_fare_cents == cheapest else "dearer"))
        count += 1
    assert count >= 350
    assert outcomes == {("perfect", "cheapest"), ("perfect", "dearer"), ("compromise", "cheapest"),
                        ("compromise", "dearer")}
