"""The preference-aware-flight-booking verdict: named checks, in order, on the answer key, the run the
submission names, its search receipts, and the booking against rules P1-P2.

Every search receipt is checked against the simulated world rebuilt here (verifier/world.py, the tools' own
file), so any offer the agent saw, on any day it searched, is known exactly.

The first five checks are integrity gates; the rest are the rules. The verdict is valid, scoring 1, only when
every check holds; any failure, gate or rule, scores 0: a booking reaches the traveller's best or it does not.
A check that depends on a failed one is "not checked". Expected values come from the verifier's own copy of
the rules applied to the pinned trip and offers; the answer key's own bookings are checked to agree with them.
The details also give the booked offer's points, preference by preference ("points"), for the result card.
"""

from .checks import check, result, run_files
from .rules import (
    offer_best,
    offers_digest,
    request_plain,
    score,
    score_text,
    seat_points,
    solve,
    stops_points,
    time_points,
)
from .solve import answer_key_problem
from .world import offers_on

TEXT = {
    "answer-key": "The answer key pinned this request's trip, booked today, its offers, and the bookings the rules "
                  "accept",
    "this-run": "The submission names a run get_trip began for this request on the same booking date, after the "
                "answer key",
    "searched": "The agent searched for flights in this run",
    "receipts-match": "Every search in this run returned exactly the route's offers for its query",
    "offer-seen": "The booked offer was among this run's search results for the trip's route and travel date",
    "seat-open": "The booked seat type is open on the offer",
    "best-score": "P1: the offer and seat reach the highest score of any offer and open seat that day",
    "lowest-fare-among-best": "P2: among the offers reaching that score, the lowest fare (any when tied)",
}
GATES = ("answer-key", "this-run", "searched", "receipts-match", "offer-seen")
RULES = ("seat-open", "best-score", "lowest-fare-among-best")


def money(cents):
    return f"${cents // 100}.{cents % 100:02d}"


def a_seat(seat):
    """"a WINDOW seat", "an AISLE seat", "a MIDDLE seat"."""
    return f"{'an' if seat.value == 'AISLE' else 'a'} {seat.value} seat"


def seat_names(seats):
    return ", ".join(seat.value for seat in seats)


class Verdict:
    def __init__(self):
        self.entries = {}
        self.blocked_by = None
        self.extra = {}

    def add(self, check_id, ok, expected="", actual="", message=""):
        if self.blocked_by is not None:
            self.entries[check_id] = check(
                check_id, TEXT[check_id], None, message=f"not checked: {self.blocked_by} failed"
            )
            return
        self.entries[check_id] = check(check_id, TEXT[check_id], ok, expected, actual, message)
        if not ok:
            self.blocked_by = check_id

    def finish(self):
        for check_id in GATES + RULES:
            if check_id not in self.entries:
                self.add(check_id, None)
        entries = [self.entries[check_id] for check_id in GATES + RULES]
        failed = [entry for entry in entries if entry["ok"] is False]
        if not failed:
            return result(True, "valid: the booking reaches the best score at the lowest fare", score=1.0,
                          checks=entries, **self.extra)
        first = failed[0]
        return result(False, f"{first['id']}: {first['message']}", score=0.0, checks=entries, **self.extra)


def receipts_check(verdict, searches):
    """receipts-match: every search receipt equals the world's offers for its query. Returns the searches as
    (origin, destination, travel date, offer ids), in call order."""
    found = []
    mismatch = None
    for number, receipt in enumerate(searches, start=1):
        if not isinstance(receipt, dict):
            mismatch = f"search {number}'s receipt is unreadable"
            break
        try:
            expected = offers_on(receipt["origin"], receipt["destination"], receipt["travel_date"])
        except (KeyError, TypeError, ValueError):
            mismatch = f"search {number}'s receipt is malformed"
            break
        ids = [offer.offer_id for offer in expected]
        if receipt.get("offer_ids") != ids or receipt.get("digest") != offers_digest(expected):
            mismatch = f"search {number} returned offers other than the route's offers for its query"
            break
        found.append((receipt["origin"], receipt["destination"], receipt["travel_date"], ids))
    verdict.add("receipts-match", mismatch is None, "receipts equal to the route's offers", mismatch or "equal",
                mismatch or f"{len(searches)} search receipts match the simulated offers")
    return found


