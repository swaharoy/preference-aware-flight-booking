"""The traveller's weighted preferences as exact rules, shared byte for byte by the tools (src/plugin/rules.py)
and the verifier (verifier/rules.py): dates and times, what a trip request may be, the time of day of a
departure, the score of a booking, the bookings the rules accept, and the canonical form of requests and offers
both sides compare.

Exact integer arithmetic only, and no datetime (a verifier may not import it): a date is a day number and a
time a minute number. It imports only modules a verifier may use, and contract.
"""

import hashlib
import json
import re
from dataclasses import dataclass

from contract import SeatType, StopPreference, TimeOfDay

DATE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")
TIME = re.compile(r"^(\d{4}-\d{2}-\d{2}) (\d{2}):(\d{2})$")
WEIGHT_TOTAL = 100  # the three weights are whole percentages adding up to exactly 100
FIRST_DEPARTURE = 6 * 60  # flights leave from 06:00 local time
RED_EYE_FROM = 21 * 60  # a first departure from 21:00 local time on is a red-eye; before it, a day flight
LAST_DEPARTURE = 23 * 60 + 55  # and the last leaves at 23:55
BOOKING_HORIZON_DAYS = 330  # flights are sold up to this many days after today
NAME_MOST_CHARS = 80
SEAT_ORDER = (SeatType.WINDOW, SeatType.AISLE, SeatType.MIDDLE)  # the order open seats are listed in


def day_number(date):
    """Days since 1970-01-01 of a YYYY-MM-DD date; ValueError when it is not a real date."""
    match = DATE.fullmatch(date)
    if not match:
        raise ValueError(f"{date!r} is not a YYYY-MM-DD date")
    year, month, day = (int(part) for part in match.groups())
    if not 1 <= month <= 12 or not 1 <= day <= days_in_month(year, month):
        raise ValueError(f"{date!r} is not a real date")
    year -= month <= 2
    era = year // 400
    year_of_era = year - era * 400
    day_of_year = (153 * (month + (-3 if month > 2 else 9)) + 2) // 5 + day - 1
    day_of_era = year_of_era * 365 + year_of_era // 4 - year_of_era // 100 + day_of_year
    return era * 146097 + day_of_era - 719468


