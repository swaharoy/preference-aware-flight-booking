"""booking_requirements, read independently of the tool's own code: every field of the booking task's input
is named, described as the contract describes it, and has an example the input accepts; every airport is
listed; the weights and each preference are defined; nothing about how to choose is said."""

from __future__ import annotations

import dataclasses
import typing
from pathlib import Path

import pytest
from conftest import TODAY
from helpers import tool_input

from contract import AirportCode, RequirementsInput, Topic, TripInput
from plugin import booking_requirements, world


@pytest.fixture
def everything(tmp_path: Path):
    return booking_requirements(RequirementsInput(Topic.ALL), tmp_path)


def test_every_input_field_is_named_and_described_as_the_contract_says(everything) -> None:
    hints = typing.get_type_hints(TripInput, include_extras=True)
    assert [field.name for field in everything.fields] == [field.name for field in dataclasses.fields(TripInput)]
    for field in everything.fields:
        assert field.required is True
        assert field.description == typing.get_args(hints[field.name])[1]


def test_the_examples_make_a_request_the_booking_task_accepts(everything) -> None:
    example = {field.name: field.example for field in everything.fields}
    for name in ("seat_weight", "time_weight", "stops_weight"):
        example[name] = int(example[name])
    assert example["seat_weight"] + example["time_weight"] + example["stops_weight"] == 100
    assert tool_input("get_trip", example)["valid"] is True
    assert example["travel_date"] in everything.example_request
    for name in ("seat_weight", "time_weight", "stops_weight"):
        assert f"weight {example[name]}" in everything.example_request


def test_every_airport_is_listed(everything) -> None:
    assert [airport.code for airport in everything.airports] == [member.value for member in AirportCode]
    assert everything.airports[0].city == world.airport("ATL").city
    assert len(everything.airports) == len(world.AIRPORTS)


def test_the_definitions_state_today_the_limits_the_weights_and_each_preference(everything) -> None:
    assert everything.today == TODAY
    text = " ".join(everything.definitions)
    assert TODAY in text and "330 days" in text and "2027-10-01" in text
    assert "add up to exactly 100" in text and "0 to 100" in text
    assert "06:00 to 20:55" in text and "21:00 to 23:55" in text
    for word in ("WINDOW", "AISLE", "MIDDLE", "DAY", "RED_EYE", "NONSTOP", "CONNECTING"):
        assert word in text


def test_no_strategy_is_given(everything) -> None:
    text = " ".join([everything.example_request, *everything.definitions]).lower()
    for word in ("cheapest", "lowest", "fare", "score", "best", "highest", "tie"):
        assert word not in text


@pytest.mark.parametrize(("topic", "fields", "airports"), [(Topic.FIELDS, True, False), (Topic.AIRPORTS, False, True)])
def test_a_topic_narrows_the_answer(tmp_path: Path, topic: Topic, fields: bool, airports: bool) -> None:
    answer = booking_requirements(RequirementsInput(topic), tmp_path)
    assert bool(answer.fields) is fields and bool(answer.definitions) is fields and bool(answer.airports) is airports
