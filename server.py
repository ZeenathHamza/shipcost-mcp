"""MCP tools for illustrative freight estimates and route planning."""

from __future__ import annotations

# No secrets are required for the core tools. If you add carrier API integrations, read keys from environment variables only — never hardcode.

import argparse
import json
import logging
import math
import os
import sys
from typing import Any

import uvicorn
from mcp.server.fastmcp import FastMCP
from starlette.types import ASGIApp, Receive, Scope, Send

from rates import CARRIER_BY_MODE, CITY_DISTANCES, RATE_TABLE

LOGGER = logging.getLogger("shipcost_mcp")


class JsonLogFormatter(logging.Formatter):
    """Format application logs as one JSON object per line."""

    def format(self, record: logging.LogRecord) -> str:
        standard_fields = set(logging.makeLogRecord({}).__dict__)
        entry: dict[str, Any] = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        context = {
            key: value
            for key, value in record.__dict__.items()
            if key not in standard_fields
        }
        if context:
            entry["context"] = context
        return json.dumps(entry)


def configure_logging() -> None:
    """Send structured logs to stderr to keep MCP stdio responses clean."""
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(JsonLogFormatter())
    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(logging.INFO)


mcp = FastMCP("ShipCost MCP", host="0.0.0.0", port=int(os.environ.get("PORT", "8080")))


def _validate_shipment(
    origin: str, destination: str, weight_kg: float, distance_km: float
) -> None:
    if not isinstance(origin, str) or not origin.strip():
        raise ValueError("origin must be a non-empty string")
    if not isinstance(destination, str) or not destination.strip():
        raise ValueError("destination must be a non-empty string")
    if (
        isinstance(weight_kg, bool)
        or not isinstance(weight_kg, (int, float))
        or not math.isfinite(weight_kg)
        or weight_kg <= 0
    ):
        raise ValueError("weight_kg must be a finite positive number")
    if (
        isinstance(distance_km, bool)
        or not isinstance(distance_km, (int, float))
        or not math.isfinite(distance_km)
        or distance_km <= 0
    ):
        raise ValueError("distance_km must be a finite positive number")


def _quote(mode: str, weight_kg: float, distance_km: float) -> tuple[float, int]:
    rates = RATE_TABLE[mode]
    cost = (
        rates["base_cost"]
        + rates["per_km"] * distance_km
        + rates["per_kg"] * weight_kg
    )
    transit_days = max(1, math.ceil(distance_km / rates["avg_speed_kmph"] / 24))
    return round(cost, 2), transit_days


@mcp.tool()
def estimate_freight(
    origin: str,
    destination: str,
    weight_kg: float,
    distance_km: float,
    mode: str = "FTL",
) -> dict[str, str | float | int]:
    """Estimate illustrative freight cost, transit time, and carrier for a shipment.

    Provide positive weight and distance values and one of FTL, LTL, AIR, or SEA.
    All prices are fictional planning estimates in Sri Lankan rupees (LKR).
    """
    _validate_shipment(origin, destination, weight_kg, distance_km)
    if not isinstance(mode, str) or mode not in RATE_TABLE:
        raise ValueError(f"mode must be one of {', '.join(RATE_TABLE)}")

    cost, transit_days = _quote(mode, weight_kg, distance_km)
    result: dict[str, str | float | int] = {
        "origin": origin.strip(),
        "destination": destination.strip(),
        "mode": mode,
        "estimated_cost_lkr": cost,
        "estimated_transit_days": transit_days,
        "carrier_suggestion": CARRIER_BY_MODE[mode],
    }
    LOGGER.info(
        "freight estimate completed",
        extra={"mode": mode, "estimated_cost_lkr": cost},
    )
    return result


