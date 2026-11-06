"""The verifier on correct, wrong, missing, malformed, tampered and boundary results, built the way the
sandbox builds them (build_output of plain JSON). Real simulated offers where they show the case, and
hand-built offers (in the tools and the verifier alike) for exact boundaries."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from helpers import Run, booking, failed, hand_built, judge, key_for, offer, request, requests, tool_input
from slimconfig import build_output, plain_output

import verifier
from contract import (
    AirportCode,
    RequirementsInput,
    RequirementsOutput,
    SearchInput,
    SearchOutput,
    SolveOutput,
    Topic,
    TripOutput,
)
from plugin import booking_requirements, get_trip, search_flights
from plugin.rules import offer_best, score

SEATS = ("WINDOW", "AISLE", "MIDDLE")


def valid(verdict: dict) -> bool:
    return verdict["valid"] is True and verdict["score"] == 1.0


def refused(verdict: dict, *check_ids: str) -> bool:
    return verdict["valid"] is False and verdict["score"] == 0.0 and failed(verdict) == list(check_ids)


# Correct --------------------------------------------------------------------------------------------


def test_the_gold_booking_is_valid_for_varied_requests(tmp_path: Path) -> None:
    for index, value in enumerate(requests(60, "gold")):
        run = Run(value, tmp_path / str(index))
        verdict = run.judge(run.gold())
        assert valid(verdict), (plain_output(value), verdict["message"])
        assert all(entry["ok"] is True for entry in verdict["details"]["checks"])
        assert verdict["details"]["points"]["total"] == run.key.best_score


def test_exactly_the_correct_bookings_pass(tmp_path: Path) -> None:
    """Every offer the agent could book from its search, with every seat type: valid if and only if the answer
    key lists that offer and seat, and refused by the check the rules say."""
    judged = 0
    for index, value in enumerate(requests(60, "every-offer")):
        run = Run(value, tmp_path / str(index))
        correct = {(b.offer_id, b.seat.value) for b in run.key.correct_bookings}
        for found in run.offers:
            for seat in SEATS:
                verdict = run.judge(booking(run.run_id, found.offer_id, seat))
                assert verdict["valid"] is ((found.offer_id, seat) in correct), (index, found.offer_id, seat)
                if seat not in [s.value for s in found.open_seats]:
                    assert failed(verdict) == ["seat-open"]
                elif not verdict["valid"]:
                    built = next(o for o in run.key.offers if o.offer_id == found.offer_id)
                    seat_type = next(s for s in built.open_seats if s.value == seat)
                    reaches = score(run.key.trip, built, seat_type) == run.key.best_score
                    assert failed(verdict) == (["lowest-fare-among-best"] if reaches else ["best-score"])
                judged += 1
    assert judged > 1_000


# Wrong, on real simulated offers -----------------------------------------------------------------------


def first_run(test, salt: str, tmp_path: Path) -> Run:
    """A run of the first varied request whose answer key passes ``test(key)``."""
    for value in requests(3_000, salt):
        if test(key_for(value)):
            return Run(value, tmp_path)
    raise LookupError(salt)


def test_the_cheapest_offer_ignoring_preferences_is_refused(tmp_path: Path) -> None:
    run = first_run(lambda k: offer_best(k.trip, min(k.offers, key=lambda o: o.fare_cents)) < k.best_score,
                    "cheapest", tmp_path)
    cheapest = min(run.offers, key=lambda o: o.fare_cents)
    verdict = run.judge(booking(run.run_id, cheapest.offer_id, cheapest.open_seats[0].value))
    assert refused(verdict, "best-score") and "the best is" in verdict["message"]


def test_a_seat_that_is_not_open_is_refused(tmp_path: Path) -> None:
    run = Run(request(), tmp_path)
    shut = next((o, s) for o in run.offers for s in SEATS if s not in [x.value for x in o.open_seats])
    verdict = run.judge(booking(run.run_id, shut[0].offer_id, shut[1]))
    assert refused(verdict, "seat-open") and "open seats are" in verdict["message"]


def test_the_right_offer_with_a_seat_not_wanted_is_refused(tmp_path: Path) -> None:
    def fits(k) -> bool:
        first = k.correct_bookings[0]
        offer = next(o for o in k.offers if o.offer_id == first.offer_id)
        return k.trip.seat_weight > 0 and first.seat.value == k.trip.seat_preference.value and len(offer.open_seats) > 1
    run = first_run(fits, "other-seat", tmp_path)
    first = run.key.correct_bookings[0]
    offer = next(o for o in run.offers if o.offer_id == first.offer_id)
    other = next(s for s in offer.open_seats if s is not first.seat)
    verdict = run.judge(booking(run.run_id, first.offer_id, other.value))
    assert refused(verdict, "best-score") and "is open on it and would score" in verdict["message"]


def test_a_dearer_offer_with_the_best_score_is_refused(tmp_path: Path) -> None:
    run = first_run(lambda k: any(offer_best(k.trip, o) == k.best_score and o.fare_cents > k.lowest_best_fare_cents
                                  for o in k.offers), "dearer", tmp_path)
    dearer = next(o for o in run.key.offers if offer_best(run.key.trip, o) == run.key.best_score
                  and o.fare_cents > run.key.lowest_best_fare_cents)
    seat = next(s for s in dearer.open_seats if score(run.key.trip, dearer, s) == run.key.best_score)
    verdict = run.judge(booking(run.run_id, dearer.offer_id, seat.value))
    assert refused(verdict, "lowest-fare-among-best") and "also scores" in verdict["message"]


def test_an_offer_of_another_day_is_refused(tmp_path: Path) -> None:
    run = Run(request(), tmp_path)
    later = run.search("2026-12-04").offers[0]
    verdict = run.judge(booking(run.run_id, later.offer_id, later.open_seats[0].value))
    assert refused(verdict, "offer-seen") and "2026-12-04" in verdict["message"]


def test_an_offer_on_another_route_is_refused(tmp_path: Path) -> None:
    """Offer ids number each route's day from 01, so the search of another route alone is made here."""
    run = Run(request(), tmp_path, search=False)
    elsewhere = run.search(origin="BOS").offers[0]
    verdict = run.judge(booking(run.run_id, elsewhere.offer_id, elsewhere.open_seats[0].value))
    assert refused(verdict, "offer-seen") and "BOS-LHR on 2026-12-03" in verdict["message"]


