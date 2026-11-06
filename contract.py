"""Each tool's and task's typed input and output (see nanoagent.plugin.v0001.contract): declarations only."""

from dataclasses import dataclass
from enum import Enum
from typing import Annotated

from slimconfig import Output


class Tool(Enum):
    BOOKING_REQUIREMENTS = "booking_requirements"
    GET_TRIP = "get_trip"
    SEARCH_FLIGHTS = "search_flights"
    SOLVE_BOOKING = "solve_booking"


class Task(Enum):
    BOOKING_REQUIREMENTS = "booking-requirements"
    SEARCH_FLIGHTS = "search-flights"
    BOOK_FLIGHT = "preference-aware-flight-booking"


class AirportCode(Enum):
    """The airports this plugin knows, by IATA code (booking_requirements lists their names and cities)."""

    ATL = "ATL"
    LAX = "LAX"
    ORD = "ORD"
    DFW = "DFW"
    DEN = "DEN"
    JFK = "JFK"
    SFO = "SFO"
    SEA = "SEA"
    LAS = "LAS"
    MCO = "MCO"
    EWR = "EWR"
    MIA = "MIA"
    CLT = "CLT"
    PHX = "PHX"
    IAH = "IAH"
    BOS = "BOS"
    MSP = "MSP"
    DTW = "DTW"
    PHL = "PHL"
    LGA = "LGA"
    BWI = "BWI"
    SLC = "SLC"
    SAN = "SAN"
    IAD = "IAD"
    DCA = "DCA"
    TPA = "TPA"
    AUS = "AUS"
    BNA = "BNA"
    HNL = "HNL"
    ANC = "ANC"
    STL = "STL"
    YYZ = "YYZ"
    YVR = "YVR"
    YUL = "YUL"
    YHZ = "YHZ"
    MEX = "MEX"
    CUN = "CUN"
    LHR = "LHR"
    CDG = "CDG"
    FRA = "FRA"
    AMS = "AMS"
    MAD = "MAD"
    FCO = "FCO"
    MUC = "MUC"
    ZRH = "ZRH"
    DUB = "DUB"
    LIS = "LIS"
    CPH = "CPH"
    BCN = "BCN"
    VIE = "VIE"
    BRU = "BRU"
    OSL = "OSL"
    ARN = "ARN"
    KEF = "KEF"
    MAN = "MAN"
    EDI = "EDI"
    SNN = "SNN"
    NRT = "NRT"
    ICN = "ICN"
    SIN = "SIN"
    HKG = "HKG"
    DXB = "DXB"
    DEL = "DEL"
    BOM = "BOM"
    SYD = "SYD"
    GRU = "GRU"
    BOG = "BOG"
    JNB = "JNB"


class SeatPreference(Enum):
    """The seat the traveller would like."""

    WINDOW = "WINDOW"
    AISLE = "AISLE"


class SeatType(Enum):
    """A seat type that may be open on a flight; MIDDLE meets no seat preference."""

    WINDOW = "WINDOW"
    AISLE = "AISLE"
    MIDDLE = "MIDDLE"


class TimeOfDay(Enum):
    """DAY: the first flight leaves 06:00-20:55 local time at the origin. RED_EYE: it leaves 21:00-23:55."""

    DAY = "DAY"
    RED_EYE = "RED_EYE"


class StopPreference(Enum):
    """NONSTOP: no stop. CONNECTING: one connection or more."""

    NONSTOP = "NONSTOP"
    CONNECTING = "CONNECTING"


class Topic(Enum):
    ALL = "ALL"
    FIELDS = "FIELDS"
    AIRPORTS = "AIRPORTS"


RUN_ID = "This booking run's id, as get_trip returned it"
TIME = "A UTC time, YYYY-MM-DD HH:MM"
CODE = "An IATA airport code, e.g. JFK"
WEIGHT = "How much it matters, a whole percentage 0-100; the three weights add up to exactly 100"


@dataclass
class Airport(Output):
    code: Annotated[str, CODE]
    name: Annotated[str, "The airport's name"]
    city: Annotated[str, "The city it serves"]
    country: Annotated[str, "Its ISO 3166 country code, e.g. US"]


@dataclass
class Segment(Output):
    origin: Annotated[str, CODE]
    destination: Annotated[str, CODE]
    flight_number: Annotated[str, "The airline's flight number, e.g. DL 1482"]
    depart: Annotated[str, TIME]
    arrive: Annotated[str, TIME]
    air_minutes: Annotated[int, "The flight's scheduled minutes, gate to gate"]


@dataclass
class Offer(Output):
    offer_id: Annotated[str, "The offer's id: its travel date and number, e.g. 20261203-07"]
    carrier: Annotated[str, "The airline"]
    stops: Annotated[int, "Connections: 0 for a nonstop, 1 for one connection"]
    depart_local: Annotated[str, "When the first flight leaves, YYYY-MM-DD HH:MM local time at the origin"]
    arrive_local: Annotated[str, "When the last flight lands, YYYY-MM-DD HH:MM local time at the destination"]
    total_minutes: Annotated[int, "Minutes from the first departure to the last arrival, connections included"]
    time_of_day: Annotated[TimeOfDay, "DAY if the first flight leaves 06:00-20:55 local time, RED_EYE if 21:00-23:55"]
    open_seats: Annotated[list[SeatType], "The seat types still open, in the order WINDOW, AISLE, MIDDLE"]
    fare_cents: Annotated[int, "The one-way economy fare, in US cents"]
    segments: Annotated[list[Segment], "The flights, in order"]


