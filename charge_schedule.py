"""充电计划的时间解析和结构化输出。"""

from datetime import datetime, time, timezone, timedelta
import re
from typing import Optional, Union


TZ_BEIJING = timezone(timedelta(hours=8))
DEFAULT_SCHEDULE_TIME = "06:05"


def parse_schedule_time(value: str) -> time:
    """解析 HH:MM 格式的北京时间。"""
    if not isinstance(value, str) or re.fullmatch(r"\d{2}:\d{2}", value.strip()) is None:
        raise ValueError("预定时间必须使用 HH:MM 格式，例如 06:05")
    try:
        parsed = datetime.strptime(value.strip(), "%H:%M").time()
    except (AttributeError, ValueError) as exc:
        raise ValueError("预定时间必须使用 HH:MM 格式，例如 06:05") from exc
    return parsed


def next_scheduled_datetime(now: datetime, schedule_time: str) -> datetime:
    """返回下一个北京时间计划时刻；若今天已过，则安排到明天。"""
    parsed_time = parse_schedule_time(schedule_time)
    current = now.astimezone(TZ_BEIJING)
    scheduled = current.replace(
        hour=parsed_time.hour,
        minute=parsed_time.minute,
        second=0,
        microsecond=0,
    )
    if scheduled <= current:
        scheduled += timedelta(days=1)
    return scheduled


def build_charge_plan(
    device: Union[str, int],
    port: Union[str, int],
    port_status: Optional[str],
    schedule_time: str = DEFAULT_SCHEDULE_TIME,
    balance: Optional[int] = None,
    charge_money: Optional[int] = None,
) -> dict:
    """构造供日志、快捷指令或后续 HTTP 接口使用的充电计划。"""
    parsed_time = parse_schedule_time(schedule_time)
    plan = {
        "scheduled_time": parsed_time.strftime("%H:%M"),
        "timezone": "Asia/Shanghai",
        "device": str(device),
        "port": str(port),
        "port_status": port_status,
        "port_free": port_status == "0",
    }

    if balance is not None:
        plan["balance"] = balance
        plan["balance_yuan"] = round(balance / 100, 2)
    if charge_money is not None:
        plan["charge_money"] = charge_money
        plan["charge_money_yuan"] = round(charge_money / 100, 2)

    plan["ready"] = plan["port_free"]
    return plan
