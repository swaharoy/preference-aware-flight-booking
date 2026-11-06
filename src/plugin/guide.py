"""What a booking request must give, shared byte for byte by the booking_requirements tool
(src/plugin/guide.py) and the verifier (verifier/guide.py): every field of the booking task's input, read
from the contract, with an example; what the date, the weights and each preference mean; and the airports.
Definitions only, no advice on choosing: weighing the offers is the agent's job, not the traveller's. It
imports only modules a verifier may use, contract, and its package's shared modules.
"""

import dataclasses
import enum
import typing

from contract import AirportCode, AirportHelp, FieldHelp, RequirementsOutput, Topic, TripInput

from .rules import BOOKING_HORIZON_DAYS, WEIGHT_TOTAL, date_of, day_number
from .world import AIRPORTS

EXAMPLE_DEPARTURE_DAYS = 30  # the example request travels this many days after today


def example_date(today):
    return date_of(day_number(today) + EXAMPLE_DEPARTURE_DAYS)


def examples(today):
    return {
        "traveller_name": "Maya Chen",
        "origin": "ORD",
        "destination": "LHR",
        "travel_date": example_date(today),
        "seat_preference": "WINDOW",
        "seat_weight": "20",
        "time_preference": "RED_EYE",
        "time_weight": "30",
        "stops_preference": "NONSTOP",
        "stops_weight": "50",
    }


def kind_of(name, kind):
    """What kind of value a field takes, in words."""
    if isinstance(kind, type) and issubclass(kind, AirportCode):
        return f"an airport code from the airport list ({len(AIRPORTS)} airports)"
    if isinstance(kind, type) and issubclass(kind, enum.Enum):
        return "one of " + ", ".join(member.value for member in kind)
    if kind is int:
        return f"a whole number from 0 to {WEIGHT_TOTAL}"
    if name.endswith("_date"):
        return "a date, YYYY-MM-DD"
    return "text"


def fields(today):
    """Every field of the booking task's input, in the contract's order."""
    hints = typing.get_type_hints(TripInput, include_extras=True)
    example = examples(today)
    found = []
    for field in dataclasses.fields(TripInput):
        kind, description = typing.get_args(hints[field.name])
        found.append(FieldHelp(name=field.name, kind=kind_of(field.name, kind), required=True,
                               example=example[field.name], description=description))
    return found


def definitions(today):
    last = date_of(day_number(today) + BOOKING_HORIZON_DAYS)
    return [
        f"Today is {today} (UTC): a request made today is booked as of today.",
        (
            f"The travel date is YYYY-MM-DD, the day the flight leaves, as a date where it leaves from; flights are "
            f"sold from today up to {BOOKING_HORIZON_DAYS} days ahead, so the travel date is {today} to {last}."
        ),
        (
            f"Give three preferences, each with a weight: a whole percentage from 0 to {WEIGHT_TOTAL}. The three "
            f"weights add up to exactly {WEIGHT_TOTAL}; a weight of 0 means that preference does not matter."
        ),
        "Seat: WINDOW or AISLE. Flights may also have MIDDLE seats open, which are neither.",
        (
            "Time: DAY is a flight whose first departure is from 06:00 to 20:55 local time where it leaves from; "
            "RED_EYE is one leaving from 21:00 to 23:55 local time."
        ),
        "Stops: NONSTOP is a flight with no stop; CONNECTING is one with one connection or more.",
    ]


def airports():
    return [AirportHelp(code=row[0], name=row[1], city=row[2], country=row[3]) for row in AIRPORTS]


def example_request(today):
    return (
        f"Book a flight for Maya Chen from Chicago O'Hare (ORD) to London Heathrow (LHR) on {example_date(today)}. "
        "She would like a window seat (weight 20), a red-eye (weight 30) and a nonstop (weight 50)."
    )


def build(topic, today):
    """The requirements for ``topic`` as of ``today``."""
    wants_fields = topic in (Topic.ALL, Topic.FIELDS)
    wants_airports = topic in (Topic.ALL, Topic.AIRPORTS)
    return RequirementsOutput(
        today=today,
        fields=fields(today) if wants_fields else [],
        definitions=definitions(today) if wants_fields else [],
        airports=airports() if wants_airports else [],
        example_request=example_request(today),
    )
