"""get_trip's checks: a request that can be booked (well formed, weights adding up to 100, flights that day),
the trip it states, and the run it began."""

from .checks import RUN_ID, read_json, result
from .rules import booking_date_problem, is_date, request_plain, request_problem, trip_matches_request
from .world import airport, offers_on


def flights_problem(value):
    """Why a well-formed request has no flight to book that day, or None."""
    if not offers_on(value.origin.value, value.destination.value, value.travel_date):
        return (f"no flight flies {value.origin.value}-{value.destination.value} on {value.travel_date}: "
                "ask for another day or another airport")
    return None


def input_problem(value):
    return request_problem(value) or flights_problem(value)


def verify_input(value):
    problem = input_problem(value)
    return result(problem is None, problem or "a well-formed trip request with flights that day")


def trip_problem(trip, request):
    """What is wrong with a trip stated for ``request`` (its booking date aside from the clock), or None."""
    if not trip_matches_request(trip, request):
        return "the trip is not the one the request asked for"
    if trip.origin != airport(trip.origin.code) or trip.destination != airport(trip.destination.code):
        return "the trip's airports are not the airport list's"
    if not is_date(trip.booking_date):
        return f"booking_date {trip.booking_date!r} is not a real YYYY-MM-DD date"
    return booking_date_problem(trip.travel_date, trip.booking_date)


def verify_output(input_value, output_value, workspace):
    trip = output_value.trip
    problem = trip_problem(trip, input_value)
    if problem:
        return result(False, problem)
    if not RUN_ID.fullmatch(output_value.run_id):
        return result(False, f"run_id {output_value.run_id!r} is not a run id")
    receipt = read_json(f"{workspace}/runs/{output_value.run_id}/trip.json")
    if (
        receipt is None
        or receipt.get("request") != request_plain(input_value)
        or receipt.get("booking_date") != trip.booking_date
    ):
        return result(False, f"run {output_value.run_id} has no receipt for this request in the workspace")
    return result(True, f"the trip of the request, booked {trip.booking_date}, run {output_value.run_id}")
