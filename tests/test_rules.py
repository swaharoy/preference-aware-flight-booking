"""The scoring rules P1-P2, the time of day and the request checks on hand-built trips and offers, every boundary
included."""

from __future__ import annotations

import pytest
from helpers import offer, request
from slimconfig import build_output

from contract import Airport, Offer, SeatPreference, SeatType, StopPreference, TimeOfDay, Trip
from plugin.rules import (
    booking_date_problem,
    date_of,
    day_number,
    minute_number,
    offer_best,
    request_problem,
    score,
    score_text,
    solve,
    time_of_day,
)

ORD = Airport("ORD", "O'Hare", "Chicago", "US")
LHR = Airport("LHR", "Heathrow", "London", "GB")
W, A, M = SeatType.WINDOW, SeatType.AISLE, SeatType.MIDDLE


def trip(seat=("WINDOW", 20), time=("RED_EYE", 30), stops=("NONSTOP", 50)) -> Trip:
    return Trip("Test Traveller", ORD, LHR, "2026-11-05", "2026-12-03", SeatPreference(seat[0]), seat[1],
                TimeOfDay(time[0]), time[1], StopPreference(stops[0]), stops[1])


def made(*args, **kwargs) -> Offer:
    return build_output(offer(*args, **kwargs), Offer)


def test_dates_and_times_round_trip_and_reject_impossible_values() -> None:
    for text in ("1970-01-01", "2000-02-29", "2027-12-31", "2028-02-29", "2100-03-01"):
        assert date_of(day_number(text)) == text
    for bad in ("2027-02-29", "2027-13-01", "2027-1-01", "tomorrow"):
        with pytest.raises(ValueError):
            day_number(bad)
    assert minute_number("2027-01-02 00:00") - minute_number("2027-01-01 23:59") == 1
    for bad in ("2027-01-01 24:00", "2027-01-01 9:00", "2027-01-01 12:60"):
        with pytest.raises(ValueError):
            minute_number(bad)


@pytest.mark.parametrize(("clock", "kind"), [("06:00", "DAY"), ("12:00", "DAY"), ("20:55", "DAY"), ("20:59", "DAY"),
                                             ("21:00", "RED_EYE"), ("22:30", "RED_EYE"), ("23:55", "RED_EYE")])
def test_a_red_eye_leaves_from_21_00_local_time(clock: str, kind: str) -> None:
    assert time_of_day(f"2026-12-03 {clock}") is TimeOfDay(kind)


def test_requests_are_checked_on_their_own() -> None:
    assert request_problem(request()) is None
    assert "both ORD" in request_problem(request(destination="ORD"))
    assert "not a real" in request_problem(request(travel_date="2026-02-30"))
    assert "blank" in request_problem(request(traveller_name="  "))
    assert "= 99, not 100" in request_problem(request(seat_weight=19))
    assert "= 101, not 100" in request_problem(request(seat_weight=21))
    assert "seat_weight is -10" in request_problem(request(seat_weight=-10, time_weight=60))
    assert "time_weight is 101" in request_problem(request(seat_weight=0, time_weight=101, stops_weight=-1))
    for weights in ((100, 0, 0), (0, 100, 0), (0, 0, 100), (34, 33, 33), (0, 50, 50)):
        assert request_problem(request(seat_weight=weights[0], time_weight=weights[1],
                                       stops_weight=weights[2])) is None, weights
    assert booking_date_problem("2026-11-05", "2026-11-05") is None
    assert "before today" in booking_date_problem("2026-11-04", "2026-11-05")
    assert booking_date_problem("2027-10-01", "2026-11-05") is None
    assert "330 days" in booking_date_problem("2027-10-02", "2026-11-05")


def test_the_score_adds_the_weights_of_the_preferences_met() -> None:
    t = trip()
    nonstop_red_eye = made(1, "21:00", 50_000)
    connecting_day = made(2, "20:55", 40_000, minutes=(120, 400))
    assert score(t, nonstop_red_eye, W) == 100 and score(t, nonstop_red_eye, A) == 80
    assert score(t, nonstop_red_eye, M) == 80, "a middle seat meets no seat preference"
    assert score(t, connecting_day, W) == 20 and score(t, connecting_day, M) == 0
    assert score_text(t, nonstop_red_eye, A) == "seat 0 + time 30 + stops 50 = 80"
    connecting = trip(stops=("CONNECTING", 50))
    assert score(connecting, connecting_day, A) == 50
    two_stops = made(3, "09:00", 30_000, minutes=(100, 100))
    two_stops.stops = 2
    assert score(connecting, two_stops, A) == 50, "two stops is connecting too"


def test_two_smaller_weights_beat_one_larger() -> None:
    t = trip(seat=("WINDOW", 30), time=("DAY", 30), stops=("NONSTOP", 40))
    window_day_connection = made(1, "10:00", 90_000, ("WINDOW",), minutes=(120, 400))
    middle_red_eye_nonstop = made(2, "22:00", 40_000, ("MIDDLE",))
    answer = solve(t, [window_day_connection, middle_red_eye_nonstop])
    assert answer.best_score == 60 and answer.correct == [("20261203-01", W)]


def test_the_lowest_fare_settles_an_equal_score_and_an_exact_tie_accepts_both() -> None:
    t = trip()
    first, second = made(1, "21:30", 50_000), made(2, "22:30", 50_001)
    assert solve(t, [first, second]).correct == [("20261203-01", W)]
    second.fare_cents = 50_000
    answer = solve(t, [first, second])
    assert answer.correct == [("20261203-01", W), ("20261203-02", W)] and answer.lowest_best_fare_cents == 50_000


def test_a_zero_weight_never_matters_and_any_open_seat_reaches_the_score() -> None:
    t = trip(seat=("WINDOW", 0), time=("DAY", 40), stops=("NONSTOP", 60))
    day = made(1, "09:00", 60_000, ("AISLE", "MIDDLE"))
    assert solve(t, [day]).correct == [("20261203-01", A), ("20261203-01", M)]


def test_a_hundred_weight_decides_alone() -> None:
    t = trip(seat=("AISLE", 0), time=("RED_EYE", 100), stops=("NONSTOP", 0))
    day, late = made(1, "20:55", 30_000), made(2, "21:00", 90_000, ("MIDDLE",), minutes=(120, 400))
    answer = solve(t, [day, late])
    assert answer.best_score == 100 and answer.correct == [("20261203-02", M)]


def test_the_wanted_seat_on_a_lower_scoring_offer_does_not_help() -> None:
    t = trip(seat=("WINDOW", 20), time=("DAY", 30), stops=("NONSTOP", 50))
    best = made(1, "09:00", 80_000, ("MIDDLE",))  # 30 + 50
    window = made(2, "09:30", 40_000, ("WINDOW",), minutes=(120, 400))  # 20 + 30
    assert offer_best(t, best) == 80 and offer_best(t, window) == 50
    assert solve(t, [best, window]).correct == [("20261203-01", M)]


def test_no_offer_to_book_raises() -> None:
    with pytest.raises(ValueError, match="no offers"):
        solve(trip(), [])