# Exact boundaries, on hand-built offers ------------------------------------------------------------------

DAY = "2026-12-03"


def boundary(tmp_path: Path, offers: list[dict], value, offer_id: str, seat: str) -> dict:
    with hand_built({DAY: offers}):
        run = Run(value, tmp_path)
        return run.judge(booking(run.run_id, offer_id, seat))


def weights(seat, time, stops, **changes):
    return request(seat_weight=seat, time_weight=time, stops_weight=stops, **changes)


def test_two_smaller_weights_beat_the_largest_one(tmp_path: Path) -> None:
    value = weights(30, 30, 40, time_preference="DAY")
    offers = [offer(1, "10:00", 90_000, ("WINDOW",), minutes=(120, 420)),  # window + day = 60
              offer(2, "22:00", 40_000, ("MIDDLE",))]  # nonstop only = 40
    assert valid(boundary(tmp_path / "a", offers, value, "20261203-01", "WINDOW"))
    assert refused(boundary(tmp_path / "b", offers, value, "20261203-02", "MIDDLE"), "best-score")


@pytest.mark.parametrize(("clock", "red_eye"), [("21:00", True), ("20:55", False)])
def test_a_red_eye_starts_at_21_00(tmp_path: Path, clock: str, red_eye: bool) -> None:
    value = weights(0, 60, 40)  # a red-eye wanted
    offers = [offer(1, clock, 40_000), offer(2, "23:00", 90_000, minutes=(120, 420))]
    verdict = boundary(tmp_path, offers, value, "20261203-01", "MIDDLE")
    assert valid(verdict) if red_eye else refused(verdict, "best-score")


def test_an_equal_score_is_settled_by_one_cent(tmp_path: Path) -> None:
    offers = [offer(1, "21:30", 50_001), offer(2, "22:30", 50_000)]
    assert valid(boundary(tmp_path / "a", offers, request(), "20261203-02", "WINDOW"))
    verdict = boundary(tmp_path / "b", offers, request(), "20261203-01", "WINDOW")
    assert refused(verdict, "lowest-fare-among-best") and "$500.00" in verdict["message"]


