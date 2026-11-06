"""An independent reading of the task instructions, written without the plugin's rules module (its own time
parsing with datetime, its own enumeration of every offer and seat), to cross-check the answer key."""

from __future__ import annotations

from datetime import datetime


def red_eye(depart_local: str) -> bool:
    """A first departure from 21:00 local time on is a red-eye."""
    clock = datetime.strptime(depart_local, "%Y-%m-%d %H:%M").time()
    return clock.hour >= 21


def points(trip, offer, seat: str) -> int:
    total = 0
    if seat == trip.seat_preference.value:
        total += trip.seat_weight
    wanted_red_eye = trip.time_preference.value == "RED_EYE"
    if red_eye(offer.depart_local) == wanted_red_eye:
        total += trip.time_weight
    wants_nonstop = trip.stops_preference.value == "NONSTOP"
    if (offer.stops == 0 and wants_nonstop) or (offer.stops >= 1 and not wants_nonstop):
        total += trip.stops_weight
    return total


def booking_answer(trip, offers) -> set[tuple[str, str]]:
    """Every (offer id, seat) the instructions accept: the top score over all offers and open seats, then the
    lowest fare among the offers that reach it."""
    scored = [(points(trip, offer, seat.value), offer.fare_cents, offer.offer_id, seat.value)
              for offer in offers for seat in offer.open_seats]
    top = max(row[0] for row in scored)
    floor = min(row[1] for row in scored if row[0] == top)
    return {(row[2], row[3]) for row in scored if row[0] == top and row[1] == floor}
