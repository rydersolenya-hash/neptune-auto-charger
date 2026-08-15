"""终端三参数定时充电入口。

用法：
    python schedule_charge.py <设备编号> <物理端口号> <HH:MM>

示例：
    python schedule_charge.py 50959132 12 06:05
"""

import argparse
import asyncio
import sys
from datetime import datetime

import aiohttp

from charge_schedule import (
    TZ_BEIJING,
    build_charge_plan,
    next_scheduled_datetime,
    parse_schedule_time,
)
from config import AREA_ID, SCHEDULE_TIME, validate_config
from main import begin_charge, get_device_info, get_user_info, log
from ports import get_port_status


DEFAULT_CHARGE_MONEY = 100  # 1 元，适合首次终端测试


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="在指定北京时间启动指定设备和物理端口的充电"
    )
    parser.add_argument("device", help="设备编号，例如 50959132")
    parser.add_argument("port", help="物理端口号，从 1 开始，例如 12")
    parser.add_argument(
        "schedule_time",
        nargs="?",
        default=SCHEDULE_TIME,
        help=f"北京时间 HH:MM，默认 {SCHEDULE_TIME}",
    )
    parser.add_argument(
        "--charge-money",
        type=int,
        default=DEFAULT_CHARGE_MONEY,
        help="充电金额参数，默认 100（通常为 1 元）",
    )
    return parser.parse_args()


def validate_args(args: argparse.Namespace) -> None:
    if not args.device.isdigit():
        raise ValueError("设备编号必须是数字")
    try:
        port = int(args.port)
    except ValueError as exc:
        raise ValueError("端口号必须是从 1 开始的数字") from exc
    if port < 1:
        raise ValueError("端口号必须从 1 开始")
    parse_schedule_time(args.schedule_time)
    if args.charge_money < 1:
        raise ValueError("charge-money 必须是正整数")


async def inspect_target(
    session,
    device: str,
    port: str,
    schedule_time: str,
    balance=None,
    charge_money: int = DEFAULT_CHARGE_MONEY,
):
    device_info = await get_device_info(session, device)
    if not device_info:
        raise RuntimeError(f"获取设备 {device} 信息失败")

    port_status = get_port_status(device_info.get("portstatur", ""), port)
    plan = build_charge_plan(
        device,
        port,
        port_status,
        schedule_time=schedule_time,
        balance=balance,
        charge_money=charge_money,
    )
    plan["device_name"] = device_info.get("devdescript")
    plan["work_time"] = device_info.get("workTime")
    return device_info, plan


async def run(args: argparse.Namespace) -> int:
    config_errors = validate_config()
    if config_errors:
        raise RuntimeError("；".join(config_errors))
    validate_args(args)

    device = str(args.device)
    port = str(int(args.port))
    scheduled_at = next_scheduled_datetime(datetime.now(TZ_BEIJING), args.schedule_time)
    log(f"设备: {device}")
    log(f"物理端口: {port}")
    log(f"计划时间: {scheduled_at.strftime('%Y-%m-%d %H:%M:%S')}（北京时间）")

    timeout = aiohttp.ClientTimeout(total=30)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        user_info = await get_user_info(session)
        if not user_info:
            raise RuntimeError("获取用户信息失败")

        balance = user_info.get("readyaccountmoney", 0)
        device_info, plan = await inspect_target(
            session,
            device,
            port,
            args.schedule_time,
            balance=balance,
            charge_money=args.charge_money,
        )
        print(f"计划预览: {plan}")
        log("程序将保持运行，等待到点；当前不会启动充电")

        while True:
            remaining = (scheduled_at - datetime.now(TZ_BEIJING)).total_seconds()
            if remaining <= 0:
                break
            await asyncio.sleep(min(remaining, 30))

        log("到达计划时间，重新检查用户、设备和端口状态...")
        user_info = await get_user_info(session)
        if not user_info:
            raise RuntimeError("到点后获取用户信息失败")
        balance = user_info.get("readyaccountmoney", 0)
        if balance < 100:
            raise RuntimeError("余额不足 1 元")

        device_info, plan = await inspect_target(
            session,
            device,
            port,
            args.schedule_time,
            balance=balance,
            charge_money=args.charge_money,
        )
        print(f"到点检查: {plan}")
        if not plan["ready"]:
            raise RuntimeError(f"端口当前不可用: {plan}")

        log(f"开始充电: 设备={device}, 端口={port}, 金额={args.charge_money / 100:.2f}元")
        result = await begin_charge(
            session,
            device,
            port,
            balance,
            device_info,
            charge_money=args.charge_money,
        )
        if not result.get("success"):
            raise RuntimeError(f"充电启动失败: {result.get('msg')}")
        log(f"充电启动成功: {result.get('msg', '')}")
        return 0


def main() -> int:
    args = parse_args()
    try:
        return asyncio.run(run(args))
    except KeyboardInterrupt:
        log("用户中断，未执行充电")
        return 130
    except Exception as exc:
        log(f"失败: {exc}")
        return 1


if __name__ == "__main__":
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