@pytest.mark.parametrize("offer_id", ["20261203-01", "20261203-02"])
def test_an_exact_fare_tie_accepts_either(tmp_path: Path, offer_id: str) -> None:
    offers = [offer(1, "21:30", 50_000), offer(2, "22:30", 50_000), offer(3, "23:30", 60_000)]
    assert valid(boundary(tmp_path, offers, request(), offer_id, "WINDOW"))


@pytest.mark.parametrize("seat", SEATS)
def test_a_zero_seat_weight_accepts_any_open_seat(tmp_path: Path, seat: str) -> None:
    value = weights(0, 30, 70)
    assert valid(boundary(tmp_path, [offer(1, "21:30", 50_000)], value, "20261203-01", seat))


def test_a_hundred_weight_decides_alone(tmp_path: Path) -> None:
    value = weights(0, 0, 100, stops_preference="CONNECTING")
    offers = [offer(1, "21:30", 30_000), offer(2, "09:00", 90_000, ("MIDDLE",), minutes=(120, 420))]
    assert valid(boundary(tmp_path / "a", offers, value, "20261203-02", "MIDDLE"))
    assert refused(boundary(tmp_path / "b", offers, value, "20261203-01", "WINDOW"), "best-score")


def test_the_wanted_seat_only_on_a_lower_scoring_offer(tmp_path: Path) -> None:
    value = weights(20, 30, 50)  # window 20, red-eye 30, nonstop 50
    offers = [offer(1, "21:30", 80_000, ("MIDDLE",)),  # 80
              offer(2, "22:00", 40_000, ("WINDOW",), minutes=(120, 420))]  # 50
    assert valid(boundary(tmp_path / "a", offers, value, "20261203-01", "MIDDLE"))
    assert refused(boundary(tmp_path / "b", offers, value, "20261203-02", "WINDOW"), "best-score")


def test_a_middle_seat_is_open_but_meets_no_seat_preference(tmp_path: Path) -> None:
    offers = [offer(1, "21:30", 50_000, ("AISLE", "MIDDLE"))]
    value = weights(20, 30, 50, seat_preference="AISLE")
    assert valid(boundary(tmp_path / "a", offers, value, "20261203-01", "AISLE"))
    assert refused(boundary(tmp_path / "b", offers, value, "20261203-01", "MIDDLE"), "best-score")
    assert refused(boundary(tmp_path / "c", offers, value, "20261203-01", "WINDOW"), "seat-open")


def test_no_flight_that_day_is_refused_before_booking(tmp_path: Path) -> None:
    with hand_built({DAY: []}):
        check = verifier.verify_input("get_trip", request())
        assert check["valid"] is False and "no flight flies" in check["message"]
        with pytest.raises(ValueError, match="no flight flies"):
            get_trip(request(), tmp_path)


# Missing --------------------------------------------------------------------------------------------


def test_booking_without_a_search_is_refused(tmp_path: Path) -> None:
    run = Run(request(), tmp_path, search=False)
    assert refused(run.judge(run.gold()), "searched")


@pytest.mark.parametrize("offer_id", ["20261203-99", "", "F01"])
def test_an_offer_never_returned_is_refused(tmp_path: Path, offer_id: str) -> None:
    run = Run(request(), tmp_path)
    assert refused(run.judge(booking(run.run_id, offer_id, "WINDOW")), "offer-seen")


@pytest.mark.parametrize("run_id", ["0123456789ab", "not-a-run", ""])
def test_a_run_that_does_not_exist_is_refused(tmp_path: Path, run_id: str) -> None:
    run = Run(request(), tmp_path)
    assert refused(run.judge(run.gold() | {"run_id": run_id}), "this-run")


def test_no_answer_key_is_refused(tmp_path: Path) -> None:
    run = Run(request(), tmp_path)
    assert refused(judge(run.request, run.gold(), None, run.workspace), "answer-key")


def test_an_answer_key_for_another_request_is_refused(tmp_path: Path) -> None:
    run = Run(request(), tmp_path)
    other = request(seat_weight=30, time_weight=20)
    assert refused(judge(other, run.gold(), run.key, run.workspace), "answer-key")


def test_every_check_after_a_failed_one_is_not_checked(tmp_path: Path) -> None:
    run = Run(request(), tmp_path, search=False)
    checks = run.judge(run.gold())["details"]["checks"]
    assert [entry["ok"] for entry in checks] == [True, True, False, None, None, None, None, None]


# Tampering ------------------------------------------------------------------------------------------


