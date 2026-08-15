"""Check one physical port once and start charging only when it is idle.

This is intended for a Windows Task Scheduler trigger.  It does not inspect
the historical power-off record and it never waits for a scheduled time.
"""

from __future__ import annotations

import argparse
import asyncio
import sys

import aiohttp

from config import AREA_ID, OPEN_ID, validate_config
from main import begin_charge, get_device_info, get_user_info, log
from ports import get_port_status


DEFAULT_CHARGE_MONEY = 100  # 1 yuan in the Neptune request unit


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="检查指定端口，空闲时启动一次充电"
    )
    parser.add_argument("device", help="设备编号，例如 50959132")
    parser.add_argument("port", help="物理端口号，例如 12")
    parser.add_argument(
        "--charge-money",
        type=int,
        default=DEFAULT_CHARGE_MONEY,
        help="充电金额参数，默认 100（通常为 1 元）",
    )
    return parser.parse_args()


async def run(device: str, port: str, charge_money: int) -> int:
    errors = validate_config()
    if errors:
        for error in errors:
            log(error)
        return 2

    if not device.isdigit() or not port.isdigit() or int(port) < 1:
        log("设备编号或端口号无效")
        return 2
    if charge_money < 1:
        log("充电金额必须是正整数")
        return 2

    timeout = aiohttp.ClientTimeout(total=30)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        user_info = await get_user_info(session)
        if not user_info:
            log("获取用户信息失败")
            return 1

        balance = user_info.get("readyaccountmoney", 0)
        log(f"检查设备={device}，端口={port}，余额={balance / 100:.2f}元")
        if balance < charge_money:
            log("余额不足，未启动充电")
            return 1

        device_info = await get_device_info(session, device)
        if not device_info:
            log(f"获取设备 {device} 信息失败")
            return 1

        port_status = get_port_status(device_info.get("portstatur", ""), port)
        log(f"端口 {port} 当前状态码: {port_status}")
        if port_status != "0":
            log(f"端口 {port} 非空闲，未启动充电")
            return 3

        log(f"端口 {port} 空闲，开始充电")
        result = await begin_charge(
            session,
            device,
            port,
            balance,
            device_info,
            charge_money=charge_money,
        )
        if result.get("success"):
            log(f"充电启动成功: {result.get('msg', '')}")
            return 0

        log(f"充电启动失败: {result.get('msg', '未知错误')}")
        return 1


def main() -> int:
    args = parse_args()
    try:
        return asyncio.run(run(args.device, str(int(args.port)), args.charge_money))
    except KeyboardInterrupt:
        log("用户中断，未执行充电")
        return 130
    except Exception as exc:
        log(f"执行失败: {exc}")
        return 1


if __name__ == "__main__":
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
