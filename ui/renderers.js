// How this plugin's page draws its tasks' outputs: what to tell us to book (fields, definitions, airports),
// the flight offers as a table, and a booking as the chosen offer and seat, its score preference by
// preference, and the verifier's checks.
import { dataTable, disclosure, h, plural, statusPill } from "./kit/components.js";

const money = (cents) => `$${(cents / 100).toFixed(2)}`;
const words = (value) => value.toLowerCase().replace("_", "-");

function facts(rows) {
  return h(
    "dl",
    { class: "trip-facts" },
    rows.map(([label, value]) => [h("dt", { text: label }), h("dd", { text: value })]),
  );
}

function fieldsTable(fields) {
  return dataTable({
    columns: [
      { key: "name", label: "Field", primary: true },
      { key: "kind", label: "Takes" },
      { key: "example", label: "Example" },
      { key: "description", label: "Meaning" },
    ],
    rows: fields,
    caption: "What to tell us",
    empty: "No fields.",
  }).element;
}

function airportsTable(airports) {
  return dataTable({
    columns: [
      { key: "code", label: "Code", primary: true },
      { key: "city", label: "City" },
      { key: "country", label: "Country" },
      { key: "name", label: "Airport" },
    ],
    rows: airports,
    sort: { key: "code" },
    caption: "Airports",
    empty: "No airports.",
  }).element;
}

function requirements(answer) {
  const parts = [h("p", { class: "muted", text: `Booking as of today, ${answer.today}` })];
  if (answer.fields.length) parts.push(fieldsTable(answer.fields));
  if (answer.definitions.length) {
    parts.push(h("h4", { text: "What it means" }), h("ul", { class: "rules" }, answer.definitions.map((rule) => h("li", { text: rule }))));
  }
  parts.push(h("h4", { text: "For example" }), h("blockquote", { class: "example", text: answer.example_request }));
  if (answer.airports.length) {
    parts.push(disclosure({ summary: plural(answer.airports.length, "airport"), open: !answer.fields.length }, airportsTable(answer.airports)));
  }
  return h("div", { class: "requirements" }, parts);
}

function route(offer) {
  const stops = offer.segments.map((segment) => segment.origin).concat(offer.segments.at(-1).destination);
  return stops.join(" → ");
}

function offersTable(offers) {
  return dataTable({
    columns: [
      { key: "offer_id", label: "Offer", primary: true },
      { key: "depart_local", label: "Departs (local)" },
      { key: "arrive_local", label: "Arrives (local)" },
      { key: "time_of_day", label: "Time", value: (o) => words(o.time_of_day) },
      { key: "route", label: "Route", value: route },
      { key: "carrier", label: "Airline" },
      { key: "flights", label: "Flights", value: (o) => o.segments.map((s) => s.flight_number).join(", ") },
      { key: "stops", label: "Stops", numeric: true },
      { key: "total_minutes", label: "Total (min)", numeric: true },
      { key: "open_seats", label: "Open seats", value: (o) => o.open_seats.map(words).join(", ") },
      { key: "fare_cents", label: "Fare", numeric: true, render: (o) => money(o.fare_cents) },
    ],
    rows: offers,
    sort: { key: "depart_local" },
    caption: "Flight offers",
    empty: "No offers on this route and day.",
  }).element;
}

function pointsTable(points) {
  return dataTable({
    columns: [
      { key: "part", label: "Preference", primary: true },
      { key: "points", label: "Points", numeric: true },
    ],
    rows: [
      { part: "Seat", points: points.seat },
      { part: "Time of day", points: points.time },
      { part: "Nonstop or connecting", points: points.stops },
      { part: "Score", points: points.total },
      { part: "Best possible that day", points: points.best },
    ],
    caption: "Score",
    empty: "No score.",
  }).element;
}

function checksTable(checks) {
  const tone = (ok) => (ok === true ? "ok" : ok === false ? "bad" : "neutral");
  const label = (ok) => (ok === true ? "holds" : ok === false ? "fails" : "not checked");
  return dataTable({
    columns: [
      { key: "id", label: "Check", primary: true },
      { key: "ok", label: "Result", render: (c) => statusPill(label(c.ok), tone(c.ok)) },
      { key: "expected", label: "Expected" },
      { key: "actual", label: "Booked" },
      { key: "message", label: "Why" },
    ],
    rows: checks,
    caption: "Checks",
    empty: "No checks.",
  }).element;
}

function bookingCard(booking, context) {
  const verdict = (context && context.verdict) || {};
  const details = verdict.details || {};
  const parts = [
    statusPill(`Booked ${booking.offer_id}, ${words(booking.seat)} seat`, verdict.valid === false ? "bad" : "ok", { icon: true }),
    facts([
      ["Offer", booking.offer_id],
      ["Seat", words(booking.seat)],
      ["Run", booking.run_id],
    ]),
  ];
  if (details.points) parts.push(pointsTable(details.points));
  if (Array.isArray(details.checks)) parts.push(disclosure({ summary: plural(details.checks.length, "check"), open: false }, checksTable(details.checks)));
  return h("div", { class: "booking" }, parts);
}

export default {
  RequirementsOutput: requirements,
  SearchOutput: ({ note, offers }) =>
    h(
      "div",
      { class: "offers" },
      h("p", { class: "muted", text: `${plural(offers.length, "offer")}. ${note}` }),
      offersTable(offers),
    ),
  BookingOutput: bookingCard,
};