def gates(verdict, arguments, output, reference, workspace):
    """The integrity gates, in order."""
    problem = "no answer key was pinned" if reference is None else answer_key_problem(arguments, reference)
    route = f"{arguments.origin.value}-{arguments.destination.value} {arguments.travel_date}"
    verdict.add("answer-key", problem is None, f"the key of {route}",
                "none" if reference is None else f"booked {reference.trip.booking_date}",
                problem or "the answer key is this request's and follows the rules")
    if problem is not None:
        return
    trip = reference.trip

    started, searches = run_files(workspace, output.run_id)
    if not isinstance(started, dict) or started.get("request") != request_plain(arguments):
        verdict.add("this-run", False, "a run of this request", output.run_id,
                    f"the workspace holds no run {output.run_id!r} begun by get_trip for this request")
    elif started.get("booking_date") != trip.booking_date:
        verdict.add("this-run", False, f"booked {trip.booking_date}", f"booked {started.get('booking_date')}",
                    f"run {output.run_id} was booked on another day than the answer key")
    elif not isinstance(started.get("started_at"), str) or started["started_at"] < reference.pinned_at:
        verdict.add("this-run", False, f"begun after {reference.pinned_at}", str(started.get("started_at")),
                    f"run {output.run_id} began before this task's answer key: it is an earlier run")
    else:
        verdict.add("this-run", True, actual=output.run_id,
                    message=f"run {output.run_id} began at {started['started_at']}")

    verdict.add("searched", bool(searches), "at least one search_flights call", f"{len(searches)} searches",
                "searched" if searches else "the agent booked without calling search_flights in this run")
    if verdict.blocked_by is not None:
        return
    found = receipts_check(verdict, searches)
    if verdict.blocked_by is not None:
        return

    wanted = (trip.origin.code, trip.destination.code, trip.travel_date)
    where = f"{wanted[0]}-{wanted[1]} on {wanted[2]}"
    if any((o, d, t) == wanted and output.offer_id in ids for o, d, t, ids in found):
        verdict.add("offer-seen", True, f"an offer of {where}", output.offer_id,
                    f"offer {output.offer_id} was in this run's search of {where}")
        return
    elsewhere = [f"{o}-{d} on {t}" for o, d, t, ids in found if output.offer_id in ids]
    if elsewhere:
        message = (f"offer {output.offer_id} was in this run's search of {elsewhere[0]}, not of the trip's route "
                   f"and date, {where}")
    else:
        message = f"offer {output.offer_id!r} was not among this run's search results"
    verdict.add("offer-seen", False, f"an offer of {where}", output.offer_id, message)


def verify_task(arguments, output, reference, workspace):
    verdict = Verdict()
    gates(verdict, arguments, output, reference, workspace)
    if verdict.blocked_by is not None:
        return verdict.finish()
    trip, offers = reference.trip, reference.offers
    answer = solve(trip, offers)
    offer = next(o for o in offers if o.offer_id == output.offer_id)
    seat = output.seat
    oid = offer.offer_id
    verdict.extra = {"points": {
        "seat": seat_points(trip, seat), "time": time_points(trip, offer), "stops": stops_points(trip, offer),
        "total": score(trip, offer, seat), "best": answer.best_score,
    }}

    # The seat must be open.
    is_open = seat in offer.open_seats
    verdict.add("seat-open", is_open, f"one of {seat_names(offer.open_seats)}", seat.value,
                f"{a_seat(seat)} is open on offer {oid}" if is_open else
                f"no {seat.value} seat is open on offer {oid}: its open seats are {seat_names(offer.open_seats)}")
    if verdict.blocked_by is not None:
        return verdict.finish()

    # P1: the best score.
    got = score(trip, offer, seat)
    example_id, example_seat = answer.correct[0]
    example = next(o for o in offers if o.offer_id == example_id)
    expected = f"{answer.best_score}, e.g. offer {example_id} with {a_seat(example_seat)}: " \
               f"{score_text(trip, example, example_seat)}"
    actual = f"{got}: {score_text(trip, offer, seat)}"
    if got == answer.best_score:
        message = f"offer {oid} with {a_seat(seat)} reaches the best score, {answer.best_score}"
    elif offer_best(trip, offer) == answer.best_score:
        better = next(s for s in offer.open_seats if score(trip, offer, s) == answer.best_score)
        message = (f"offer {oid} with {a_seat(seat)} scores {got}; {a_seat(better)} is open on it and "
                   f"would score {answer.best_score}, the best")
    else:
        message = (f"offer {oid} with {a_seat(seat)} scores {got} ({score_text(trip, offer, seat)}); the best is "
                   f"{answer.best_score}, e.g. offer {example_id} with {a_seat(example_seat)}")
    verdict.add("best-score", got == answer.best_score, expected, actual, message)
    if verdict.blocked_by is not None:
        return verdict.finish()

    # P2: the lowest fare among the offers reaching the best score.
    cheapest = sorted({offer_id for offer_id, _ in answer.correct})
    cheap = offer.fare_cents == answer.lowest_best_fare_cents
    verdict.add("lowest-fare-among-best", cheap,
                f"{money(answer.lowest_best_fare_cents)} (offer {', '.join(cheapest)})", money(offer.fare_cents),
                f"offer {oid} has the lowest fare, {money(offer.fare_cents)}, of the offers scoring "
                f"{answer.best_score}" if cheap else
                f"offer {oid} costs {money(offer.fare_cents)}; offer {cheapest[0]} also scores {answer.best_score} "
                f"and costs {money(answer.lowest_best_fare_cents)}")
    return verdict.finish()
