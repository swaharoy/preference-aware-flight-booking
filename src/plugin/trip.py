"""get_trip: the trip a request describes, booked as of today, with the traveller's preferences and weights,
and a new run to book it in."""

from pathlib import Path

from contract import Trip, TripInput, TripOutput
from plugin import receipts, world
from plugin.rules import booking_date_problem, request_plain, request_problem


def flights_problem(value: TripInput) -> str | None:
    """Why a request cannot be booked because no flight flies its route that day, or None."""
    if not world.offers_on(value.origin.value, value.destination.value, value.travel_date):
        return (f"no flight flies {value.origin.value}-{value.destination.value} on {value.travel_date}: "
                "ask for another day or another airport")
    return None


def make_trip(value: TripInput, booking_date: str) -> Trip:
    """The trip of a request on ``booking_date``; raises when it cannot be booked that day."""
    problem = request_problem(value) or booking_date_problem(value.travel_date, booking_date) or flights_problem(value)
    if problem:
        raise ValueError(problem)
    return Trip(
        traveller_name=value.traveller_name,
        origin=world.airport(value.origin.value),
        destination=world.airport(value.destination.value),
        booking_date=booking_date,
        travel_date=value.travel_date,
        seat_preference=value.seat_preference,
        seat_weight=value.seat_weight,
        time_preference=value.time_preference,
        time_weight=value.time_weight,
        stops_preference=value.stops_preference,
        stops_weight=value.stops_weight,
    )


def get_trip(value: TripInput, workspace: Path) -> TripOutput:
    stamp = receipts.CLOCK()
    trip = make_trip(value, stamp[:10])
    run_id = receipts.new_run(workspace, request_plain(value), trip.booking_date, stamp)
    return TripOutput(run_id=run_id, trip=trip)