def edit(path: Path, **changes) -> None:
    value = json.loads(path.read_text())
    value.update(changes)
    path.write_text(json.dumps(value))


@pytest.mark.parametrize("changes", [{"digest": "0" * 64}, {"offer_ids": []}, {"origin": "XXX"},
                                     {"travel_date": "x"}, {"travel_date": "2026-12-04"}])
def test_a_tampered_search_receipt_is_refused(tmp_path: Path, changes: dict) -> None:
    run = Run(request(), tmp_path)
    edit(run.workspace / "runs" / run.run_id / "search-1.json", **changes)
    assert refused(run.judge(run.gold()), "receipts-match")


def test_a_run_begun_before_the_answer_key_is_refused(tmp_path: Path) -> None:
    run = Run(request(), tmp_path)
    edit(run.workspace / "runs" / run.run_id / "trip.json", started_at="2026-11-05 00:00:00.000000")
    verdict = run.judge(run.gold())
    assert refused(verdict, "this-run") and "earlier run" in verdict["message"]


def test_a_run_booked_another_day_or_for_other_weights_is_refused(tmp_path: Path) -> None:
    run = Run(request(), tmp_path)
    edit(run.workspace / "runs" / run.run_id / "trip.json", booking_date="2026-11-04")
    assert refused(run.judge(run.gold()), "this-run")
    run = Run(request(), tmp_path / "b")
    path = run.workspace / "runs" / run.run_id / "trip.json"
    edit(path, request=json.loads(path.read_text())["request"] | {"seat_weight": 50, "stops_weight": 20})
    assert refused(run.judge(run.gold()), "this-run")


def test_a_tampered_answer_key_is_refused(tmp_path: Path) -> None:
    run = Run(request(), tmp_path)
    run.key.best_score += 1
    assert refused(run.judge(run.gold()), "answer-key")


def test_an_answer_key_with_edited_offers_is_refused(tmp_path: Path) -> None:
    run = Run(request(), tmp_path)
    run.key.offers[0].open_seats = run.key.offers[0].open_seats[:1]
    run.key.offers[0].fare_cents += 1
    assert refused(run.judge(run.gold()), "answer-key")


# Determinism and the tools' own checks -----------------------------------------------------------------


def test_the_verdict_is_the_same_twice(tmp_path: Path) -> None:
    run = Run(request(), tmp_path)
    for output in (run.gold(), booking(run.run_id, run.offers[0].offer_id, "MIDDLE")):
        assert json.dumps(run.judge(output), sort_keys=True) == json.dumps(run.judge(output), sort_keys=True)


def test_tool_inputs_are_checked() -> None:
    good = plain_output(request())
    assert tool_input("get_trip", good)["valid"] is True
    assert tool_input("solve_booking", good | {"stops_preference": "CONNECTING"})["valid"] is True
    for bad in ({"destination": "ORD"}, {"travel_date": "2026-02-30"}, {"traveller_name": " "},
                {"seat_weight": 19}, {"seat_weight": 21}, {"seat_weight": -10, "time_weight": 60},
                {"seat_weight": 0, "time_weight": 0, "stops_weight": 0}):
        for tool in ("get_trip", "solve_booking"):
            verdict = tool_input(tool, good | bad)
            assert verdict["valid"] is False, (tool, bad)
    assert "= 99, not 100" in tool_input("get_trip", good | {"seat_weight": 19})["message"]
    query = {"run_id": "", "origin": "JFK", "destination": "LAX", "travel_date": "2027-03-01"}
    assert tool_input("search_flights", query)["valid"] is True
    assert tool_input("search_flights", query | {"run_id": "0123456789ab"})["valid"] is True
    for bad in ({"travel_date": "2027-02-30"}, {"run_id": "nope"}, {"destination": "JFK"}):
        assert tool_input("search_flights", query | bad)["valid"] is False, bad
    for topic in Topic:
        assert tool_input("booking_requirements", {"topic": topic.value})["valid"] is True


@pytest.mark.parametrize("bad", [{"origin": "XXX"}, {"seat_weight": 20.5}, {"seat_weight": "20"},
                                 {"seat_preference": "MIDDLE"}, {"time_preference": "NIGHT"}])
def test_values_of_the_wrong_kind_are_refused_by_the_contract(bad: dict) -> None:
    with pytest.raises(ValueError):
        tool_input("get_trip", plain_output(request()) | bad)


