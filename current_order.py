"""Read-only inspection of current Neptune charging orders and port states.

This module deliberately never calls ``beginCharge``.  The Neptune endpoint
used by the project is named ``getChargeLog`` and may contain the currently
running order as a record without an end timestamp.  The exact response
fields have varied, so the parser keeps the original record and reports the
fields it observed instead of assuming one status field.

Usage::

    python current_order.py
    python current_order.py --raw
"""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime, timedelta
from typing import Any, Iterable

import aiohttp

from config import AREA_ID, EMPLOYEE_ID, validate_config
from main import (
    HEADERS,
    TZ_BEIJING,
    get_charge_log,
    get_device_info,
)


DEVICE_KEYS = ("devaddress", "device", "deviceid", "deviceId")
PORT_KEYS = ("devport", "port", "portno", "portNo")
START_KEYS = (
    "startdt",
    "startDt",
    "begindt",
    "beginDt",
    "starttime",
    "startTime",
)
END_KEYS = ("enddt", "endDt", "endtime", "endTime")
END_TYPE_KEYS = ("endtype", "endType", "endstatus", "endStatus")
STATUS_KEYS = (
    "status",
    "state",
    "chargestatus",
    "chargeStatus",
    "orderstatus",
    "orderStatus",
)

ACTIVE_STATUS_VALUES = {
    "active",
    "charging",
    "running",
    "started",
    "进行中",
    "充电中",
    "正在充电",
}
ENDED_STATUS_VALUES = {
    "ended",
    "finished",
    "completed",
    "stopped",
    "已结束",
    "已完成",
    "结束",
}


def first_value(record: dict[str, Any], keys: Iterable[str]) -> Any:
    """Return the first present, non-empty value for a set of aliases."""

    for key in keys:
        if key in record and record[key] not in (None, ""):
            return record[key]
    return None


def is_empty_timestamp(value: Any) -> bool:
    return value in (None, "", 0, "0")


def is_active_order(record: dict[str, Any]) -> bool:
    """Best-effort detection of an order that has not ended yet.

    An explicit active status wins.  Otherwise, a record with a device, port,
    and start time but no end timestamp is treated as an active candidate.
    Records with an explicit end status or end timestamp are excluded.
    """

    device = first_value(record, DEVICE_KEYS)
    port = first_value(record, PORT_KEYS)
    if device is None or port is None:
        return False

    status = first_value(record, STATUS_KEYS)
    if status is not None:
        normalized = str(status).strip().lower()
        if normalized in ACTIVE_STATUS_VALUES:
            return True
        if normalized in ENDED_STATUS_VALUES:
            return False

    end_type = first_value(record, END_TYPE_KEYS)
    if end_type is not None and str(end_type).strip().lower() in {
        "39",
        "end",
        "ended",
        "finished",
        "completed",
    }:
        return False

    start = first_value(record, START_KEYS)
    end = first_value(record, END_KEYS)
    return start is not None and is_empty_timestamp(end)


def format_timestamp(value: Any) -> str | None:
    """Format common Neptune timestamps without failing the whole report."""

    if is_empty_timestamp(value):
        return None
    text = str(value).strip()
    # ``begindt`` is returned as YYYYMMDDHHMMSS, while ``enddt`` is usually
    # a Unix timestamp in milliseconds.
    if len(text) == 14 and text.isdigit():
        try:
            return datetime.strptime(text, "%Y%m%d%H%M%S").replace(
                tzinfo=TZ_BEIJING
            ).strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            pass
    try:
        number = float(text)
        if number > 100_000_000_000:
            number /= 1000
        return datetime.fromtimestamp(number, tz=TZ_BEIJING).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
    except (TypeError, ValueError, OverflowError, OSError):
        return str(value)


def summarize_order(record: dict[str, Any]) -> dict[str, Any]:
    """Expose stable fields while retaining the original API field names."""

    return {
        "device": first_value(record, DEVICE_KEYS),
        "port": first_value(record, PORT_KEYS),
        "status": first_value(record, STATUS_KEYS),
        "start_time": format_timestamp(first_value(record, START_KEYS)),
        "end_time": format_timestamp(first_value(record, END_KEYS)),
        "end_type": first_value(record, END_TYPE_KEYS),
        "raw": record,
    }


def month_terms(now: datetime) -> list[str]:
    terms = [now.strftime("%Y%m")]
    if now.day <= 3:
        previous_month = now.replace(day=1) - timedelta(days=1)
        terms.append(previous_month.strftime("%Y%m"))
    return terms


async def collect_report(session: aiohttp.ClientSession) -> dict[str, Any]:
    now = datetime.now(TZ_BEIJING)
    logs: list[dict[str, Any]] = []
    for term in month_terms(now):
        result = await get_charge_log(session, term)
        logs.extend(item for item in result if isinstance(item, dict))

    active_orders = [summarize_order(record) for record in logs if is_active_order(record)]
    field_names = sorted({key for record in logs for key in record})

    # The history endpoint may not expose an active order.  Device status is
    # therefore reported independently for every device seen in the history.
    device_states: list[dict[str, Any]] = []
    devices = sorted(
        {str(first_value(record, DEVICE_KEYS)) for record in logs if first_value(record, DEVICE_KEYS) is not None}
    )
    for device in devices:
        info = await get_device_info(session, device)
        if not info:
            device_states.append({"device": device, "error": "getDeviceInfo failed"})
            continue
        raw_status = str(info.get("portstatur", ""))
        ports = []
        for number, code in enumerate(raw_status, start=1):
            ports.append(
                {
                    "port": number,
                    "status_code": code,
                    "status": {"0": "idle", "1": "in_use", "3": "fault"}.get(
                        code, "unknown"
                    ),
                }
            )
        device_states.append(
            {
                "device": device,
                "device_name": info.get("devdescript"),
                "port_status_raw": raw_status,
                "in_use_ports": [item["port"] for item in ports if item["status_code"] == "1"],
                "ports": ports,
            }
        )

    return {
        "queried_at": now.strftime("%Y-%m-%d %H:%M:%S %z"),
        "terms": month_terms(now),
        "record_count": len(logs),
        "record_fields": field_names,
        "active_order_count": len(active_orders),
        "active_orders": active_orders,
        "device_states": device_states,
        "raw_records": logs,
    }


async def run(raw: bool = False) -> int:
    errors = validate_config()
    if errors:
        for error in errors:
            print(error)
        return 2

    timeout = aiohttp.ClientTimeout(total=30)
    async with aiohttp.ClientSession(timeout=timeout, headers=HEADERS) as session:
        report = await collect_report(session)

    if not raw:
        report.pop("raw_records", None)
        for order in report["active_orders"]:
            order.pop("raw", None)
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="只读查询当前 Neptune 充电订单")
    parser.add_argument(
        "--raw",
        action="store_true",
        help="同时输出接口返回的原始订单记录",
    )
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run(raw=parse_args().raw)))
