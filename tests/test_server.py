"""The real MCP server over stdio: it lists the four tools and answers booking_requirements, get_trip and
search_flights, and refuses a request it cannot book."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import anyio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parent.parent


def test_the_server_serves_the_tools(tmp_path: Path) -> None:
    environment = dict(os.environ, NANOAGENT_WORKSPACE=str(tmp_path), PYTHONPATH=str(ROOT / "src"))
    parameters = StdioServerParameters(command=sys.executable, args=["-m", "plugin"], env=environment, cwd=str(ROOT))

    def payload(answer):
        return answer.structuredContent or json.loads(answer.content[0].text)

    async def session() -> tuple:
        async with stdio_client(parameters) as (read, write), ClientSession(read, write) as client:
            await client.initialize()
            tools = sorted(tool.name for tool in (await client.list_tools()).tools)
            guide = payload(await client.call_tool("booking_requirements", {"topic": "FIELDS"}))
            travel_date = guide["fields"][3]["example"]
            request = {"traveller_name": "Maya Chen", "origin": "ORD", "destination": "LHR",
                       "travel_date": travel_date, "seat_preference": "WINDOW", "seat_weight": 20,
                       "time_preference": "RED_EYE", "time_weight": 30, "stops_preference": "NONSTOP",
                       "stops_weight": 50}
            trip = payload(await client.call_tool("get_trip", request))
            found = await client.call_tool("search_flights", {
                "run_id": trip["run_id"], "origin": "ORD", "destination": "LHR", "travel_date": travel_date})
            refused = await client.call_tool("get_trip", request | {"seat_weight": 21})
            return tools, guide, trip, found, refused

    tools, guide, trip, found, refused = anyio.run(session)
    assert tools == ["booking_requirements", "get_trip", "search_flights", "solve_booking"]
    assert [field["name"] for field in guide["fields"]][:2] == ["traveller_name", "origin"]
    assert trip["trip"]["origin"]["city"] == "Chicago"
    assert trip["trip"]["stops_weight"] == 50
    assert (tmp_path / "runs" / trip["run_id"] / "trip.json").is_file()
    assert not found.isError and (tmp_path / "runs" / trip["run_id"] / "search-1.json").is_file()
    assert payload(found)["note"].startswith("Simulated")
    assert refused.isError
