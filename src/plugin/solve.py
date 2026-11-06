"""solve_booking, the reference tool: the trip booked as of today, every offer that day and the bookings the
rules accept, pinned before the agent starts and never shown to it."""

from pathlib import Path

from contract import BestBooking, SolveOutput, TripInput
from plugin import receipts, world
from plugin.rules import solve
from plugin.trip import make_trip


def solve_booking(value: TripInput, workspace: Path) -> SolveOutput:
    stamp = receipts.CLOCK()
    trip = make_trip(value, stamp[:10])
    offers = world.offers_on(trip.origin.code, trip.destination.code, trip.travel_date)
    answer = solve(trip, offers)
    return SolveOutput(
        pinned_at=stamp,
        trip=trip,
        offers=offers,
        best_score=answer.best_score,
        lowest_best_fare_cents=answer.lowest_best_fare_cents,
        correct_bookings=[BestBooking(offer_id=offer_id, seat=seat) for offer_id, seat in answer.correct],
    )