def date_of(number):
    """The YYYY-MM-DD date of a day number."""
    number += 719468
    era = number // 146097
    day_of_era = number - era * 146097
    year_of_era = (day_of_era - day_of_era // 1460 + day_of_era // 36524 - day_of_era // 146096) // 365
    day_of_year = day_of_era - (365 * year_of_era + year_of_era // 4 - year_of_era // 100)
    shifted = (5 * day_of_year + 2) // 153
    day = day_of_year - (153 * shifted + 2) // 5 + 1
    month = shifted + (3 if shifted < 10 else -9)
    year = year_of_era + era * 400 + (month <= 2)
    return f"{year:04d}-{month:02d}-{day:02d}"


def days_in_month(year, month):
    if month == 2:
        return 29 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 28
    return 30 if month in (4, 6, 9, 11) else 31


def is_date(text):
    try:
        day_number(text)
    except ValueError:
        return False
    return True


def minute_number(time):
    """Minutes since 1970-01-01 00:00 of a YYYY-MM-DD HH:MM time; ValueError when it is not one."""
    match = TIME.fullmatch(time)
    if not match:
        raise ValueError(f"{time!r} is not a YYYY-MM-DD HH:MM time")
    date, hour, minute = match.group(1), int(match.group(2)), int(match.group(3))
    if hour > 23 or minute > 59:
        raise ValueError(f"{time!r} is not a real time")
    return day_number(date) * 1440 + hour * 60 + minute


def request_problem(request):
    """What is wrong with a trip request on its own (no clock or flights needed), or None."""
    if not request.traveller_name.strip():
        return "traveller_name is blank: give the traveller's name"
    if len(request.traveller_name) > NAME_MOST_CHARS:
        return f"traveller_name is longer than {NAME_MOST_CHARS} characters"
    if request.origin is request.destination:
        return f"origin and destination are both {request.origin.value}: give two different airports"
    if not is_date(request.travel_date):
        return f"travel_date {request.travel_date!r} is not a real YYYY-MM-DD date"
    weights = {"seat_weight": request.seat_weight, "time_weight": request.time_weight,
               "stops_weight": request.stops_weight}
    for name, weight in weights.items():
        if not 0 <= weight <= WEIGHT_TOTAL:
            return f"{name} is {weight}: each weight is a whole percentage from 0 to {WEIGHT_TOTAL}"
    total = sum(weights.values())
    if total != WEIGHT_TOTAL:
        listed = " + ".join(str(weight) for weight in weights.values())
        return f"the weights add up to {listed} = {total}, not {WEIGHT_TOTAL}: they must add up to exactly {WEIGHT_TOTAL}"
    return None


def booking_date_problem(travel_date, booking_date):
    """What is wrong with travelling on ``travel_date`` booked on ``booking_date`` (today), or None."""
    if day_number(travel_date) < day_number(booking_date):
        return f"travel_date {travel_date} is before today, {booking_date}: flights cannot leave in the past"
    if day_number(travel_date) > day_number(booking_date) + BOOKING_HORIZON_DAYS:
        return (f"travel_date {travel_date} is more than {BOOKING_HORIZON_DAYS} days after today, {booking_date}: "
                "flights are not sold that far ahead")
    return None


def request_plain(request):
    """A trip request as plain JSON values, the form receipts record and the verifier compares."""
    return {
        "traveller_name": request.traveller_name,
        "origin": request.origin.value,
        "destination": request.destination.value,
        "travel_date": request.travel_date,
        "seat_preference": request.seat_preference.value,
        "seat_weight": request.seat_weight,
        "time_preference": request.time_preference.value,
        "time_weight": request.time_weight,
        "stops_preference": request.stops_preference.value,
        "stops_weight": request.stops_weight,
    }


def trip_matches_request(trip, request):
    """Whether a trip states exactly what the request asked for."""
    return (
        trip.traveller_name == request.traveller_name
        and trip.origin.code == request.origin.value
        and trip.destination.code == request.destination.value
        and trip.travel_date == request.travel_date
        and trip.seat_preference is request.seat_preference
        and trip.seat_weight == request.seat_weight
        and trip.time_preference is request.time_preference
        and trip.time_weight == request.time_weight
        and trip.stops_preference is request.stops_preference
        and trip.stops_weight == request.stops_weight
    )


def time_of_day(depart_local):
    """DAY when the first flight leaves before 21:00 local time (from 06:00), RED_EYE from 21:00 to 23:59."""
    return TimeOfDay.RED_EYE if minute_number(depart_local) % 1440 >= RED_EYE_FROM else TimeOfDay.DAY


def seat_points(trip, seat):
    """The seat weight when the seat is the one wanted (MIDDLE never is), else 0."""
    return trip.seat_weight if seat.value == trip.seat_preference.value else 0


def time_points(trip, offer):
    """The time weight when the first flight leaves at the time of day wanted, else 0."""
    return trip.time_weight if time_of_day(offer.depart_local) is trip.time_preference else 0


def stops_points(trip, offer):
    """The stops weight when NONSTOP is wanted and the offer has no stop, or CONNECTING and it has one or more."""
    nonstop = offer.stops == 0
    return trip.stops_weight if nonstop == (trip.stops_preference is StopPreference.NONSTOP) else 0


def score(trip, offer, seat):
    """The score of booking ``seat`` on ``offer``: the sum of the weights of the preferences it meets."""
    return seat_points(trip, seat) + time_points(trip, offer) + stops_points(trip, offer)


def score_text(trip, offer, seat):
    """A score as its parts, e.g. "seat 0 + time 30 + stops 40 = 70"."""
    parts = (seat_points(trip, seat), time_points(trip, offer), stops_points(trip, offer))
    return f"seat {parts[0]} + time {parts[1]} + stops {parts[2]} = {sum(parts)}"


def offer_best(trip, offer):
    """The highest score any open seat on ``offer`` reaches."""
    return max(score(trip, offer, seat) for seat in offer.open_seats)


@dataclass
class Answer:
    """The bookings the rules accept for a trip and its offers."""

    best_score: int  # the highest score of any offer and open seat
    lowest_best_fare_cents: int  # the lowest fare among the offers reaching it
    correct: list  # (offer id, seat) pairs that are correct bookings, in offer order then seat order


def solve(trip, offers):
    """P1 the highest score over every offer and open seat; P2 among the offers reaching it, the lowest fare
    (any of them when tied), with any open seat reaching it. Raises when there is no offer to book."""
    if not offers:
        raise ValueError("no offers to book: no flight flies the route that day")
    best = max(offer_best(trip, offer) for offer in offers)
    lowest = min(offer.fare_cents for offer in offers if offer_best(trip, offer) == best)
    correct = [
        (offer.offer_id, seat)
        for offer in offers
        if offer.fare_cents == lowest and offer_best(trip, offer) == best
        for seat in SEAT_ORDER
        if seat in offer.open_seats and score(trip, offer, seat) == best
    ]
    return Answer(best, lowest, correct)


def segment_plain(segment):
    return {
        "origin": segment.origin,
        "destination": segment.destination,
        "flight_number": segment.flight_number,
        "depart": segment.depart,
        "arrive": segment.arrive,
        "air_minutes": segment.air_minutes,
    }


def offer_plain(offer):
    """An offer as plain JSON values, the form both sides hash."""
    return {
        "offer_id": offer.offer_id,
        "carrier": offer.carrier,
        "stops": offer.stops,
        "depart_local": offer.depart_local,
        "arrive_local": offer.arrive_local,
        "total_minutes": offer.total_minutes,
        "time_of_day": offer.time_of_day.value,
        "open_seats": [seat.value for seat in offer.open_seats],
        "fare_cents": offer.fare_cents,
        "segments": [segment_plain(segment) for segment in offer.segments],
    }


def offers_digest(offers):
    """The SHA-256 of a list of offers in their canonical JSON form."""
    text = json.dumps([offer_plain(offer) for offer in offers], sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def same_offers(left, right):
    """Whether two lists of offers are the same offers, in the same order."""
    return [offer_plain(offer) for offer in left] == [offer_plain(offer) for offer in right]