@dataclass
class Trip(Output):
    traveller_name: Annotated[str, "The traveller's name"]
    origin: Annotated[Airport, "The airport the trip leaves from"]
    destination: Annotated[Airport, "The airport the trip goes to"]
    booking_date: Annotated[str, "Today, the day the flight is booked, YYYY-MM-DD (UTC)"]
    travel_date: Annotated[str, "The day of travel, YYYY-MM-DD (local date at the origin)"]
    seat_preference: Annotated[SeatPreference, "The seat the traveller would like"]
    seat_weight: Annotated[int, WEIGHT]
    time_preference: Annotated[TimeOfDay, "The time of day the traveller would like to leave"]
    time_weight: Annotated[int, WEIGHT]
    stops_preference: Annotated[StopPreference, "Whether the traveller would like a nonstop or a connection"]
    stops_weight: Annotated[int, WEIGHT]


@dataclass
class TripInput(Output):
    traveller_name: Annotated[str, "The traveller's full name, as on the ticket"]
    origin: Annotated[AirportCode, "The airport to leave from, by IATA code (e.g. ORD for Chicago O'Hare)"]
    destination: Annotated[AirportCode, "The airport to fly to, by IATA code (e.g. LHR for London Heathrow)"]
    travel_date: Annotated[str, "The day to travel, YYYY-MM-DD (local date at the origin), today or later"]
    seat_preference: Annotated[SeatPreference, "WINDOW or AISLE"]
    seat_weight: Annotated[int, "How much the seat matters, a whole percentage 0-100"]
    time_preference: Annotated[TimeOfDay, "DAY for a daytime departure, RED_EYE for a late-night one"]
    time_weight: Annotated[int, "How much the departure time matters, a whole percentage 0-100"]
    stops_preference: Annotated[StopPreference, "NONSTOP for a direct flight, CONNECTING for one with a connection"]
    stops_weight: Annotated[int, "How much nonstop or connecting matters, a whole percentage 0-100; the three "
                                 "weights add up to exactly 100"]


@dataclass
class TripOutput(Output):
    run_id: Annotated[str, "This booking run's id: pass it to search_flights and submit it"]
    trip: Annotated[Trip, "The trip to book, with the traveller's preferences and weights"]


@dataclass
class SearchInput(Output):
    run_id: Annotated[str, "This booking run's id, as get_trip returned it; empty to only look, outside a booking"]
    origin: Annotated[AirportCode, "The airport to leave from"]
    destination: Annotated[AirportCode, "The airport to fly to"]
    travel_date: Annotated[str, "The day to search, YYYY-MM-DD (local date at the origin), today or later"]


@dataclass
class SearchOutput(Output):
    run_id: Annotated[str, RUN_ID]
    note: Annotated[str, "Where the offers come from: simulated fares and schedules"]
    offers: Annotated[list[Offer], "Every one-way offer on the route that day, by departure"]


@dataclass
class BookingOutput(Output):
    run_id: Annotated[str, RUN_ID]
    offer_id: Annotated[str, "The booked offer's id"]
    seat: Annotated[SeatType, "The seat type booked: one of the offer's open_seats"]


@dataclass
class BestBooking(Output):
    offer_id: Annotated[str, "An offer that is a correct booking"]
    seat: Annotated[SeatType, "A seat on it that reaches the best score"]


@dataclass
class SolveOutput(Output):
    pinned_at: Annotated[str, "When the answer key was pinned, UTC YYYY-MM-DD HH:MM:SS.ffffff"]
    trip: Annotated[Trip, "The trip, with today as its booking date"]
    offers: Annotated[list[Offer], "Every offer on the route that day"]
    best_score: Annotated[int, "The highest score any offer and open seat reaches"]
    lowest_best_fare_cents: Annotated[int, "The lowest fare among the offers that reach the best score"]
    correct_bookings: Annotated[list[BestBooking], "Every offer and seat that is a correct booking"]


@dataclass
class RequirementsInput(Output):
    topic: Annotated[Topic, "ALL for everything, FIELDS for what to tell us, AIRPORTS for the airport list"]


@dataclass
class FieldHelp(Output):
    name: Annotated[str, "The field's name"]
    kind: Annotated[str, "What kind of value it takes"]
    required: Annotated[bool, "Whether every booking request must give it"]
    example: Annotated[str, "An example value"]
    description: Annotated[str, "What it means"]


@dataclass
class AirportHelp(Output):
    code: Annotated[str, CODE]
    name: Annotated[str, "The airport's name"]
    city: Annotated[str, "The city it serves"]
    country: Annotated[str, "Its ISO 3166 country code"]


@dataclass
class RequirementsOutput(Output):
    today: Annotated[str, "Today, the booking date, YYYY-MM-DD (UTC)"]
    fields: Annotated[list[FieldHelp], "What a booking request gives, field by field; empty for AIRPORTS"]
    definitions: Annotated[list[str], "How the date, the weights and each preference work; empty for AIRPORTS"]
    airports: Annotated[list[AirportHelp], "The airports a trip may use; empty for FIELDS"]
    example_request: Annotated[str, "A complete booking request in plain words"]


TOOLS = {
    Tool.BOOKING_REQUIREMENTS: (RequirementsInput, RequirementsOutput),
    Tool.GET_TRIP: (TripInput, TripOutput),
    Tool.SEARCH_FLIGHTS: (SearchInput, SearchOutput),
    Tool.SOLVE_BOOKING: (TripInput, SolveOutput),
}
TASKS = {
    Task.BOOKING_REQUIREMENTS: (RequirementsInput, RequirementsOutput),
    Task.SEARCH_FLIGHTS: (SearchInput, SearchOutput),
    Task.BOOK_FLIGHT: (TripInput, BookingOutput),
}