@mcp.tool()
def compare_carriers(
    origin: str, destination: str, weight_kg: float, distance_km: float
) -> list[dict[str, str | float | int]]:
    """Compare four illustrative carrier options, ranked by estimated LKR cost."""
    _validate_shipment(origin, destination, weight_kg, distance_km)

    options: list[dict[str, str | float | int]] = []
    for mode, carrier in CARRIER_BY_MODE.items():
        cost, transit_days = _quote(mode, weight_kg, distance_km)
        options.append(
            {
                "name": carrier,
                "mode": mode,
                "cost_lkr": cost,
                "transit_days": transit_days,
            }
        )
    ranked_options = sorted(options, key=lambda option: float(option["cost_lkr"]))
    LOGGER.info("carrier comparison completed", extra={"option_count": len(ranked_options)})
    return ranked_options


@mcp.tool()
def calculate_route(pickup_points: list[str], depot: str) -> dict[str, Any]:
    """Order pickup cities from a depot using a nearest-neighbor distance heuristic.

    City names must match the supported Sri Lankan cities in the distance map. The
    route starts at the depot and visits each pickup once; it does not return to
    the depot. Travel time uses an illustrative average road speed of 40 km/h.
    """
    if not isinstance(depot, str) or depot not in CITY_DISTANCES:
        raise ValueError(f"depot must be one of: {', '.join(CITY_DISTANCES)}")
    if not isinstance(pickup_points, list) or any(
        not isinstance(city, str) or city not in CITY_DISTANCES
        for city in pickup_points
    ):
        raise ValueError(
            "pickup_points must contain supported city names: "
            f"{', '.join(CITY_DISTANCES)}"
        )
    if len(set(pickup_points)) != len(pickup_points):
        raise ValueError("pickup_points must not contain duplicate cities")
    if depot in pickup_points:
        raise ValueError("pickup_points must not include the depot")

    remaining = set(pickup_points)
    current_city = depot
    optimized_order: list[str] = []
    total_distance_km = 0

    while remaining:
        next_city = min(
            remaining,
            key=lambda city: (CITY_DISTANCES[current_city][city], city),
        )
        total_distance_km += CITY_DISTANCES[current_city][next_city]
        optimized_order.append(next_city)
        remaining.remove(next_city)
        current_city = next_city

    result: dict[str, Any] = {
        "optimized_order": optimized_order,
        "total_distance_km": total_distance_km,
        "estimated_time_hours": round(total_distance_km / 40, 2),
    }
    LOGGER.info(
        "route calculated",
        extra={"pickup_count": len(optimized_order), "total_distance_km": total_distance_km},
    )
    return result


class HealthCheckApp:
    """Serve a lightweight health response and delegate other requests to MCP."""

    def __init__(self, mcp_app: ASGIApp) -> None:
        self.mcp_app = mcp_app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and scope.get("path") == "/health":
            body = b'{"status":"ok"}'
            await send(
                {
                    "type": "http.response.start",
                    "status": 200,
                    "headers": [
                        (b"content-type", b"application/json"),
                        (b"content-length", str(len(body)).encode("ascii")),
                    ],
                }
            )
            await send({"type": "http.response.body", "body": body})
            return
        await self.mcp_app(scope, receive, send)


def create_http_app() -> ASGIApp:
    """Build the ASGI application with MCP and a Cloud Run health endpoint."""
    return HealthCheckApp(mcp.streamable_http_app())


def main() -> None:
    """Run the MCP server over HTTP by default or stdio for local MCP clients."""
    configure_logging()
    parser = argparse.ArgumentParser(description="ShipCost MCP freight estimation server")
    parser.add_argument(
        "--transport",
        choices=("streamable-http", "stdio"),
        default="streamable-http",
        help="MCP transport to run (default: streamable-http)",
    )
    args = parser.parse_args()

    if args.transport == "stdio":
        LOGGER.info("starting MCP server", extra={"transport": "stdio"})
        mcp.run(transport="stdio")
        return

    port = int(os.environ.get("PORT", "8080"))
    LOGGER.info("starting MCP server", extra={"transport": "streamable-http", "port": port})
    uvicorn.run(create_http_app(), host="0.0.0.0", port=port, log_config=None)


if __name__ == "__main__":
    main()
