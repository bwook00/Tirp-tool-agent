from typing import Any

from app.models.schemas import TransitOption
from app.tools.bus_search import search_buses
from app.tools.checkout import get_checkout_link
from app.tools.train_search import search_trains

__all__ = [
    "search_trains",
    "search_buses",
    "get_checkout_link",
    "execute_tool",
    "TOOL_DEFINITIONS",
]

TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "name": "search_trains",
        "description": (
            "Search for train options between two cities via Omio. "
            "Returns a list of available trains with departure/arrival times, prices, and duration."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "origin": {
                    "type": "string",
                    "description": "Departure city (e.g. 'Berlin', 'Paris')",
                },
                "destination": {
                    "type": "string",
                    "description": "Arrival city (e.g. 'Munich', 'Amsterdam')",
                },
                "date": {
                    "type": "string",
                    "description": "Travel date in YYYY-MM-DD format",
                },
                "time": {
                    "type": "string",
                    "description": "Preferred departure time in HH:MM format (optional)",
                },
            },
            "required": ["origin", "destination", "date"],
        },
    },
    {
        "name": "search_buses",
        "description": (
            "Search for bus options between two cities via Omio. "
            "Returns a list of available buses with departure/arrival times, prices, and duration."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "origin": {
                    "type": "string",
                    "description": "Departure city (e.g. 'Berlin', 'Prague')",
                },
                "destination": {
                    "type": "string",
                    "description": "Arrival city (e.g. 'Munich', 'Vienna')",
                },
                "date": {
                    "type": "string",
                    "description": "Travel date in YYYY-MM-DD format",
                },
                "time": {
                    "type": "string",
                    "description": "Preferred departure time in HH:MM format (optional)",
                },
            },
            "required": ["origin", "destination", "date"],
        },
    },
    {
        "name": "get_checkout_link",
        "description": (
            "Generate a booking/checkout link for a selected transit option. "
            "Returns a URL and an expiration timestamp."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "transport_type": {
                    "type": "string",
                    "enum": ["train", "flight", "bus"],
                    "description": "Type of transport",
                },
                "provider": {
                    "type": "string",
                    "description": "Provider name (e.g. 'Deutsche Bahn', 'FlixBus')",
                },
                "departure_time": {
                    "type": "string",
                    "description": "Departure time in ISO 8601 format",
                },
                "arrival_time": {
                    "type": "string",
                    "description": "Arrival time in ISO 8601 format",
                },
                "duration_minutes": {
                    "type": "integer",
                    "description": "Duration in minutes",
                },
                "price": {
                    "type": "number",
                    "description": "Price amount",
                },
                "currency": {
                    "type": "string",
                    "description": "Currency code (default: EUR)",
                },
                "transfers": {
                    "type": "integer",
                    "description": "Number of transfers",
                },
                "details": {
                    "type": "string",
                    "description": "Additional details about the option",
                },
            },
            "required": [
                "transport_type",
                "provider",
                "departure_time",
                "arrival_time",
                "duration_minutes",
                "price",
            ],
        },
    },
]

_TOOL_DISPATCH: dict[str, Any] = {
    "search_trains": search_trains,
    "search_buses": search_buses,
    "get_checkout_link": None,  # handled specially below
}


async def execute_tool(name: str, arguments: dict[str, Any]) -> Any:
    """Dispatch a tool call to the appropriate function.

    For search tools, passes arguments directly.
    For get_checkout_link, constructs a TransitOption from the arguments first.
    """
    if name == "get_checkout_link":
        option = TransitOption(**arguments)
        return await get_checkout_link(option)

    func = _TOOL_DISPATCH.get(name)
    if func is None:
        raise ValueError(f"Unknown tool: {name}")

    return await func(**arguments)