def test_tool_outputs_are_checked(tmp_path: Path) -> None:
    run = Run(request(), tmp_path)
    trip_out = build_output(plain_output(TripOutput(run.run_id, run.trip)), TripOutput)
    assert verifier.verify_output("get_trip", run.request, trip_out, str(run.workspace))["valid"] is True
    assert verifier.verify_output("get_trip", request(seat_preference="AISLE"), trip_out,
                                  str(run.workspace))["valid"] is False
    moved = build_output(plain_output(trip_out) | {"trip": plain_output(run.trip) | {"booking_date": "2026-12-04"}},
                         TripOutput)
    assert verifier.verify_output("get_trip", run.request, moved, str(run.workspace))["valid"] is False
    query = SearchInput(run.run_id, AirportCode.ORD, AirportCode.LHR, run.trip.travel_date)
    found = build_output(plain_output(SearchOutput(run.run_id, "Simulated fares and schedules; airline names are "
                                                   "used for realism only.", run.offers)), SearchOutput)
    assert verifier.verify_output("search_flights", query, found, str(run.workspace))["valid"] is True
    shifted = SearchInput(run.run_id, AirportCode.ORD, AirportCode.LHR, "2026-12-04")
    assert verifier.verify_output("search_flights", shifted, found, str(run.workspace))["valid"] is False
    found.offers[0].open_seats = ["WINDOW", "AISLE", "MIDDLE"] if len(found.offers[0].open_seats) < 3 else ["MIDDLE"]
    found = build_output(plain_output(found), SearchOutput)
    assert verifier.verify_output("search_flights", query, found, str(run.workspace))["valid"] is False
    found = build_output(plain_output(SearchOutput(run.run_id, "Real fares.", run.offers)), SearchOutput)
    assert verifier.verify_output("search_flights", query, found, str(run.workspace))["valid"] is False
    key = build_output(plain_output(run.key), SolveOutput)
    assert verifier.verify_output("solve_booking", run.request, key, str(tmp_path))["valid"] is True
    key.lowest_best_fare_cents -= 1
    assert verifier.verify_output("solve_booking", run.request, key, str(tmp_path))["valid"] is False


@pytest.mark.parametrize("topic", list(Topic))
def test_the_requirements_are_checked(tmp_path: Path, topic: Topic) -> None:
    given = RequirementsInput(topic)
    made = build_output(plain_output(booking_requirements(given, tmp_path)), RequirementsOutput)
    assert verifier.verify_output("booking_requirements", given, made, str(tmp_path))["valid"] is True
    assert verifier.verify_task("booking-requirements", given, made, None, str(tmp_path))["valid"] is True
    for change in ({"today": "2026-13-01"}, {"example_request": "Book anything."},
                   {"airports": [] if topic is not Topic.FIELDS else [{"code": "BOS", "name": "x", "city": "y",
                                                                         "country": "US"}]}):
        altered = build_output(plain_output(made) | change, RequirementsOutput)
        assert verifier.verify_output("booking_requirements", given, altered, str(tmp_path))["valid"] is False, change


def test_tool_tasks_are_judged_as_their_tools(tmp_path: Path) -> None:
    query = SearchInput("", AirportCode.JFK, AirportCode.LAX, "2026-12-01")
    found = build_output(plain_output(search_flights(query, tmp_path)), SearchOutput)
    assert verifier.verify_task("search-flights", query, found, None, str(tmp_path))["valid"] is True
    other = SearchInput("", AirportCode.JFK, AirportCode.SFO, "2026-12-01")
    assert verifier.verify_task("search-flights", other, found, None, str(tmp_path))["valid"] is False


def test_tools_refuse_past_and_far_dates_and_bad_weights(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="before today"):
        get_trip(request(travel_date="2026-11-04"), tmp_path)
    with pytest.raises(ValueError, match="330 days"):
        get_trip(request(travel_date="2027-10-02"), tmp_path)
    with pytest.raises(ValueError, match="not 100"):
        get_trip(request(seat_weight=21), tmp_path)
    with pytest.raises(ValueError, match="before today"):
        search_flights(SearchInput("", AirportCode.JFK, AirportCode.LAX, "2026-11-01"), tmp_path)
    with pytest.raises(ValueError, match="get_trip first"):
        search_flights(SearchInput("0123456789ab", AirportCode.JFK, AirportCode.LAX, "2026-12-01"), tmp_path)
